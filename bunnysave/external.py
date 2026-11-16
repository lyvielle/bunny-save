"""Archives that are not in this instance's history (e.g. downloaded from another Bunny Save server).

An external archive is described by the same dict shape as a history row, so browsing, previews and restore
reuse the normal code paths. Only the name (and, for zip, the entry flags) decides format and encryption."""
import os
import re
import time
import zipfile

from .archive_io import FMT_EXT  # noqa: F401  (documents the supported formats)

SUFFIXES = (("tar.gz", (".tar.gz", ".tgz")), ("tar.zst", (".tar.zst", ".tzst")), ("tar.bz2", (".tar.bz2", ".tbz2")), ("zip", (".zip",)))
SUPPORTED = ".tar.gz, .tar.zst, .tar.bz2 or .zip, optionally followed by .gpg or .age"


def detect(name):
    """-> (fmt, tool) from a file name like 'x-2026....tar.gz.gpg'."""
    low, tool = name.lower(), None
    for ext, t in ((".gpg", "gpg"), (".age", "age")):
        if low.endswith(ext):
            low, tool = low[:-len(ext)], t
            break
    for fmt, exts in SUFFIXES:
        if low.endswith(exts):
            return fmt, tool
    raise ValueError(f"unsupported archive type; expected {SUPPORTED}")


def safe_name(name):
    base = os.path.basename((name or "").replace("\\", "/")) or "archive"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", base)[:150]


def make_external(ext_id, path, display_name=None, enc_hint=None, uploaded=False):
    if not os.path.isfile(path):
        raise ValueError("not a file (or not readable inside the container)")
    name = display_name or os.path.basename(path)
    fmt, tool = detect(name)
    hint = enc_hint or {}
    enc = {"enabled": False}
    if fmt == "zip":
        try:
            with zipfile.ZipFile(path) as zf:
                if any(i.flag_bits & 0x1 for i in zf.infolist()):
                    enc = {"enabled": True, "tool": "aes", "mode": "passphrase", "secret_mode": "prompt"}
        except zipfile.BadZipFile:
            raise ValueError("not a valid zip file")
    elif tool:
        mode = "recipient" if hint.get("mode") == "recipient" else "passphrase"
        enc = {"enabled": True, "tool": tool, "mode": mode, "secret_mode": "prompt"}
        if tool == "age" and mode == "recipient":
            if not hint.get("identity_file"):
                raise ValueError("age key mode needs the identity file name (in the keys folder)")
            enc["identity_file"] = hint["identity_file"]
    st = os.stat(path)
    return {"id": ext_id, "setup_id": None, "setup_name": "external", "filename": name, "path": path, "fmt": fmt,
            "encrypted": bool(enc["enabled"]), "enc": enc, "secret_ref": "external", "sha256": None,
            "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime)), "size": st.st_size,
            "status": "ok", "verify_status": "unchecked", "error": None, "external": True, "uploaded": uploaded}


def view(b):
    return {"id": b["id"], "filename": b["filename"], "size": b["size"], "fmt": b["fmt"], "encrypted": b["encrypted"],
            "enc_tool": b["enc"].get("tool"), "created": b["created"], "external": True, "uploaded": b["uploaded"], "path": b["path"]}
