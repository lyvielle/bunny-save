"""Restore planning + execution. Targets: local dir (or /) and SFTP (origin restore of SFTP sources)."""
import json
import logging
import os
import posixpath
import shutil
import stat
import time
from collections import Counter

from .archive_io import open_reader
from .backup import Cancelled
from .conflict import decide_conflict, rename_target
from .hooks import run_command
from .manifest import MANIFEST_PATH
from .redact import redact
from .secretstore import resolve_archive_secret, resolve_sftp_secrets
from .sources import SftpFs, open_fs

log = logging.getLogger("bunnysave.restore")
MAX_PLAN_ROWS = 2000


class UnsafePath(ValueError):
    pass


def clean_rel(name):
    rel = posixpath.normpath(name).lstrip("/")
    if rel in ("", ".") or rel == ".." or rel.startswith("../") or "/../" in rel:
        raise UnsafePath(name)
    return rel


class LocalTarget:
    def __init__(self, root):
        self.root = root
        self.real_root = os.path.realpath(root)
        self.chown_failed = False

    def dest(self, rel):
        d = os.path.join(self.root, clean_rel(rel))
        if self.real_root != "/":
            rp = os.path.realpath(os.path.dirname(d))
            if not (rp == self.real_root or rp.startswith(self.real_root + os.sep)):
                raise UnsafePath(f"{rel} escapes target via symlink")
        return d

    def stat(self, p):  # None = missing, True = dir, False = other
        try:
            return stat.S_ISDIR(os.lstat(p).st_mode)
        except FileNotFoundError:
            return None

    def mkdirs(self, p):
        os.makedirs(p, exist_ok=True)

    def rename(self, a, b):
        os.rename(a, b)

    def remove(self, p):
        os.remove(p)

    def write(self, p, fobj, job):
        self.mkdirs(os.path.dirname(p))
        tmp = p + ".bunnysave-tmp"
        try:
            with open(tmp, "wb") as out:
                while chunk := fobj.read(1 << 20):
                    job.check_cancel()
                    out.write(chunk)
                    job.done_bytes += len(chunk)
            os.replace(tmp, p)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def symlink(self, link, p):
        self.mkdirs(os.path.dirname(p))
        os.symlink(link, p)

    def meta(self, p, m, preserve, is_link=False):
        try:
            if preserve:
                try:
                    os.chown(p, m.uid, m.gid, follow_symlinks=False)
                except (PermissionError, OSError):
                    self.chown_failed = True
                if not is_link:
                    os.chmod(p, m.mode & 0o7777)
            if not is_link and m.mtime:
                os.utime(p, (m.mtime, m.mtime))
        except OSError:
            pass

    def close(self):
        pass

    def exists(self, p):
        return os.path.lexists(p)


class SftpTarget:
    def __init__(self, fs: SftpFs, root="/"):
        self.fs, self.sftp = fs, fs.sftp
        self.root = "/" + (root or "/").strip("/")
        self.chown_failed = False

    def dest(self, rel):
        return posixpath.join(self.root, clean_rel(rel))

    def stat(self, p):
        try:
            return stat.S_ISDIR(self.sftp.lstat(p).st_mode)
        except IOError:
            return None

    def exists(self, p):
        return self.stat(p) is not None

    def mkdirs(self, p):
        parts, cur = [x for x in p.split("/") if x], ""
        for part in parts:
            cur += "/" + part
            if self.stat(cur) is None:
                self.sftp.mkdir(cur)

    def rename(self, a, b):
        self.sftp.posix_rename(a, b)

    def write(self, p, fobj, job):
        self.mkdirs(posixpath.dirname(p))
        tmp = p + ".bunnysave-tmp"
        with self.sftp.open(tmp, "wb") as out:
            while chunk := fobj.read(1 << 20):
                job.check_cancel()
                out.write(chunk)
                job.done_bytes += len(chunk)
        self.sftp.posix_rename(tmp, p)

    def symlink(self, link, p):
        self.mkdirs(posixpath.dirname(p))
        self.sftp.symlink(link, p)

    def remove(self, p):
        self.sftp.remove(p)

    def meta(self, p, m, preserve, is_link=False):
        try:
            if preserve:
                try:
                    self.sftp.chown(p, m.uid, m.gid)
                except IOError:
                    self.chown_failed = True
                if not is_link:
                    self.sftp.chmod(p, m.mode & 0o7777)
            if not is_link and m.mtime:
                self.sftp.utime(p, (m.mtime, m.mtime))
        except IOError:
            pass

    def close(self):
        self.fs.close()


def run_restore(settings, db, job, backup, params, supplied):
    """params: mode (origin|local|sftp), target (local dir), start (archive sub-path to restore from),
    dest (SFTP destination), conflict, selection[list], apply(bool), post_restore{enabled,confirm,indices}.
    Returns plan dict. When apply is False nothing is written."""
    apply = bool(params.get("apply"))
    policy = params.get("conflict", "skip")
    target_root = (params.get("target") or "/").strip() or "/"
    mode = params.get("mode") or ("origin" if target_root == "/" else "local")
    if mode not in ("origin", "local", "sftp"):
        raise ValueError(f"unknown restore mode {mode!r}")
    start = clean_rel(params["start"]) if (params.get("start") or "").strip("/ ") else ""
    dest_cfg = params.get("dest") or {}
    if mode == "sftp" and not (dest_cfg.get("host") and dest_cfg.get("username")):
        raise ValueError("SFTP destination needs host and username")
    selection = [clean_rel(s) for s in params.get("selection") or []]
    enc = backup["enc"] if backup["encrypted"] else None
    secret = resolve_archive_secret(settings, backup["fmt"], backup["enc"], backup["secret_ref"],
                                    supplied.get("archive_password")) if enc else None
    job.register_secret(secret)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    counts, rows, warnings = Counter(), [], []
    targets, dir_meta = {}, []
    manifest = None

    def sftp_target(sid, manifest):
        if sid not in targets:
            src = next(s for s in manifest["sources"] if s["id"] == sid)
            pw, kp = resolve_sftp_secrets(src, (supplied.get("sftp") or {}).get(sid))
            job.register_secret(pw)
            job.register_secret(kp)
            targets[sid] = SftpTarget(open_fs(src, settings, pw, kp))
        return targets[sid]

    def sftp_dest_target():
        if "dest" not in targets:
            src = {"type": "sftp", "host": dest_cfg["host"].strip(), "port": int(dest_cfg.get("port") or 22),
                   "username": dest_cfg["username"].strip(), "auth": dest_cfg.get("auth", "password"),
                   "key_path": dest_cfg.get("key_path", ""), "secret_mode": "prompt"}
            pw, kp = resolve_sftp_secrets(src, supplied.get("dest"))
            job.register_secret(pw)
            job.register_secret(kp)
            targets["dest"] = SftpTarget(open_fs(src, settings, pw, kp), dest_cfg.get("path") or "/")
        return targets["dest"]

    def route(name):
        """-> (target, relative path below the target root, label) or None to skip."""
        if mode == "origin":
            if manifest and name.startswith("sftp/"):
                parts = name.split("/", 2)
                if len(parts) == 3 and any(s["id"] == parts[1] and s["type"] == "sftp" for s in manifest["sources"]):
                    return sftp_target(parts[1], manifest), parts[2], f"sftp:{parts[1]}"
            if "local" not in targets:
                host = any(s["type"] == "host" for s in manifest["sources"])
                targets["local"] = LocalTarget(str(settings.host_root) if host else "/")
            return targets["local"], name, "local"
        rel = name
        if start:
            if rel == start or not rel.startswith(start + "/"):
                return None
            rel = rel[len(start) + 1:]
        if mode == "sftp":
            return sftp_dest_target(), rel, "sftp"
        if "local" not in targets:
            if apply:
                os.makedirs(target_root, exist_ok=True)
            targets["local"] = LocalTarget(target_root)
        return targets["local"], rel, "local"

    fmt = backup["fmt"]
    try:
        with open_reader(backup["path"], fmt, backup["enc"] if backup["encrypted"] else None, secret, settings) as rd:
            it = rd.members()
            first = next(it)
            if first.name != MANIFEST_PATH:
                raise ValueError("manifest missing or not first member")
            manifest = json.loads(first.open().read())
            preserve = bool(manifest.get("preserve_permissions"))
            skeleton = {posixpath.normpath(p).lstrip("/") for p in manifest.get("skeleton", [])}
            if apply:
                job.phase = "restoring"
                job.total_bytes = (manifest.get("stats") or {}).get("total_bytes", 0)
                job.files_total = (manifest.get("stats") or {}).get("entries", 0)
            else:
                job.phase = "planning"
            for m in it:
                job.check_cancel()
                if m.name.startswith(".bunnysave/") or m.type == "other":
                    continue
                try:
                    rel = clean_rel(m.name)
                except UnsafePath:
                    warnings.append(f"refused unsafe path {m.name!r}")
                    continue
                if selection and not any(rel == s or rel.startswith(s + "/") for s in selection):
                    continue
                routed = route(rel)
                if routed is None:
                    continue
                tgt, trel, tname = routed
                job.current = rel
                try:
                    dest = tgt.dest(trel)
                except UnsafePath as e:
                    warnings.append(str(e))
                    continue
                st = tgt.stat(dest)
                action = decide_conflict(policy, st is not None, bool(st), m.type == "dir")
                counts[action] += 1
                if len(rows) < MAX_PLAN_ROWS:
                    rows.append({"path": rel, "dest": (f"{tname}:" if tname != "local" else "") + dest, "type": m.type,
                                 "size": m.size, "action": action, "skeleton": rel in skeleton})
                if not apply:
                    continue
                if action == "skip":
                    continue
                if action == "rename_then_create":
                    tgt.rename(dest, rename_target(dest, stamp, tgt.exists))
                if m.type == "dir":
                    tgt.mkdirs(dest)
                    dir_meta.append((tgt, dest, m))  # applied after children (reverse order)
                    continue
                if m.type == "symlink":
                    if action == "overwrite" and tgt.exists(dest):
                        tgt.remove(dest)
                    tgt.symlink(m.linkname, dest)
                    tgt.meta(dest, m, preserve, is_link=True)
                else:
                    f = m.open()
                    tgt.write(dest, f, job)
                    tgt.meta(dest, m, preserve)
                job.files_done += 1
            for tgt, dest, m in reversed(dir_meta):
                tgt.meta(dest, m, preserve)
        if any(getattr(t, "chown_failed", False) for t in targets.values()):
            warnings.append("could not change ownership for some entries (needs root); modes were applied")
    finally:
        for t in targets.values():
            t.close()
    for w in warnings:
        job.warn(w)
    is_host = bool(manifest and any(s["type"] == "host" for s in manifest["sources"]))
    desc = {"origin": "original locations" + (" (host filesystem)" if is_host else ""), "local": target_root,
            "sftp": f"sftp://{dest_cfg.get('username')}@{dest_cfg.get('host')}{dest_cfg.get('path') or '/'}"}[mode]
    plan = {"applied": apply, "target": desc, "mode": mode, "start": start, "conflict": policy, "summary": dict(counts),
            "rows": rows, "truncated": sum(counts.values()) > len(rows), "warnings": warnings,
            "post_restore_commands": (manifest or {}).get("post_restore_commands", [])}

    # ---- post-restore commands: disabled by default, require explicit confirmation
    pr = params.get("post_restore") or {}
    if apply and pr.get("enabled"):
        if pr.get("confirm") != "RUN":
            raise ValueError("post-restore commands not confirmed; nothing executed")
        cmds = manifest.get("post_restore_commands", [])
        env = {"BUNNYSAVE_JOB_ID": job.id, "BUNNYSAVE_ARCHIVE": backup["path"], "BUNNYSAVE_SOURCE": desc}
        job.phase = "post-restore"
        for i in pr.get("indices", []):
            if 0 <= i < len(cmds):
                r = run_command(cmds[i]["command"], cmds[i].get("timeout", 300), env,
                                cwd=target_root if mode == "local" and os.path.isdir(target_root) else None)
                job.hooks.append({"which": "post-restore", **r})
                job.log(f"post-restore #{i} exit={r['exit_code']}")
    job.result = plan
    return plan
