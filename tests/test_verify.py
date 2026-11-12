import os
import shutil

import pytest

from bunnysave.archive_io import verify_archive
from bunnysave.backup import run_backup
from conftest import new_job


def _src(tmp_path):
    src = tmp_path / "src"
    (src / "d").mkdir(parents=True)
    (src / "a.txt").write_text("hello\n" * 1000)
    (src / "d" / "b.bin").write_bytes(os.urandom(50_000))
    return src


def test_verify_ok_and_detects_corruption(env, mk, tmp_path):
    s, db = env
    _src(tmp_path)
    setup = mk()
    job = new_job()
    run_backup(s, db, job, setup, {})
    b = db.list_backups()[0]
    assert b["status"] == "ok" and b["verify_status"] == "ok" and len(b["sha256"]) == 64
    ok, _ = verify_archive(b["path"], "tar.gz", None, None, s)
    assert ok
    data = bytearray(open(b["path"], "rb").read())
    data[len(data) // 2] ^= 0xFF  # flip a byte mid-stream
    open(b["path"], "wb").write(data)
    ok, detail = verify_archive(b["path"], "tar.gz", None, None, s)
    assert not ok and detail


def test_verify_truncated(env, mk, tmp_path):
    s, db = env
    _src(tmp_path)
    run_backup(s, db, new_job(), mk(), {})
    b = db.list_backups()[0]
    data = open(b["path"], "rb").read()
    open(b["path"], "wb").write(data[: len(data) // 2])
    ok, _ = verify_archive(b["path"], "tar.gz", None, None, s)
    assert not ok


def test_insufficient_space_refused(env, mk, tmp_path, monkeypatch):
    s, db = env
    _src(tmp_path)
    import bunnysave.backup as bk
    monkeypatch.setattr(bk.shutil, "disk_usage", lambda p: shutil._ntuple_diskusage(100, 99, 1))
    with pytest.raises(RuntimeError, match="insufficient free space"):
        run_backup(s, db, new_job(), mk(), {})
    assert not any(p.name.endswith(".part") for p in s.backups_dir.iterdir())
