"""Password sourcing: UI prompt (memory only), env master key (scrypt-derived), OS keyring.
Nothing here ever writes a secret to disk."""
import base64
import hashlib
import os
import sys

SERVICE = "bunnysave"


class SecretError(RuntimeError):
    pass


def derive_from_master(master, secret_ref, purpose="archive"):
    salt = f"bunnysave/v1/{secret_ref}/{purpose}".encode()
    key = hashlib.scrypt(master.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return base64.urlsafe_b64encode(key).decode().rstrip("=")


def _keyring():
    try:
        import keyring
        return keyring
    except ImportError as e:
        raise SecretError("keyring package not installed") from e


def keyring_get(name):
    kr = _keyring()
    try:
        return kr.get_password(SERVICE, name)
    except Exception as e:  # no backend, locked, ...
        raise SecretError(f"keyring unavailable: {type(e).__name__}") from e


def keyring_set(name, value):
    kr = _keyring()
    try:
        kr.set_password(SERVICE, name, value)
    except Exception as e:
        raise SecretError(f"keyring unavailable: {type(e).__name__}") from e


def archive_secret_required(fmt, enc):
    """True when a secret is mandatory to write/read this archive."""
    if not enc.get("enabled"):
        return False
    return fmt == "zip" or enc.get("mode", "passphrase") == "passphrase"


def resolve_archive_secret(settings, fmt, enc, secret_ref, supplied=None):
    """Return the archive passphrase (or key passphrase in recipient mode) or None."""
    if not enc.get("enabled"):
        return None
    required = archive_secret_required(fmt, enc)
    mode = enc.get("secret_mode", "prompt")
    val = None
    if mode == "prompt":
        val = supplied or None
    elif mode == "env":
        if not settings.master_key:
            raise SecretError("secret_mode=env but BUNNYSAVE_MASTER_KEY is not set")
        val = derive_from_master(settings.master_key, secret_ref)
    elif mode == "keyring":
        val = keyring_get(f"archive:{secret_ref}") or supplied
    if required and not val:
        raise SecretError(f"archive password required (secret mode: {mode})")
    return val


def sftp_secret_name(src):
    return f"sftp:{src.get('username','')}@{src.get('host','')}:{src.get('port',22)}"


def resolve_sftp_secrets(src, supplied=None):
    """Return (password, key_passphrase) for an SFTP source."""
    supplied = supplied or {}
    mode = src.get("secret_mode", "prompt") if src.get("auth") != "tailscale" else "none"
    pw = supplied.get("password") or None
    kp = supplied.get("key_passphrase") or None
    if mode == "keyring":
        if src.get("auth") == "key":
            kp = kp or keyring_get(f"sftp-key:{src.get('key_path','')}")
        else:
            pw = pw or keyring_get(sftp_secret_name(src))
    if src.get("auth") == "tailscale":
        return None, None  # Tailscale SSH: identity comes from the tailnet, no credential
    if src.get("auth", "password") == "password" and not pw:
        raise SecretError(f"SFTP password required for {src.get('host')}")
    return pw, kp


if __name__ == "__main__":  # python -m bunnysave.secretstore derive <secret_ref>
    if len(sys.argv) == 3 and sys.argv[1] == "derive":
        mk = os.environ.get("BUNNYSAVE_MASTER_KEY")
        if not mk:
            sys.exit("set BUNNYSAVE_MASTER_KEY")
        print(derive_from_master(mk, sys.argv[2]))
    else:
        sys.exit("usage: python -m bunnysave.secretstore derive <secret_ref>")
