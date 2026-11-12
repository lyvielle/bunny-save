"""Secret redaction for logs, job output and UI-facing text."""
import json
import logging
import re
import threading
import time

_lock = threading.Lock()
_secrets: dict[str, int] = {}
_KV = re.compile(r"(?i)\b(pass(?:word|phrase)?|secret|token|key_passphrase)(\s*[=:]\s*)(\S+)")
MASK = "***"


def register(secret):
    if secret and len(secret) >= 4:
        with _lock:
            _secrets[secret] = _secrets.get(secret, 0) + 1


def unregister(secret):
    with _lock:
        if secret in _secrets:
            _secrets[secret] -= 1
            if _secrets[secret] <= 0:
                del _secrets[secret]


def redact(text):
    if not text:
        return text
    text = str(text)
    with _lock:
        secrets = sorted(_secrets, key=len, reverse=True)
    for s in secrets:
        text = text.replace(s, MASK)
    return _KV.sub(lambda m: m.group(1) + m.group(2) + MASK, text)


class RedactingFilter(logging.Filter):
    def filter(self, record):
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record):
        d = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for k in ("job_id", "setup_id", "backup_id"):
            if hasattr(record, k):
                d[k] = getattr(record, k)
        if record.exc_info:
            d["exc"] = redact(self.formatException(record.exc_info))
        return redact(json.dumps(d, ensure_ascii=False))


def setup_logging(logs_dir=None, level=logging.INFO):
    from logging.handlers import RotatingFileHandler
    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)
    handlers = [logging.StreamHandler()]
    if logs_dir:
        handlers.append(RotatingFileHandler(f"{logs_dir}/bunnysave.log", maxBytes=5_000_000, backupCount=3))
    for h in handlers:
        h.setFormatter(JsonFormatter())
        h.addFilter(RedactingFilter())
        root.addHandler(h)
    logging.getLogger("paramiko").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
