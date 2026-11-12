"""Runtime settings (paths + master key). Master key is removed from os.environ so
child processes (hooks, gpg, ...) never inherit it."""
import os
from pathlib import Path

from . import redact


class Settings:
    def __init__(self, data_dir, master_key=None, host_root=None):
        self.data_dir = Path(data_dir)
        self.host_root = Path(host_root or "/hostfs")
        self.db_path = self.data_dir / "bunnysave.db"
        self.backups_dir = self.data_dir / "backups"
        self.keys_dir = self.data_dir / "keys"
        self.gnupg_home = self.data_dir / "gnupg"
        self.logs_dir = self.data_dir / "logs"
        self.known_hosts = self.data_dir / "known_hosts"
        for d in (self.data_dir, self.backups_dir, self.keys_dir, self.gnupg_home, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)
        try:
            self.gnupg_home.chmod(0o700)
        except OSError:
            pass
        self.master_key = master_key
        if master_key:
            redact.register(master_key)

    @classmethod
    def from_env(cls):
        mk = os.environ.pop("BUNNYSAVE_MASTER_KEY", None)
        mk_file = os.environ.pop("BUNNYSAVE_MASTER_KEY_FILE", None)
        if not mk and mk_file and os.path.isfile(mk_file):
            mk = Path(mk_file).read_text().strip()
        return cls(os.environ.get("BUNNYSAVE_DATA", "/data"), mk or None, os.environ.get("BUNNYSAVE_HOST_ROOT", "/hostfs"))

    def host_available(self):
        try:
            return self.host_root.is_dir() and any(self.host_root.iterdir())
        except OSError:
            return False
