"""Archive listing and text preview.

Fast path: a sidecar index (`<archive>.idx`, gzip JSON, encrypted like the archive) written at backup time holds
the manifest, every entry's metadata and small text previews, so browsing never touches the big archive.
Fallback: decrypt/decompress the whole archive (old backups); that pass writes the missing index afterwards.
zip needs no index: its central directory is already random-access.
"""
import json
import logging
import os
import posixpath
import time

from .archive_io import PipelineError, open_reader, read_index, write_index
from .manifest import MANIFEST_PATH

log = logging.getLogger("bunnysave.browse")
MAX_PREVIEW = 10 * 1024 * 1024
MAX_ENTRIES = 200_000
EMBED_FILE_MAX, EMBED_TOTAL_MAX = 128 * 1024, 8 * 1024 * 1024
TEXT_EXT = {".txt", ".yml", ".yaml", ".xaml", ".json", ".md", ".py", ".conf", ".cfg", ".ini", ".toml", ".sh",
            ".xml", ".html", ".htm", ".css", ".js", ".ts", ".log", ".csv", ".env", ".service", ".sql", ".rst",
            ".cs", ".csproj", ".sln", ".properties", ".bat", ".ps1", ".rules", ".timer", ".list", ".lock"}
TEXT_NAMES = {"dockerfile", "makefile", ".gitignore", ".dockerignore", ".bashrc", ".profile", "readme", "license"}


def is_text_name(name):
    base = posixpath.basename(name).lower()
    return base in TEXT_NAMES or posixpath.splitext(base)[1] in TEXT_EXT


_cache = {}  # backup id -> (timestamp, {"info": {name: info}, "previews": {name: text}, "binary": set}); RAM only
CACHE_TTL, CACHE_BACKUPS = 900, 4


def _cache_get(bid):
    ent = _cache.get(bid)
    if not ent or time.time() - ent[0] > CACHE_TTL:
        _cache.pop(bid, None)
        return None
    return ent[1]


def _cache_put(bid, entries, previews, binary):
    now = time.time()
    for k in [k for k, v in _cache.items() if now - v[0] > CACHE_TTL]:
        del _cache[k]
    d = {"info": {e["name"].lstrip("/"): e for e in entries}, "previews": previews, "binary": set(binary)}
    _cache[bid] = (now, d)
    while len(_cache) > CACHE_BACKUPS:
        del _cache[min(_cache, key=lambda k: _cache[k][0])]
    return d


def _enc(backup):
    return backup["enc"] if backup["encrypted"] else None


def _index_path(backup):
    return backup["path"] + ".idx"


def load_index(backup, secret, settings):
    """Return the validated index dict, or None (missing / stale / unreadable -> caller falls back)."""
    if backup["fmt"] == "zip" or not os.path.exists(_index_path(backup)):
        return None
    try:
        idx = read_index(_index_path(backup), _enc(backup), secret, settings)
    except (PipelineError, OSError, ValueError, EOFError) as e:
        log.info("browse index unusable for %s: %s", backup["id"], type(e).__name__)
        return None
    if idx.get("v") != 1 or idx.get("archive_sha256") != backup["sha256"]:
        return None
    return idx


def list_archive(backup, secret, settings):
    idx = load_index(backup, secret, settings)
    if idx:
        entries = idx["entries"]
        _cache_put(backup["id"], entries, idx.get("previews", {}), idx.get("binary", []))
        return {"manifest": idx["manifest"], "entries": entries[:MAX_ENTRIES], "truncated": len(entries) > MAX_ENTRIES, "indexed": True}

    entries, manifest, truncated = [], None, False
    previews, binary, used = {}, [], 0
    with open_reader(backup["path"], backup["fmt"], _enc(backup), secret, settings) as rd:
        for m in rd.members():
            if m.name == MANIFEST_PATH:
                manifest = json.loads(m.open().read())
                continue
            if len(entries) >= MAX_ENTRIES:
                truncated = True
                continue  # keep draining so the stream is verified end-to-end
            entries.append(m.info())
            if m.type == "file" and m.size <= EMBED_FILE_MAX and used < EMBED_TOTAL_MAX and is_text_name(m.name):
                data = m.open().read(EMBED_FILE_MAX)
                if b"\0" in data[:8192]:
                    binary.append(m.name.lstrip("/"))
                else:
                    previews[m.name.lstrip("/")] = data.decode("utf-8", "replace")
                    used += len(data)
    _cache_put(backup["id"], entries, previews, binary)
    if backup["fmt"] != "zip" and not truncated and manifest:
        try:  # upgrade an old backup: next open is instant
            write_index(_index_path(backup), {"v": 1, "archive_sha256": backup["sha256"], "manifest": manifest, "entries": entries,
                                              "previews": previews, "binary": binary}, _enc(backup), secret, settings)
        except Exception as e:
            log.info("could not write browse index for %s: %s", backup["id"], type(e).__name__)
    return {"manifest": manifest, "entries": entries, "truncated": truncated, "indexed": False}


def _metadata_reason(info, path, binary):
    if info["type"] != "file":
        return f"{info['type']} entry"
    if info["size"] >= MAX_PREVIEW:
        return "larger than 10 MB"
    if not is_text_name(path):
        return "binary / unknown extension: metadata only"
    if path in binary:
        return "binary content: metadata only"
    return None


def preview(backup, secret, settings, path):
    path = posixpath.normpath(path).lstrip("/")
    c = _cache_get(backup["id"])
    if c is None:
        idx = load_index(backup, secret, settings)
        if idx:
            c = _cache_put(backup["id"], idx["entries"], idx.get("previews", {}), idx.get("binary", []))
    if c:
        info = c["info"].get(path)
        if info:
            if path in c["previews"]:
                return {"info": info, "text": c["previews"][path], "reason": None, "cached": True}
            why = _metadata_reason(info, path, c["binary"])
            if why:  # decided from the index alone, archive untouched
                return {"info": info, "text": None, "reason": why}
    with open_reader(backup["path"], backup["fmt"], _enc(backup), secret, settings) as rd:
        if backup["fmt"] == "zip":
            hits = [m for m in [rd.find(path)] if m]  # direct lookup, reads only this member
        else:
            hits = (m for m in rd.members() if m.name.lstrip("/") == path)  # stream, stops at the entry
        for m in hits:
            info = m.info()
            why = _metadata_reason(info, path, ())
            if why:
                return {"info": info, "text": None, "reason": why}
            data = m.open().read(MAX_PREVIEW)
            if b"\0" in data[:8192]:
                return {"info": info, "text": None, "reason": "binary content: metadata only"}
            return {"info": info, "text": data.decode("utf-8", "replace"), "reason": None}
    raise FileNotFoundError(path)
