import json

from . import VERSION
from .model import strip_secrets

MANIFEST_PATH = ".bunnysave/manifest.json"


def build_manifest(name, timestamp, host, sources, preserve_permissions, post_restore, fmt,
                   skeleton_paths=(), stats=None, secret_ref=None):
    srcs = strip_secrets(sources)
    return {
        "bunnysave_manifest": 1,
        "name": name,
        "timestamp": timestamp,
        "hostname": host,
        "bunnysave_version": VERSION,
        "format": fmt,
        "sources": srcs,
        "excludes": [e for s in srcs for e in s.get("excludes", [])],
        "skeleton": sorted(skeleton_paths),
        "preserve_permissions": bool(preserve_permissions),
        "post_restore_commands": list(post_restore),
        "stats": stats or {},
    }


def dumps(m):
    return json.dumps(m, indent=2, sort_keys=True).encode()
