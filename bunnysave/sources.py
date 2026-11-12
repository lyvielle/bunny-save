"""Source filesystems (local / SFTP), glob expansion, exclusion and entry gathering."""
import fnmatch
import glob as _glob
import os
import posixpath
import stat
from dataclasses import dataclass
from typing import Optional

MAGIC = set("*?[")


def has_magic(p):
    return any(c in p for c in MAGIC)


@dataclass
class Entry:
    arcname: str
    path: str
    kind: str  # file | dir | symlink
    size: int
    mode: int
    uid: int
    gid: int
    mtime: float
    src_id: str = ""
    linkname: Optional[str] = None
    skeleton: bool = False


class LocalFs:
    label = "local"

    def glob(self, pattern):
        if not has_magic(pattern):
            return [pattern] if os.path.lexists(pattern) else []
        return sorted(_glob.glob(pattern, recursive=True, include_hidden=True))

    def lstat(self, p):
        return os.lstat(p)

    def listdir(self, p):
        with os.scandir(p) as it:
            return sorted(e.name for e in it)

    def scandir(self, p):
        """[(name, stat_result)] without extra per-entry round trips."""
        out = []
        with os.scandir(p) as it:
            for e in it:
                try:
                    out.append((e.name, e.stat(follow_symlinks=False)))
                except OSError:
                    out.append((e.name, None))
        return sorted(out, key=lambda x: x[0])

    def open(self, p):
        return open(p, "rb")

    def readlink(self, p):
        return os.readlink(p)

    def close(self):
        pass


def _none_auth_client():
    import paramiko

    class NoneAuthClient(paramiko.SSHClient):
        """Tailscale SSH: the server authenticates the tailnet identity and accepts SSH 'none' auth."""
        def _auth(self, username, *a, **k):
            self._transport.auth_none(username)
    return NoneAuthClient()


class HostFs(LocalFs):
    """Host filesystem mounted into the container (e.g. `/:/hostfs:ro`). Users and archives see HOST paths."""
    label = "host"

    def __init__(self, root):
        self.root = str(root).rstrip("/")

    def _t(self, p):
        return self.root + "/" + p.lstrip("/")

    def glob(self, pattern):
        t = self._t(pattern)
        if not has_magic(pattern):
            return [pattern] if os.path.lexists(t) else []
        n = len(self.root)
        return sorted((g[n:] or "/") for g in _glob.glob(t, recursive=True, include_hidden=True))

    def lstat(self, p):
        return os.lstat(self._t(p))

    def listdir(self, p):
        return super().listdir(self._t(p))

    def scandir(self, p):
        return super().scandir(self._t(p))

    def open(self, p):
        return open(self._t(p), "rb")

    def readlink(self, p):
        return os.readlink(self._t(p))


class SftpFs:
    def __init__(self, src, password, key_passphrase, known_hosts):
        import paramiko  # lazy: only needed for SFTP sources
        self.label = f"sftp://{src['username']}@{src['host']}"
        self.client = _none_auth_client() if src.get("auth") == "tailscale" else paramiko.SSHClient()
        if os.path.exists(known_hosts):
            self.client.load_host_keys(str(known_hosts))
        # Trust-on-first-use: unknown hosts are remembered, *changed* keys are rejected.
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kw = dict(hostname=src["host"], port=src.get("port", 22), username=src["username"],
                  timeout=20, banner_timeout=20, auth_timeout=20, allow_agent=False, look_for_keys=False)
        if src.get("auth") == "key":
            kw["key_filename"] = src.get("key_path") or None
            kw["passphrase"] = key_passphrase
        else:
            kw["password"] = password
        self.client.connect(**kw)
        self.client.save_host_keys(str(known_hosts))
        self.sftp = self.client.open_sftp()
        self.sftp.get_channel().settimeout(45)

    def glob(self, pattern):
        if not has_magic(pattern):
            try:
                self.sftp.lstat(pattern)
                return [pattern]
            except IOError:
                return []
        cur = ["/"]
        for seg in [s for s in pattern.split("/") if s]:
            nxt = []
            for base in cur:
                if has_magic(seg):
                    try:
                        names = [a.filename for a in self.sftp.listdir_attr(base)]
                    except IOError:
                        continue
                    nxt += [posixpath.join(base, n) for n in sorted(fnmatch.filter(names, seg.replace("**", "*")))]
                else:
                    p = posixpath.join(base, seg)
                    try:
                        self.sftp.lstat(p)
                        nxt.append(p)
                    except IOError:
                        pass
            cur = nxt
        return cur

    def lstat(self, p):
        return self.sftp.lstat(p)

    def listdir(self, p):
        return sorted(a.filename for a in self.sftp.listdir_attr(p))

    def scandir(self, p):
        """One SFTP READDIR gives names *and* attributes: no per-file lstat round trips."""
        return sorted(((a.filename, a) for a in self.sftp.listdir_attr(p)), key=lambda x: x[0])

    def open(self, p):
        f = self.sftp.open(p, "rb")
        try:
            f.prefetch()
        except Exception:
            pass
        return f

    def readlink(self, p):
        return self.sftp.readlink(p)

    def close(self):
        try:
            self.sftp.close()
            self.client.close()
        except Exception:
            pass


def open_fs(src, settings, password=None, key_passphrase=None):
    if src["type"] == "local":
        return LocalFs()
    if src["type"] == "host":
        if not settings.host_available():
            raise RuntimeError(f"host filesystem not mounted at {settings.host_root} (see docker-compose.yml)")
        return HostFs(settings.host_root)
    return SftpFs(src, password, key_passphrase, settings.known_hosts)


def is_excluded(path, patterns):
    base = posixpath.basename(path)
    for pat in patterns:
        if "/" in pat:
            if fnmatch.fnmatch(path, pat) or path == pat.rstrip("/") or path.startswith(pat.rstrip("/") + "/"):
                return True
        elif fnmatch.fnmatch(base, pat):
            return True
    return False


def arcname_for(src, path):
    rel = posixpath.normpath(path).lstrip("/")
    return rel if src["type"] != "sftp" else f"sftp/{src['id']}/{rel}"


def _entry(fs, src, path, st, skeleton=False):
    m = st.st_mode
    if stat.S_ISDIR(m):
        kind, link = "dir", None
    elif stat.S_ISLNK(m):
        kind, link = "symlink", fs.readlink(path)
    elif stat.S_ISREG(m):
        kind, link = "file", None
    else:
        return None  # sockets, fifos, devices
    return Entry(arcname_for(src, path), path, kind, st.st_size if kind == "file" else 0,
                 stat.S_IMODE(m), st.st_uid or 0, st.st_gid or 0, st.st_mtime or 0, src["id"], link, skeleton)


def gather(fs, src, warn, progress=None):
    """Return entries for one source. Skeleton includes yield only the directory itself.
    progress(count, path) is called per entry (it may raise to cancel)."""
    out, seen = [], set()
    excl = src.get("excludes", [])

    def add(path, skeleton=False, st=None):
        if path in seen:
            return None
        seen.add(path)
        try:
            st = st or fs.lstat(path)
            e = _entry(fs, src, path, st, skeleton)
        except (OSError, IOError) as ex:
            warn(f"skipped {path}: {ex}")
            return None
        if e is None:
            warn(f"skipped special file {path}")
            return None
        out.append(e)
        if progress:
            progress(len(out), path)
        return e

    for inc in src["includes"]:
        for root in fs.glob(inc["path"]):
            if progress:
                progress(len(out), root)
            if is_excluded(root, excl):
                continue
            e = add(root, skeleton=inc.get("skeleton", False))
            if e is None or e.kind != "dir" or inc.get("skeleton"):
                continue
            stack = [root]
            while stack:
                d = stack.pop()
                if progress:
                    progress(len(out), d)
                try:
                    items = fs.scandir(d)
                except (OSError, IOError) as ex:
                    warn(f"cannot list {d}: {ex}")
                    continue
                subdirs = []
                for n, st in items:
                    p = posixpath.join(d, n)
                    if is_excluded(p, excl):
                        continue
                    ce = add(p, st=st)
                    if ce and ce.kind == "dir":
                        subdirs.append(p)
                stack.extend(reversed(subdirs))
    return out
