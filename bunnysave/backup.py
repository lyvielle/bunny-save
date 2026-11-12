"""Backup job: hooks -> scan -> space check -> write (.part, fsync, rename) -> sha256 -> verify -> retention."""
import io
import json
import logging
import os
import pwd
import grp
import shutil
import stat
import tarfile
import time
import uuid
import zipfile
from datetime import datetime

from . import VERSION
from .archive_io import FMT_EXT, PipelineError, WriteChain, verify_archive, write_index
from .browse import EMBED_FILE_MAX, EMBED_TOTAL_MAX, is_text_name
from .hooks import run_command
from .manifest import MANIFEST_PATH, build_manifest, dumps
from .redact import redact
from .retention import select_for_deletion
from .secretstore import SecretError, resolve_archive_secret, resolve_sftp_secrets
from .sources import gather, open_fs
from .util import fsync_dir, hostname, iso, parse_iso, sha256_file, slug, utcnow

log = logging.getLogger("bunnysave.backup")
SAFETY_MARGIN = 0.10
MIN_MARGIN = 64 * 1024 * 1024


class Cancelled(Exception):
    pass


class CountingReader:
    """Reads exactly `size` bytes (pads with zeros if the file shrank), reports progress, honours cancel."""

    def __init__(self, f, size, job):
        self.f, self.remaining, self.job, self.short = f, size, job, False

    def read(self, n=-1):
        n = self.remaining if n is None or n < 0 else min(n, self.remaining)
        if n <= 0:
            return b""
        self.job.check_cancel()
        buf = bytearray()
        while len(buf) < n and not self.short:
            chunk = self.f.read(n - len(buf))
            if not chunk:
                self.short = True
                break
            buf += chunk
        if len(buf) < n:
            buf += b"\0" * (n - len(buf))
        self.remaining -= len(buf)
        self.job.done_bytes += len(buf)
        return bytes(buf)


def _names(uid, gid):
    try:
        u = pwd.getpwuid(uid).pw_name
    except KeyError:
        u = ""
    try:
        g = grp.getgrgid(gid).gr_name
    except KeyError:
        g = ""
    return u, g


def _tarinfo(e, preserve, local):
    ti = tarfile.TarInfo(e.arcname)
    ti.mtime = int(e.mtime)
    ti.type = {"dir": tarfile.DIRTYPE, "symlink": tarfile.SYMTYPE, "file": tarfile.REGTYPE}[e.kind]
    if preserve:
        ti.mode, ti.uid, ti.gid = e.mode, e.uid, e.gid
        if local:
            ti.uname, ti.gname = _names(e.uid, e.gid)
    else:
        ti.mode = 0o755 if e.kind == "dir" else 0o777 if e.kind == "symlink" else 0o644
        ti.uid = ti.gid = 0
    if e.kind == "file":
        ti.size = e.size
    if e.kind == "symlink":
        ti.linkname = e.linkname
    return ti


class _Tee:
    def __init__(self, rd):
        self.rd, self.buf = rd, bytearray()

    def read(self, n=-1):
        d = self.rd.read(n)
        self.buf += d
        return d


def write_tar(chain, entries, manifest_bytes, preserve, fsmap, job, idx=None):
    """idx (optional dict) is filled with the browse index: entries, small text previews, binary-looking names."""
    tf = tarfile.open(fileobj=chain.sink, mode="w|", format=tarfile.PAX_FORMAT)
    try:
        _write_tar(tf, entries, manifest_bytes, preserve, fsmap, job, idx)
    except BaseException:
        tf.closed = True  # avoid tarfile flushing into the aborted pipe on GC
        tf.fileobj.closed = True
        raise


def _write_tar(tf, entries, manifest_bytes, preserve, fsmap, job, idx=None):
    used = 0
    mi = tarfile.TarInfo(MANIFEST_PATH)
    mi.size, mi.mtime, mi.mode = len(manifest_bytes), int(time.time()), 0o600
    tf.addfile(mi, io.BytesIO(manifest_bytes))
    for e in entries:
        job.check_cancel()
        job.current = e.arcname
        fs = fsmap[e.src_id]
        ti = _tarinfo(e, preserve, fs.label == "local")
        if e.kind == "file":
            try:
                f = fs.open(e.path)
            except (OSError, IOError) as ex:
                job.warn(f"skipped unreadable file {e.path}: {ex}")
                job.done_bytes += e.size
                continue
            try:
                rd = CountingReader(f, e.size, job)
                keep = idx is not None and e.size <= EMBED_FILE_MAX and used < EMBED_TOTAL_MAX and is_text_name(e.arcname)
                src = _Tee(rd) if keep else rd
                tf.addfile(ti, src)
                if rd.short:
                    job.warn(f"file shrank while reading, zero-padded: {e.path}")
                if keep:
                    data = bytes(src.buf)
                    if rd.short or b"\0" in data[:8192]:
                        idx["binary"].append(ti.name.lstrip("/"))
                    else:
                        idx["previews"][ti.name.lstrip("/")] = data.decode("utf-8", "replace")
                        used += len(data)
            finally:
                f.close()
        else:
            tf.addfile(ti)
        if idx is not None:
            kind = "dir" if ti.isdir() else "symlink" if ti.issym() else "file"
            idx["entries"].append({"name": ti.name.rstrip("/"), "type": kind, "size": ti.size if kind == "file" else 0,
                                   "mode": ti.mode, "uid": ti.uid, "gid": ti.gid, "mtime": ti.mtime,
                                   "linkname": ti.linkname if kind == "symlink" else None})
        job.files_done += 1
    tf.close()


def write_zip(part, entries, manifest_bytes, preserve, fsmap, job, fmt_level, secret):
    import pyzipper
    zf = pyzipper.AESZipFile(part, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=fmt_level)
    if secret:
        zf.setpassword(secret.encode())
        zf.setencryption(pyzipper.WZ_AES, nbits=256)  # AES-256 only, never ZipCrypto

    def zinfo(name, mtime, mode, kind):
        t = time.localtime(max(mtime, 315532800))
        zi = zipfile.ZipInfo(name, date_time=t[:6])
        zi.compress_type = zipfile.ZIP_DEFLATED
        try:
            zi._compresslevel = fmt_level
        except Exception:
            pass
        ifmt = {"dir": stat.S_IFDIR, "symlink": stat.S_IFLNK, "file": stat.S_IFREG}[kind]
        zi.external_attr = ((ifmt | mode) & 0xFFFF) << 16 | (0x10 if kind == "dir" else 0)
        zi.create_system = 3
        return zi
    try:
        zf.writestr(zinfo(MANIFEST_PATH, time.time(), 0o600, "file"), manifest_bytes)
        for e in entries:
            job.check_cancel()
            job.current = e.arcname
            mode = e.mode if preserve else (0o755 if e.kind == "dir" else 0o644)
            if e.kind == "dir":
                zf.writestr(zinfo(e.arcname + "/", e.mtime, mode, "dir"), b"")
            elif e.kind == "symlink":
                zf.writestr(zinfo(e.arcname, e.mtime, 0o777, "symlink"), e.linkname.encode())
            else:
                try:
                    f = fsmap[e.src_id].open(e.path)
                except (OSError, IOError) as ex:
                    job.warn(f"skipped unreadable file {e.path}: {ex}")
                    job.done_bytes += e.size
                    continue
                try:
                    rd = CountingReader(f, e.size, job)
                    with zf.open(zinfo(e.arcname, e.mtime, mode, "file"), "w", force_zip64=True) as dest:
                        while chunk := rd.read(1 << 20):
                            dest.write(chunk)
                finally:
                    f.close()
            job.files_done += 1
    finally:
        zf.close()
    with open(part, "rb+") as fh:
        os.fsync(fh.fileno())


def apply_retention(settings, db, setup_id, policy, job):
    ok = [b for b in db.list_backups(setup_id) if b["status"] == "ok"]
    doomed = select_for_deletion([(b["id"], parse_iso(b["created"])) for b in ok], policy, utcnow())
    for b in ok:
        if b["id"] in doomed:
            delete_backup_files(b)
            db.delete_backup(b["id"])
            job.log(f"retention: deleted {b['filename']}")


def delete_backup_files(b):
    for p in (b["path"], b["path"] + ".json", b["path"] + ".idx"):
        try:
            os.remove(p)
        except FileNotFoundError:
            pass


def run_backup(settings, db, job, setup, supplied):
    """supplied = {"archive_password": str|None, "sftp": {source_id: {password, key_passphrase}}}"""
    cfg = setup["config"]
    fmt, enc, level = cfg["format"], cfg["encryption"], cfg["level"]
    sid, ref = setup["id"], cfg["secret_ref"]
    bid = uuid.uuid4().hex[:12]
    stamp = utcnow()
    target_dir = cfg.get("target_dir") or str(settings.backups_dir)
    os.makedirs(target_dir, exist_ok=True)
    secret = resolve_archive_secret(settings, fmt, enc, ref, supplied.get("archive_password"))
    job.register_secret(secret)
    tool_ext = ""
    if enc.get("enabled") and fmt != "zip":
        tool_ext = ".gpg" if enc["tool"] == "gpg" else ".age"
    fname = f"{slug(cfg['name'])}-{stamp.strftime('%Y%m%dT%H%M%SZ')}{FMT_EXT[fmt]}{tool_ext}"
    final = os.path.join(target_dir, fname)
    part = final + ".part"
    env = {"BUNNYSAVE_JOB_ID": job.id, "BUNNYSAVE_ARCHIVE": final,
           "BUNNYSAVE_SOURCE": ",".join(f"sftp://{s['username']}@{s['host']}" if s["type"] == "sftp" else s["type"]
                                       for s in cfg["sources"])}

    def hook(which):
        h = cfg["hooks"].get(which) or {}
        if not h.get("command"):
            return None
        job.phase = f"{which}-hook"
        r = run_command(h["command"], h["timeout"], env)
        job.hooks.append({"which": which, **r})
        job.log(f"{which} hook exit={r['exit_code']}{' (timeout)' if r['timed_out'] else ''}")
        return r

    fsmap, backup_id_done = {}, None
    status, err = "ok", None
    try:
        r = hook("pre")
        if r and (r["exit_code"] != 0 or r["timed_out"]):
            raise RuntimeError("pre-backup hook failed; aborting")

        # ---- scan
        job.phase = "scanning"
        entries = []
        for src in cfg["sources"]:
            job.check_cancel()
            pw, kp = (None, None)
            if src["type"] == "sftp":
                pw, kp = resolve_sftp_secrets(src, (supplied.get("sftp") or {}).get(src["id"]))
                job.register_secret(pw)
                job.register_secret(kp)
            job.log(f"scanning source {src['id']} ({src['type']})")
            fs = open_fs(src, settings, pw, kp)
            fsmap[src["id"]] = fs
            base, last = len(entries), [time.time()]

            def tick(n, path, base=base, last=last):
                job.check_cancel()  # makes Cancel work during the scan
                job.files_total = base + n
                job.current = path
                if time.time() - last[0] > 10:
                    last[0] = time.time()
                    job.log(f"scanning... {base + n} entries so far, now in {path}")
            entries += gather(fs, src, job.warn, tick)
        if not entries:
            raise RuntimeError("nothing matched the include patterns")
        total = sum(e.size for e in entries)
        job.total_bytes, job.files_total, job.done_bytes, job.files_done = total, len(entries), 0, 0

        # ---- free space
        est = int(total * cfg.get("space_ratio", 1.0))
        need = est + max(int(est * SAFETY_MARGIN), MIN_MARGIN)
        free = shutil.disk_usage(target_dir).free
        job.log(f"{len(entries)} entries, {total} bytes; need ~{need}, free {free}")
        if free < need:
            raise RuntimeError(f"insufficient free space on target ({free} free, ~{need} required)")

        skel = [e.path for e in entries if e.skeleton]
        manifest = build_manifest(cfg["name"], iso(stamp), hostname(), cfg["sources"],
                                  cfg["preserve_permissions"], cfg["post_restore"], fmt, skel,
                                  {"entries": len(entries), "total_bytes": total})
        mbytes = dumps(manifest)

        # ---- write
        job.phase = "writing"
        idx = {"entries": [], "previews": {}, "binary": []}
        if fmt == "zip":
            write_zip(part, entries, mbytes, cfg["preserve_permissions"], fsmap, job, level, secret if enc.get("enabled") else None)
        else:
            chain = WriteChain(fmt, level, enc if enc.get("enabled") else None, secret, part, settings)
            try:
                write_tar(chain, entries, mbytes, cfg["preserve_permissions"], fsmap, job, idx)
                chain.finish()
            except BrokenPipeError:
                chain.abort()
                raise PipelineError(chain.errors() or "pipeline closed unexpectedly")
            except BaseException:
                chain.abort()
                raise
        job.phase = "finalizing"
        os.replace(part, final)
        fsync_dir(target_dir)
        size = os.path.getsize(final)
        job.phase = "hashing"
        digest = sha256_file(final)
        job.log(f"sha256 {digest}")

        # ---- verify
        job.phase = "verifying"
        vok, vdetail = verify_archive(final, fmt, enc if enc.get("enabled") and fmt != "zip" else None, secret,
                                      settings, expected_entries=job.files_done + 1)
        job.log(f"verification: {'ok' if vok else 'FAILED'} - {vdetail}")
        if not vok:
            status, err = "failed", f"verification failed: {vdetail}"
        elif fmt != "zip":  # zip's central directory is already a fast index
            try:
                write_index(final + ".idx", {"v": 1, "archive_sha256": digest, "manifest": manifest, "entries": idx["entries"],
                                             "previews": idx["previews"], "binary": idx["binary"]},
                            enc if enc.get("enabled") else None, secret, settings)
                job.log(f"browse index written ({len(idx['entries'])} entries)")
            except Exception as ex:
                job.log(f"browse index skipped: {redact(str(ex))}")
        rec = {"id": bid, "setup_id": sid, "setup_name": cfg["name"], "filename": fname, "path": final,
               "created": iso(stamp), "size": size, "fmt": fmt, "encrypted": int(bool(enc.get("enabled"))),
               "enc": {k: v for k, v in enc.items() if k != "password"}, "sha256": digest,
               "verify_status": "ok" if vok else "failed", "status": status, "error": err,
               "secret_ref": ref, "manifest": {k: manifest[k] for k in ("name", "timestamp", "stats", "preserve_permissions")}}
        db.add_backup(rec)
        with open(final + ".json", "w") as f:
            json.dump({k: v for k, v in rec.items() if k not in ("path",)}, f, indent=1)
        job.result = {"backup_id": bid, "sha256": digest, "size": size, "verify": vdetail}
        backup_id_done = bid
        if status == "ok":
            apply_retention(settings, db, sid, cfg["retention"], job)
    except Cancelled:
        status = "cancelled"
        err = "cancelled by user"
    except Exception as e:
        status, err = "failed", redact(f"{type(e).__name__}: {e}")
        log.exception("backup failed", extra={"job_id": job.id, "setup_id": sid})
    finally:
        for fs in fsmap.values():
            fs.close()
        if os.path.exists(part):
            try:
                os.remove(part)  # partial output never survives
            except OSError:
                pass
    env["BUNNYSAVE_STATUS"] = status
    if status != "cancelled":
        try:
            hook("post")
        except Exception as e:
            job.log(f"post hook error: {redact(str(e))}")
    if status == "failed":
        raise RuntimeError(err)
    if status == "cancelled":
        raise Cancelled()
