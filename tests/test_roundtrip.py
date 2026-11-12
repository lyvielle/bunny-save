import os
import shutil
import stat

import pytest

from bunnysave.backup import Cancelled, run_backup
from bunnysave.browse import list_archive, preview
from bunnysave.restore import run_restore
from conftest import new_job


def make_tree(tmp_path):
    src = tmp_path / "src"
    (src / "app" / "sub").mkdir(parents=True)
    (src / "skel" / "inner").mkdir(parents=True)
    (src / "skel" / "inner" / "secret.txt").write_text("should not be stored")
    (src / ".hidden").write_text("dot")
    (src / "app" / "conf.yml").write_text("a: 1\n")
    (src / "app" / "sub" / "bin.dat").write_bytes(os.urandom(4096))
    (src / "app" / "skip.tmp").write_text("excluded")
    (src / "app" / "run.sh").write_text("#!/bin/sh\n")
    os.chmod(src / "app" / "run.sh", 0o750)
    os.chmod(src / "skel", 0o711)
    os.symlink("conf.yml", src / "app" / "link")
    return src


def restore(s, db, b, target, conflict="overwrite", **kw):
    params = {"target": str(target), "conflict": conflict, "selection": kw.get("selection", []), "apply": True}
    return run_restore(s, db, new_job("restore"), b, params, kw.get("supplied", {}))


def cfg_over(tmp_path, **o):
    base = {"preserve_permissions": True,
            "sources": [{"type": "local", "excludes": ["*.tmp"],
                         "includes": [{"path": str(tmp_path / "src" / "app")},
                                      {"path": str(tmp_path / "src" / "skel"), "skeleton": True},
                                      {"path": str(tmp_path / "src" / ".hidden")}]}]}
    base.update(o)
    return base


def test_targz_roundtrip(env, mk, tmp_path):
    s, db = env
    src = make_tree(tmp_path)
    run_backup(s, db, new_job(), mk(**cfg_over(tmp_path)), {})
    b = db.list_backups()[0]
    assert b["status"] == "ok"

    listing = list_archive(b, None, s)
    names = {e["name"] for e in listing["entries"]}
    rel = lambda p: str(p).lstrip("/")
    assert rel(src / "app" / "conf.yml") in names
    assert rel(src / "app" / "skip.tmp") not in names           # exclude
    assert rel(src / "skel") in names                            # skeleton dir stored...
    assert rel(src / "skel" / "inner") not in names              # ...without contents
    assert listing["manifest"]["skeleton"] == [str(src / "skel")]
    assert preview(b, None, s, rel(src / "app" / "conf.yml"))["text"] == "a: 1\n"
    assert preview(b, None, s, rel(src / "app" / "sub" / "bin.dat"))["text"] is None  # binary: metadata only

    out = tmp_path / "out"
    res = restore(s, db, b, out)
    r = out / rel(src)
    assert (r / "app" / "conf.yml").read_text() == "a: 1\n"
    assert (r / "app" / "sub" / "bin.dat").read_bytes() == (src / "app" / "sub" / "bin.dat").read_bytes()
    assert not (r / "app" / "skip.tmp").exists()
    assert os.readlink(r / "app" / "link") == "conf.yml"
    assert (r / ".hidden").read_text() == "dot"
    assert stat.S_IMODE(os.stat(r / "app" / "run.sh").st_mode) == 0o750      # permissions flag honoured
    assert stat.S_IMODE(os.stat(r / "skel").st_mode) == 0o711
    assert list((r / "skel").iterdir()) == []                                # skeleton: empty dir only
    assert res["summary"]["create"] > 0


def test_conflict_policies_on_restore(env, mk, tmp_path):
    s, db = env
    src = make_tree(tmp_path)
    run_backup(s, db, new_job(), mk(**cfg_over(tmp_path)), {})
    b = db.list_backups()[0]
    out = tmp_path / "out"
    restore(s, db, b, out)
    f = out / str(src).lstrip("/") / "app" / "conf.yml"
    f.write_text("LOCAL EDIT")
    restore(s, db, b, out, "skip")
    assert f.read_text() == "LOCAL EDIT"
    restore(s, db, b, out, "rename")
    assert f.read_text() == "a: 1\n"
    baks = [p for p in f.parent.iterdir() if p.name.startswith("conf.yml.bak-")]
    assert len(baks) == 1 and baks[0].read_text() == "LOCAL EDIT"
    f.write_text("X")
    restore(s, db, b, out, "overwrite")
    assert f.read_text() == "a: 1\n"
    # plan does not write
    f.write_text("PLAN")
    plan = run_restore(s, db, new_job("restore"), b, {"target": str(out), "conflict": "skip", "apply": False}, {})
    assert f.read_text() == "PLAN" and plan["applied"] is False and plan["summary"]["skip"] >= 1


def test_selection_restore(env, mk, tmp_path):
    s, db = env
    src = make_tree(tmp_path)
    run_backup(s, db, new_job(), mk(**cfg_over(tmp_path)), {})
    b = db.list_backups()[0]
    out = tmp_path / "out"
    restore(s, db, b, out, selection=[str(src / "app" / "sub").lstrip("/")])
    assert (out / str(src).lstrip("/") / "app" / "sub" / "bin.dat").exists()
    assert not (out / str(src).lstrip("/") / "app" / "conf.yml").exists()


def test_post_restore_requires_confirmation(env, mk, tmp_path):
    s, db = env
    make_tree(tmp_path)
    marker = tmp_path / "marker"
    run_backup(s, db, new_job(), mk(**cfg_over(tmp_path, post_restore=[{"command": f"echo $BUNNYSAVE_JOB_ID > {marker}"}])), {})
    b = db.list_backups()[0]
    out = tmp_path / "out"
    base = {"target": str(out), "conflict": "skip", "apply": True}
    run_restore(s, db, new_job("restore"), b, base, {})                       # disabled by default
    assert not marker.exists()
    with pytest.raises(ValueError):
        run_restore(s, db, new_job("restore"), b, {**base, "post_restore": {"enabled": True, "indices": [0]}}, {})
    assert not marker.exists()
    j = new_job("restore")
    run_restore(s, db, j, b, {**base, "post_restore": {"enabled": True, "confirm": "RUN", "indices": [0]}}, {})
    assert marker.read_text().strip() == j.id
    assert j.hooks[0]["exit_code"] == 0


def test_hooks_and_env(env, mk, tmp_path):
    s, db = env
    make_tree(tmp_path)
    out = tmp_path / "hook.txt"
    hooks = {"pre": {"command": f"echo pre:$BUNNYSAVE_JOB_ID >> {out}"},
             "post": {"command": f"echo post:$BUNNYSAVE_ARCHIVE:$BUNNYSAVE_SOURCE >> {out}"}}
    j = new_job()
    run_backup(s, db, j, mk(**cfg_over(tmp_path, hooks=hooks)), {})
    lines = out.read_text().splitlines()
    assert lines[0] == f"pre:{j.id}" and lines[1].startswith("post:") and lines[1].endswith(":local")
    assert [h["which"] for h in j.hooks] == ["pre", "post"]


def test_failing_pre_hook_aborts(env, mk, tmp_path):
    s, db = env
    make_tree(tmp_path)
    with pytest.raises(RuntimeError):
        run_backup(s, db, new_job(), mk(**cfg_over(tmp_path, hooks={"pre": {"command": "exit 3"}})), {})
    assert db.list_backups() == []


def test_cancel_removes_part(env, mk, tmp_path):
    s, db = env
    make_tree(tmp_path)
    j = new_job()
    j.cancel_event.set()
    with pytest.raises(Cancelled):
        run_backup(s, db, j, mk(**cfg_over(tmp_path)), {})
    assert list(s.backups_dir.iterdir()) == [] and db.list_backups() == []


@pytest.mark.skipif(not shutil.which("gpg"), reason="gpg missing")
def test_gpg_passphrase_roundtrip_and_wrong_password(env, mk, tmp_path):
    s, db = env
    src = make_tree(tmp_path)
    enc = {"enabled": True, "tool": "gpg", "mode": "passphrase", "secret_mode": "prompt"}
    run_backup(s, db, new_job(), mk(**cfg_over(tmp_path, encryption=enc)), {"archive_password": "pw-correct-1"})
    b = db.list_backups()[0]
    assert b["encrypted"] and b["filename"].endswith(".tar.gz.gpg") and b["verify_status"] == "ok"
    assert b"conf.yml" not in open(b["path"], "rb").read()
    with pytest.raises(Exception):
        list_archive(b, "wrong-password", s)
    out = tmp_path / "out"
    restore(s, db, b, out, supplied={"archive_password": "pw-correct-1"})
    assert (out / str(src).lstrip("/") / "app" / "conf.yml").read_text() == "a: 1\n"


@pytest.mark.skipif(not shutil.which("age"), reason="age missing")
def test_age_passphrase_roundtrip(env, mk, tmp_path):
    s, db = env
    make_tree(tmp_path)
    enc = {"enabled": True, "tool": "age", "mode": "passphrase", "secret_mode": "prompt"}
    run_backup(s, db, new_job(), mk(**cfg_over(tmp_path, encryption=enc)), {"archive_password": "age-pass-1"})
    b = db.list_backups()[0]
    assert b["filename"].endswith(".age") and b["verify_status"] == "ok"
    assert len(list_archive(b, "age-pass-1", s)["entries"]) > 3
    with pytest.raises(Exception):
        list_archive(b, "nope-nope", s)


@pytest.mark.skipif(not shutil.which("gpg"), reason="gpg missing")
def test_env_master_key_derivation(env, mk, tmp_path):
    s, db = env
    make_tree(tmp_path)
    enc = {"enabled": True, "tool": "gpg", "mode": "passphrase", "secret_mode": "env"}
    run_backup(s, db, new_job(), mk(**cfg_over(tmp_path, encryption=enc)), {})
    b = db.list_backups()[0]
    from bunnysave.secretstore import resolve_archive_secret
    secret = resolve_archive_secret(s, b["fmt"], b["enc"], b["secret_ref"], None)   # derived, no prompt
    assert len(list_archive(b, secret, s)["entries"]) > 3


def test_secrets_not_in_logs_or_db(env, mk, tmp_path):
    s, db = env
    make_tree(tmp_path)
    j = new_job()
    enc = {"enabled": True, "tool": "gpg", "mode": "passphrase", "secret_mode": "prompt"}
    run_backup(s, db, j, mk(**cfg_over(tmp_path, encryption=enc)), {"archive_password": "SuperSecret123"})
    blob = repr(j.to_dict()) + repr(db.list_backups()) + repr(db.list_setups())
    assert "SuperSecret123" not in blob
    for p in s.data_dir.rglob("*"):
        if p.is_file() and p.suffix in (".json", ".log", ".db"):
            assert b"SuperSecret123" not in p.read_bytes()


def test_restore_start_point_strips_prefix_and_plan_writes_nothing(env, mk, tmp_path):
    s, db = env
    src = make_tree(tmp_path)
    run_backup(s, db, new_job(), mk(**cfg_over(tmp_path)), {})
    b = db.list_backups()[0]
    start = str(src / "app").lstrip("/")
    out = tmp_path / "flat"
    plan = run_restore(s, db, new_job("restore"), b, {"mode": "local", "target": str(out), "start": start,
                                                     "conflict": "skip", "apply": False}, {})
    assert not out.exists() and plan["start"] == start          # plan creates nothing, not even the target dir
    run_restore(s, db, new_job("restore"), b, {"mode": "local", "target": str(out), "start": start,
                                              "conflict": "skip", "apply": True}, {})
    assert (out / "conf.yml").read_text() == "a: 1\n"           # prefix stripped
    assert (out / "sub" / "bin.dat").exists() and not (out / ".hidden").exists()


def test_source_validity_check(env, tmp_path):
    from bunnysave.testing import test_source
    s, _ = env
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "a.bin").write_bytes(b"0" * 1000)
    src = {"type": "local", "id": "s1", "excludes": [],
           "includes": [{"path": str(tmp_path / "x")}, {"path": str(tmp_path / "x"), "skeleton": True},
                        {"path": str(tmp_path / "nope" / "*")}]}
    r = test_source(src, s, {})
    assert r["connected"]
    a, skel, missing = r["items"]
    assert a["exists"] and a["bytes"] == 1000 and a["files"] == 1
    assert skel["exists"] and skel["bytes"] == 0
    assert not missing["exists"]


def test_host_filesystem_source_roundtrip(tmp_path):
    from bunnysave.db import DB
    from bunnysave.settings import Settings
    from conftest import make_setup
    host = tmp_path / "hostroot"
    (host / "opt" / "app").mkdir(parents=True)
    (host / "opt" / "app" / "a.txt").write_text("host file")
    s = Settings(tmp_path / "data", host_root=host)
    db = DB(s.db_path)
    setup = make_setup(db, tmp_path, sources=[{"type": "host", "includes": [{"path": "/opt/app/*"}]}])
    run_backup(s, db, new_job(), setup, {})
    b = db.list_backups()[0]
    assert b["status"] == "ok"
    assert any(e["name"] == "opt/app/a.txt" for e in list_archive(b, None, s)["entries"])   # HOST paths in the archive
    (host / "opt" / "app" / "a.txt").write_text("changed")
    run_restore(s, db, new_job("restore"), b, {"mode": "origin", "conflict": "overwrite", "apply": True}, {})
    assert (host / "opt" / "app" / "a.txt").read_text() == "host file"                       # restored onto the host root


def test_host_and_local_cannot_mix():
    from bunnysave.model import normalize_setup
    with pytest.raises(ValueError):
        normalize_setup({"name": "x", "sources": [{"type": "host", "includes": ["/a"]}, {"type": "local", "includes": ["/b"]}]})


def test_browse_index_plain_and_old_backup_upgrade(env, mk, tmp_path):
    from bunnysave import browse
    s, db = env
    src = make_tree(tmp_path)
    run_backup(s, db, new_job(), mk(**cfg_over(tmp_path)), {})
    b = db.list_backups()[0]
    idxp = b["path"] + ".idx"
    assert os.path.exists(idxp)
    hidden = b["path"] + ".moved"
    os.rename(b["path"], hidden)                                  # archive untouched when the index is used
    try:
        lst = list_archive(b, None, s)
        assert lst["indexed"] and lst["manifest"]["name"]
        browse._cache.clear()
        rel = lambda p: str(p).lstrip("/")
        assert preview(b, None, s, rel(src / "app" / "conf.yml"))["text"] == "a: 1\n"
        assert preview(b, None, s, rel(src / "app" / "sub" / "bin.dat"))["text"] is None
    finally:
        os.rename(hidden, b["path"])
    os.remove(idxp)                                               # "old" backup: falls back, then writes the index
    browse._cache.clear()
    assert list_archive(b, None, s)["indexed"] is False
    assert os.path.exists(idxp) and list_archive(b, None, s)["indexed"] is True
    from bunnysave.backup import delete_backup_files
    delete_backup_files(b)
    assert not os.path.exists(idxp)


def test_browse_index_is_encrypted(env, mk, tmp_path):
    s, db = env
    make_tree(tmp_path)
    enc = {"enabled": True, "tool": "gpg", "mode": "passphrase", "secret_mode": "prompt"}
    run_backup(s, db, new_job(), mk(**cfg_over(tmp_path, encryption=enc)), {"archive_password": "pw-correct-1"})
    b = db.list_backups()[0]
    raw = open(b["path"] + ".idx", "rb").read()
    assert b"conf.yml" not in raw and b"a: 1" not in raw
    assert list_archive(b, "pw-correct-1", s)["indexed"] is True
    with pytest.raises(Exception):
        list_archive(b, "wrong-password", s)
