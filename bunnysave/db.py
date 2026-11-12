import json
import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS setups(id TEXT PRIMARY KEY, name TEXT, config TEXT, created TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS backups(
  id TEXT PRIMARY KEY, setup_id TEXT, setup_name TEXT, filename TEXT, path TEXT, created TEXT,
  size INTEGER, fmt TEXT, encrypted INTEGER, enc TEXT, sha256 TEXT, verify_status TEXT,
  status TEXT, error TEXT, secret_ref TEXT, manifest TEXT);
CREATE INDEX IF NOT EXISTS ix_backups_setup ON backups(setup_id, created);
"""


class DB:
    def __init__(self, path):
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.conn.executescript(SCHEMA)

    def _q(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def _x(self, sql, args=()):
        with self.lock:
            self.conn.execute(sql, args)
            self.conn.commit()

    # setups
    def list_setups(self):
        rows = self._q("SELECT * FROM setups ORDER BY lower(name)")
        for r in rows:
            r["config"] = json.loads(r["config"])
        return rows

    def get_setup(self, sid):
        rows = self._q("SELECT * FROM setups WHERE id=?", (sid,))
        if not rows:
            return None
        rows[0]["config"] = json.loads(rows[0]["config"])
        return rows[0]

    def save_setup(self, sid, config, now):
        self._x("INSERT INTO setups(id,name,config,created,updated) VALUES(?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, config=excluded.config, updated=excluded.updated",
                (sid, config["name"], json.dumps(config), now, now))

    def delete_setup(self, sid):
        self._x("DELETE FROM setups WHERE id=?", (sid,))

    # backups
    def add_backup(self, rec):
        rec = dict(rec)
        rec["enc"] = json.dumps(rec.get("enc") or {})
        rec["manifest"] = json.dumps(rec.get("manifest") or {})
        cols = ",".join(rec)
        self._x(f"INSERT INTO backups({cols}) VALUES({','.join('?' * len(rec))})", tuple(rec.values()))

    def update_backup(self, bid, **kw):
        sets = ",".join(f"{k}=?" for k in kw)
        self._x(f"UPDATE backups SET {sets} WHERE id=?", (*kw.values(), bid))

    def _load_backup(self, r):
        r["enc"] = json.loads(r.get("enc") or "{}")
        r["manifest"] = json.loads(r.get("manifest") or "{}")
        r["encrypted"] = bool(r["encrypted"])
        return r

    def get_backup(self, bid):
        rows = self._q("SELECT * FROM backups WHERE id=?", (bid,))
        return self._load_backup(rows[0]) if rows else None

    def list_backups(self, setup_id=None):
        if setup_id:
            rows = self._q("SELECT * FROM backups WHERE setup_id=? ORDER BY created DESC", (setup_id,))
        else:
            rows = self._q("SELECT * FROM backups ORDER BY created DESC")
        return [self._load_backup(r) for r in rows]

    def delete_backup(self, bid):
        self._x("DELETE FROM backups WHERE id=?", (bid,))
