import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from bunnysave.db import DB
from bunnysave.jobs import Job
from bunnysave.model import normalize_setup
from bunnysave.settings import Settings


@pytest.fixture
def env(tmp_path):
    s = Settings(tmp_path / "data", master_key="test-master-key")
    return s, DB(s.db_path)


def make_setup(db, tmp_path, **over):
    raw = {"name": "t", "format": "tar.gz",
           "sources": [{"type": "local", "includes": [{"path": str(tmp_path / "src" / "*")}], "excludes": []}]}
    raw.update(over)
    cfg = normalize_setup(raw)
    db.save_setup("setup01", cfg, "2026-01-01T00:00:00Z")
    return db.get_setup("setup01")


@pytest.fixture
def mk(env, tmp_path):
    s, db = env
    return lambda **o: make_setup(db, tmp_path, **o)


def new_job(kind="backup"):
    return Job(kind, "setup01", "t")
