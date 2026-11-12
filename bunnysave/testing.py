"""'Test validity' for a source: connect, expand each include, estimate size within a time budget."""
import stat
import time

from . import redact
from .secretstore import resolve_sftp_secrets
from .sources import is_excluded, open_fs

PER_ITEM_SECONDS = 4.0
TOTAL_SECONDS = 120.0
MAX_ENTRIES = 200_000


def test_source(src, settings, supplied):
    res = {"connected": False, "error": None, "items": []}
    fs = None
    secrets = []
    try:
        pw, kp = resolve_sftp_secrets(src, supplied) if src["type"] == "sftp" else (None, None)
        for s in (pw, kp):
            if s:
                redact.register(s)
                secrets.append(s)
        fs = open_fs(src, settings, pw, kp)
        res["connected"] = True
    except Exception as e:
        res["error"] = redact.redact(f"{type(e).__name__}: {e}")
        for s in secrets:
            redact.unregister(s)
        return res
    excl = src.get("excludes", [])
    t_all = time.time()
    try:
        for inc in src["includes"]:
            item = {"path": inc["path"], "skeleton": bool(inc.get("skeleton")), "exists": False, "matches": 0,
                    "files": 0, "dirs": 0, "bytes": 0, "partial": False, "error": None}
            res["items"].append(item)
            if time.time() - t_all > TOTAL_SECONDS:
                item["error"] = "skipped (overall time budget used up)"
                continue
            deadline = time.time() + PER_ITEM_SECONDS
            try:
                matches = [m for m in fs.glob(inc["path"]) if not is_excluded(m, excl)]
                item["matches"], item["exists"] = len(matches), bool(matches)
                count = 0
                for m in matches:
                    st = fs.lstat(m)
                    if stat.S_ISDIR(st.st_mode):
                        item["dirs"] += 1
                        if item["skeleton"]:
                            continue
                        stack = [m]
                        while stack and not item["partial"]:
                            d = stack.pop()
                            try:
                                items = fs.scandir(d)
                            except (OSError, IOError):
                                continue
                            for n, est in items:
                                p = d.rstrip("/") + "/" + n
                                if is_excluded(p, excl) or est is None:
                                    continue
                                count += 1
                                if stat.S_ISDIR(est.st_mode):
                                    item["dirs"] += 1
                                    stack.append(p)
                                elif stat.S_ISREG(est.st_mode):
                                    item["files"] += 1
                                    item["bytes"] += est.st_size or 0
                                if count >= MAX_ENTRIES or time.time() > deadline:
                                    item["partial"] = True
                                    break
                    elif stat.S_ISREG(st.st_mode):
                        item["files"] += 1
                        item["bytes"] += st.st_size or 0
            except Exception as e:
                item["error"] = redact.redact(f"{type(e).__name__}: {e}")
    finally:
        fs.close()
        for s in secrets:
            redact.unregister(s)
    return res
