"""Subprocess pipelines (compress / encrypt / decrypt / decompress) and archive readers.

Write path : python tarfile stream -> gzip|bzip2|zstd -> [gpg|age] -> <name>.part
Read path  : file -> [gpg|age -d] -> gzip|bzip2|zstd -d -> tar stream
Zip        : pyzipper (AES-256 only) in-process.
Secrets travel via an inherited pipe fd (gpg) or a pty (age); never argv/env/disk.
"""
import fcntl
import gzip
import json
import os
import pty
import select
import signal
import stat
import subprocess
import tarfile
import termios
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional

from .redact import redact

FMT_EXT = {"tar.gz": ".tar.gz", "tar.zst": ".tar.zst", "tar.bz2": ".tar.bz2", "zip": ".zip"}


class PipelineError(RuntimeError):
    pass


def comp_cmd(fmt, level):
    if fmt == "tar.gz":
        return ["gzip", "-c", f"-{level}"]
    if fmt == "tar.bz2":
        return ["bzip2", "-c", f"-{level}"]
    if fmt == "tar.zst":
        return ["zstd", "-c", "-q", f"-{level}", "-T0"]
    raise ValueError(fmt)


def decomp_cmd(fmt):
    return {"tar.gz": ["gzip", "-dc"], "tar.bz2": ["bzip2", "-dc"], "tar.zst": ["zstd", "-dc", "-q"]}[fmt]


# ---------------------------------------------------------------- processes
def _pty_feed(master, secret, p):
    sent, buf = 0, b""
    try:
        while p.poll() is None:
            r, _, _ = select.select([master], [], [], 0.5)
            if not r:
                continue
            try:
                data = os.read(master, 1024)
            except OSError:
                time.sleep(0.05)  # EIO before the child opened /dev/tty: not an error
                continue
            buf += data
            if sent < 3 and b"assphrase" in buf[-300:] and buf.rstrip().endswith(b":"):
                os.write(master, secret.encode() + b"\n")
                sent += 1
                buf = b""
    finally:
        for fd in (master,):
            try:
                os.close(fd)
            except OSError:
                pass


class Proc:
    """Popen wrapper: own process group, stderr tail captured, optional secret delivery."""

    def __init__(self, cmd, stdin=None, stdout=subprocess.PIPE, env=None, secret_fd=None, pty_secret=None):
        self.cmd = cmd
        self._tail = deque(maxlen=30)
        kw = dict(stdin=stdin, stdout=stdout, stderr=subprocess.PIPE, env=env, close_fds=True)
        slave = master = None
        if secret_fd is not None:
            kw["pass_fds"] = (secret_fd,)
        if pty_secret is not None:
            master, slave = pty.openpty()

            def pre():
                os.setsid()
                fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
            kw["preexec_fn"] = pre
        else:
            kw["start_new_session"] = True
        self.p = subprocess.Popen(cmd, **kw)
        if pty_secret is not None:
            # keep `slave` open in the parent until the child exits (avoids EIO races)
            def feed():
                try:
                    _pty_feed(master, pty_secret, self.p)
                finally:
                    try:
                        os.close(slave)
                    except OSError:
                        pass
            threading.Thread(target=feed, daemon=True).start()
        threading.Thread(target=self._drain, daemon=True).start()

    def _drain(self):
        try:
            for line in iter(self.p.stderr.readline, b""):
                self._tail.append(line.decode("utf-8", "replace").rstrip())
        except (ValueError, OSError):
            pass

    def err(self):
        return redact("\n".join(self._tail)[-1500:])

    def terminate(self, grace=5.0):
        if self.p.poll() is not None:
            return
        try:
            os.killpg(self.p.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            self.p.wait(grace)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self.p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.p.wait()


def _secret_pipe(secret):
    r, w = os.pipe()
    os.write(w, secret.encode() + b"\n")
    os.close(w)
    return r


def _is_age_encrypted_identity(path):
    try:
        with open(path, "rb") as f:
            head = f.read(40)
        return head.startswith(b"age-encryption.org/") or head.startswith(b"-----BEGIN AGE ENCRYPTED")
    except OSError:
        return False


def identity_path(settings, name):
    base = os.path.basename(name or "")
    if not base:
        raise PipelineError("identity_file not configured")
    p = settings.keys_dir / base
    if not p.is_file():
        raise PipelineError(f"age identity file not found in keys dir: {base}")
    return str(p)


def crypto_proc(enc, direction, secret, stdin, stdout, settings):
    tool, mode = enc["tool"], enc.get("mode", "passphrase")
    env = dict(os.environ, GNUPGHOME=str(settings.gnupg_home))
    fd = None
    pty_secret = None
    try:
        if tool == "gpg":
            base = ["gpg", "--batch", "--yes", "--no-tty", "--pinentry-mode", "loopback"]
            if secret:
                fd = _secret_pipe(secret)
                base += ["--passphrase-fd", str(fd)]
            if direction == "encrypt":
                if mode == "passphrase":
                    cmd = base + ["--symmetric", "--cipher-algo", "AES256", "--s2k-mode", "3",
                                  "--s2k-digest-algo", "SHA512", "--s2k-count", "65011712",
                                  "--compress-algo", "none", "-o", "-"]
                else:
                    cmd = base + ["--trust-model", "always", "--encrypt", "--recipient", enc["recipient"],
                                  "--compress-algo", "none", "-o", "-"]
            else:
                cmd = base + ["--decrypt", "-o", "-"]
        elif tool == "age":
            if direction == "encrypt":
                if mode == "passphrase":
                    cmd, pty_secret = ["age", "-p"], secret
                else:
                    cmd = ["age", "-r", enc["recipient"]]
            else:
                if mode == "passphrase":
                    cmd, pty_secret = ["age", "-d"], secret
                else:
                    ip = identity_path(settings, enc.get("identity_file"))
                    cmd = ["age", "-d", "-i", ip]
                    if _is_age_encrypted_identity(ip):
                        pty_secret = secret
                        if not secret:
                            raise PipelineError("age identity is passphrase-protected: passphrase required")
        else:
            raise PipelineError(f"unknown encryption tool {tool}")
        return Proc(cmd, stdin=stdin, stdout=stdout, env=env, secret_fd=fd, pty_secret=pty_secret)
    finally:
        if fd is not None:
            os.close(fd)


# ---------------------------------------------------------------- write chain
class WriteChain:
    def __init__(self, fmt, level, enc, secret, part_path, settings):
        self.procs = []
        self.out = open(part_path, "wb")
        try:
            comp = Proc(comp_cmd(fmt, level), stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE if enc else self.out)
            self.procs.append(comp)
            if enc:
                e = crypto_proc(enc, "encrypt", secret, comp.p.stdout, self.out, settings)
                comp.p.stdout.close()
                self.procs.append(e)
            self.sink = comp.p.stdin
        except Exception:
            self.abort()
            raise

    def finish(self):
        """Close input, wait for all stages, fsync. Raises PipelineError on any failure."""
        try:
            self.sink.close()
        except (BrokenPipeError, OSError):
            pass
        for pr in self.procs:
            pr.p.wait()
        errs = [f"{pr.cmd[0]} exited {pr.p.returncode}: {pr.err()}" for pr in self.procs if pr.p.returncode]
        if errs:
            self.out.close()
            raise PipelineError("; ".join(errs))
        self.out.flush()
        os.fsync(self.out.fileno())
        self.out.close()

    def abort(self):
        for pr in reversed(self.procs):
            pr.terminate()
        for f in (getattr(self, "sink", None), self.out):
            try:
                f and f.close()
            except OSError:
                pass

    def errors(self):
        return "; ".join(f"{pr.cmd[0]}: {pr.err()}" for pr in self.procs if pr.p.poll() not in (None, 0))


# ---------------------------------------------------------------- read chain
class ReadChain:
    def __init__(self, path, fmt, enc, secret, settings):
        self.procs = []
        src = open(path, "rb")
        try:
            stream = src
            if enc:
                d = crypto_proc(enc, "decrypt", secret, src, subprocess.PIPE, settings)
                self.procs.append(d)
                stream = d.p.stdout
            dc = Proc(decomp_cmd(fmt), stdin=stream, stdout=subprocess.PIPE)
            self.procs.append(dc)
            if enc:
                d.p.stdout.close()
            self.stdout = dc.p.stdout
        except Exception:
            self.close(drained=False)
            raise
        finally:
            src.close()

    def drain(self):
        while self.stdout.read(1 << 20):
            pass

    def close(self, drained):
        if not drained:
            for pr in self.procs:
                pr.terminate(2)
        try:
            self.stdout.close()
        except Exception:
            pass
        for pr in self.procs:
            pr.p.wait()

    def check(self):
        errs = [f"{pr.cmd[0]} exited {pr.p.returncode}: {pr.err()}" for pr in self.procs if pr.p.returncode]
        if errs:
            raise PipelineError("; ".join(errs))


# ---------------------------------------------------------------- readers
@dataclass
class Member:
    name: str
    type: str  # file | dir | symlink | other
    size: int
    mode: int
    uid: int
    gid: int
    mtime: float
    linkname: Optional[str] = None
    open: Optional[Callable] = None

    def info(self):
        return {"name": self.name, "type": self.type, "size": self.size, "mode": self.mode,
                "uid": self.uid, "gid": self.gid, "mtime": self.mtime, "linkname": self.linkname}


class TarReader:
    def __init__(self, path, fmt, enc, secret, settings):
        self.chain = ReadChain(path, fmt, enc, secret, settings)
        self.drained = False

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        self.chain.close(drained=self.drained and et is None)
        if et is None and self.drained:
            self.chain.check()
        return False

    def members(self):
        try:
            tf = tarfile.open(fileobj=self.chain.stdout, mode="r|")
        except tarfile.TarError as e:
            self.chain.close(drained=False)
            self.chain.check()
            raise PipelineError(f"not a readable tar stream: {e}")
        n = 0
        try:
            for ti in tf:
                n += 1
                t = "dir" if ti.isdir() else "symlink" if ti.issym() else "file" if ti.isreg() else "other"
                m = Member(ti.name, t, ti.size if t == "file" else 0, ti.mode, ti.uid, ti.gid, ti.mtime,
                           ti.linkname if t == "symlink" else None)
                if t == "file":
                    m.open = (lambda ti=ti: tf.extractfile(ti))
                yield m
        except tarfile.TarError as e:
            self.chain.close(drained=False)
            self.chain.check()
            raise PipelineError(f"corrupt tar stream: {e}")
        self.chain.drain()
        self.drained = True
        self.chain.close(drained=True)
        self.chain.check()
        if n == 0:
            raise PipelineError("archive is empty")


class ZipReader:
    def __init__(self, path, secret):
        import pyzipper
        self.zf = pyzipper.AESZipFile(path)
        if secret:
            self.zf.setpassword(secret.encode())

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.zf.close()
        return False

    def find(self, name):
        """Direct central-directory lookup (no scan, no decryption needed to locate the entry)."""
        for cand in (name, name + "/"):
            try:
                return self._member(self.zf.getinfo(cand))
            except KeyError:
                continue
        return None

    def members(self):
        for zi in self.zf.infolist():
            yield self._member(zi)

    def _member(self, zi):
        mode = (zi.external_attr >> 16) & 0xFFFF
        name = zi.filename
        if name.endswith("/") or zi.is_dir():
            t = "dir"
        elif stat.S_ISLNK(mode):
            t = "symlink"
        else:
            t = "file"
        link = self.zf.read(zi).decode() if t == "symlink" else None
        import datetime
        try:
            mt = datetime.datetime(*zi.date_time).timestamp()
        except ValueError:
            mt = 0
        m = Member(name.rstrip("/"), t, zi.file_size if t == "file" else 0,
                   mode & 0o7777 or (0o755 if t == "dir" else 0o644), 0, 0, mt, link)
        if t == "file":
            m.open = (lambda zi=zi: self.zf.open(zi))
        return m


# ---------------------------------------------------------------- browse index (sidecar, tar formats)
def write_index(path, obj, enc, secret, settings):
    """gzip(JSON), encrypted with the archive's own tool/secret when the archive is encrypted. Atomic."""
    data = gzip.compress(json.dumps(obj, separators=(",", ":")).encode(), 6)
    part = path + ".part"
    try:
        with open(part, "wb") as out:
            if not enc:
                out.write(data)
            else:
                pr = crypto_proc(enc, "encrypt", secret, subprocess.PIPE, out, settings)
                try:
                    pr.p.stdin.write(data)
                    pr.p.stdin.close()
                except (BrokenPipeError, OSError):
                    pass
                pr.p.wait()
                if pr.p.returncode:
                    raise PipelineError(f"index encryption failed: {pr.err()}")
            out.flush()
            os.fsync(out.fileno())
        os.replace(part, path)
    finally:
        if os.path.exists(part):
            os.remove(part)


def read_index(path, enc, secret, settings):
    if not enc:
        with open(path, "rb") as f:
            data = f.read()
    else:
        with open(path, "rb") as src:
            pr = crypto_proc(enc, "decrypt", secret, src, subprocess.PIPE, settings)
            data = pr.p.stdout.read()
            pr.p.wait()
        if pr.p.returncode:
            raise PipelineError(f"index decryption failed: {pr.err()}")
    return json.loads(gzip.decompress(data))


def open_reader(path, fmt, enc, secret, settings):
    if fmt == "zip":
        return ZipReader(path, secret if enc else None)
    return TarReader(path, fmt, enc, secret, settings)


# ---------------------------------------------------------------- verification
def verify_archive(path, fmt, enc, secret, settings, expected_entries=None):
    """Return (ok: bool, detail: str). tar: `tar -tf -` on the (decrypted, decompressed) stream.
    zip: pyzipper read-back with CRC/HMAC checks."""
    if fmt == "zip":
        try:
            import pyzipper
            with pyzipper.AESZipFile(path) as zf:
                if secret:
                    zf.setpassword(secret.encode())
                bad = zf.testzip()
                n = len(zf.infolist())
            if bad:
                return False, f"corrupt member: {bad}"
            if expected_entries is not None and n != expected_entries:
                return False, f"entry count {n} != expected {expected_entries}"
            return True, f"{n} entries read back"
        except Exception as e:
            return False, redact(f"zip read-back failed: {type(e).__name__}: {e}")
    chain = ReadChain(path, fmt, enc, secret, settings)
    tar = Proc(["tar", "-tf", "-"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    count = {"n": 0, "manifest": False}

    def count_lines():
        for line in iter(tar.p.stdout.readline, b""):
            count["n"] += 1
            if line.strip() == b".bunnysave/manifest.json":
                count["manifest"] = True
    t = threading.Thread(target=count_lines, daemon=True)
    t.start()
    tar_alive = True
    try:
        for chunk in iter(lambda: chain.stdout.read(1 << 20), b""):
            if tar_alive:
                try:
                    tar.p.stdin.write(chunk)
                except (BrokenPipeError, OSError):
                    tar_alive = False  # tar stopped at end-of-archive marker; keep draining for CRC
        try:
            tar.p.stdin.close()
        except OSError:
            pass
        tar.p.wait()
        t.join(5)
        chain.close(drained=True)
        try:
            chain.check()
        except PipelineError as e:
            return False, str(e)
        if tar.p.returncode:
            return False, f"tar -tf failed: {tar.err()}"
        if not count["manifest"]:
            return False, "manifest missing from archive"
        if expected_entries is not None and count["n"] != expected_entries:
            return False, f"entry count {count['n']} != expected {expected_entries}"
        return True, f"tar -tf ok, {count['n']} entries"
    except Exception as e:
        chain.close(drained=False)
        tar.terminate(1)
        return False, redact(f"verification error: {type(e).__name__}: {e}")
