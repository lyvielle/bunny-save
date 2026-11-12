"""Setup configuration validation/normalisation. Secrets are stripped, never stored."""
import copy
import uuid

FORMATS = ("tar.gz", "tar.zst", "tar.bz2", "zip")
LEVELS = {"tar.gz": (1, 9, 6), "tar.bz2": (1, 9, 9), "tar.zst": (1, 19, 3), "zip": (0, 9, 6)}
SECRET_KEYS = {"password", "passphrase", "key_passphrase", "secret", "archive_password"}


def strip_secrets(d):
    if isinstance(d, dict):
        return {k: strip_secrets(v) for k, v in d.items() if k not in SECRET_KEYS}
    if isinstance(d, list):
        return [strip_secrets(x) for x in d]
    return d


def _int(v, default, lo, hi):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _cmds(items):
    out = []
    for c in items or []:
        if isinstance(c, str):
            c = {"command": c}
        cmd = (c.get("command") or "").strip()
        if cmd:
            out.append({"command": cmd, "timeout": _int(c.get("timeout"), 300, 1, 86400)})
    return out


def normalize_setup(raw, existing=None):
    raw = strip_secrets(copy.deepcopy(raw))
    name = (raw.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    fmt = raw.get("format", "tar.gz")
    if fmt not in FORMATS:
        raise ValueError(f"format must be one of {FORMATS}")
    lo, hi, dflt = LEVELS[fmt]
    cfg = {
        "name": name,
        "format": fmt,
        "level": _int(raw.get("level"), dflt, lo, hi),
        "preserve_permissions": bool(raw.get("preserve_permissions")),
        "target_dir": (raw.get("target_dir") or "").strip(),
        "space_ratio": float(raw.get("space_ratio") or 1.0),
        "secret_ref": (existing or {}).get("secret_ref") or uuid.uuid4().hex,
    }
    cfg["space_ratio"] = max(0.05, min(1.5, cfg["space_ratio"]))
    srcs = []
    for i, s in enumerate(raw.get("sources") or []):
        typ = s.get("type", "local")
        if typ not in ("local", "host", "sftp"):
            raise ValueError("source type must be local, host or sftp")
        incs = []
        for inc in s.get("includes") or []:
            if isinstance(inc, str):
                inc = {"path": inc}
            p = (inc.get("path") or "").strip()
            if p:
                if not p.startswith("/"):
                    raise ValueError(f"include paths must be absolute: {p}")
                incs.append({"path": p, "skeleton": bool(inc.get("skeleton"))})
        if not incs:
            raise ValueError(f"source {i + 1}: at least one include path is required")
        src = {
            "id": s.get("id") or f"s{i + 1}",
            "type": typ,
            "includes": incs,
            "excludes": [e.strip() for e in (s.get("excludes") or []) if e and e.strip()],
        }
        if typ == "sftp":
            if not (s.get("host") or "").strip() or not (s.get("username") or "").strip():
                raise ValueError("SFTP source needs host and username")
            src.update(host=s["host"].strip(), port=_int(s.get("port"), 22, 1, 65535),
                       username=s["username"].strip(),
                       auth=s.get("auth") if s.get("auth") in ("password", "key", "tailscale") else "password",
                       key_path=(s.get("key_path") or "").strip(),
                       secret_mode=s.get("secret_mode") if s.get("secret_mode") in ("prompt", "keyring") else "prompt")
        srcs.append(src)
    if len({s["id"] for s in srcs}) != len(srcs):
        raise ValueError("duplicate source ids")
    if not srcs:
        raise ValueError("at least one source is required")
    if {"local", "host"} <= {s["type"] for s in srcs}:
        raise ValueError("container-local and host-filesystem sources cannot be mixed in one setup (their paths would collide)")
    cfg["sources"] = srcs

    e = raw.get("encryption") or {}
    enc = {"enabled": bool(e.get("enabled"))}
    if enc["enabled"]:
        tool = e.get("tool") if e.get("tool") in ("gpg", "age") else "gpg"
        mode = e.get("mode") if e.get("mode") in ("passphrase", "recipient") else "passphrase"
        sm = e.get("secret_mode") if e.get("secret_mode") in ("prompt", "env", "keyring") else "prompt"
        if fmt == "zip":
            tool, mode = "zip-aes", "passphrase"
        if mode == "recipient":
            if not (e.get("recipient") or "").strip():
                raise ValueError("recipient is required for key-based encryption")
            if sm == "env":
                raise ValueError("env master key can only derive archive passphrases, not key passphrases")
        enc.update(tool=tool, mode=mode, secret_mode=sm, recipient=(e.get("recipient") or "").strip(),
                   identity_file=(e.get("identity_file") or "").strip())
    cfg["encryption"] = enc

    sc = raw.get("schedule") or {}
    t = sc.get("type", "none")
    if t == "interval":
        cfg["schedule"] = {"type": "interval", "hours": _int(sc.get("hours"), 24, 1, 24 * 90)}
    elif t == "daily":
        hh, _, mm = (sc.get("time") or "03:00").partition(":")
        cfg["schedule"] = {"type": "daily", "time": f"{_int(hh, 3, 0, 23):02d}:{_int(mm, 0, 0, 59):02d}"}
    else:
        cfg["schedule"] = {"type": "none"}

    r = raw.get("retention") or {}
    rt = r.get("type", "keep_all")
    if rt == "last":
        cfg["retention"] = {"type": "last", "n": _int(r.get("n"), 7, 1, 10000)}
    elif rt == "days":
        cfg["retention"] = {"type": "days", "n": _int(r.get("n"), 30, 1, 36500)}
    elif rt == "gfs":
        cfg["retention"] = {"type": "gfs", "daily": _int(r.get("daily"), 7, 0, 3650),
                            "weekly": _int(r.get("weekly"), 4, 0, 520),
                            "monthly": _int(r.get("monthly"), 12, 0, 240),
                            "yearly": _int(r.get("yearly"), 0, 0, 100)}
    else:
        cfg["retention"] = {"type": "keep_all"}

    h = raw.get("hooks") or {}
    cfg["hooks"] = {k: ({"command": (h.get(k) or {}).get("command", "").strip(),
                         "timeout": _int((h.get(k) or {}).get("timeout"), 300, 1, 86400)})
                    for k in ("pre", "post")}
    cfg["post_restore"] = _cmds(raw.get("post_restore"))
    return cfg
