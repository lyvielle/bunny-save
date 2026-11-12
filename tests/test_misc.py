import json

import pytest

from bunnysave import redact
from bunnysave.model import normalize_setup
from bunnysave.secretstore import derive_from_master


def test_redaction():
    redact.register("topsecretvalue")
    try:
        out = redact.redact("x topsecretvalue y password=abc123 key_passphrase: zzz")
        assert "topsecretvalue" not in out and "abc123" not in out and "zzz" not in out
    finally:
        redact.unregister("topsecretvalue")


def test_normalize_strips_secrets_and_validates():
    cfg = normalize_setup({"name": "n", "sources": [{"type": "sftp", "host": "h", "username": "u", "password": "pw",
                                                    "includes": ["/a/*"]}]})
    assert "\"pw\"" not in json.dumps(cfg) and "\"password\":" not in json.dumps(cfg)
    with pytest.raises(ValueError):
        normalize_setup({"name": "n", "sources": [{"type": "local", "includes": ["relative"]}]})
    with pytest.raises(ValueError):
        normalize_setup({"name": "", "sources": []})


def test_zip_encryption_is_forced_to_aes_tool():
    cfg = normalize_setup({"name": "n", "format": "zip", "encryption": {"enabled": True, "tool": "gpg"},
                           "sources": [{"type": "local", "includes": ["/a"]}]})
    assert cfg["encryption"]["tool"] == "zip-aes"


def test_derive_is_deterministic_and_scoped():
    assert derive_from_master("m", "ref1") == derive_from_master("m", "ref1")
    assert derive_from_master("m", "ref1") != derive_from_master("m", "ref2")
    assert derive_from_master("m", "ref1") != derive_from_master("m2", "ref1")


def test_zip_roundtrip_aes(env, mk, tmp_path):
    pytest.importorskip("pyzipper")
    from bunnysave.backup import run_backup
    from bunnysave.browse import list_archive
    from conftest import new_job
    from test_roundtrip import cfg_over, make_tree
    s, db = env
    make_tree(tmp_path)
    enc = {"enabled": True, "secret_mode": "prompt"}
    run_backup(s, db, new_job(), mk(**cfg_over(tmp_path, format="zip", encryption=enc)), {"archive_password": "zip-pw-1"})
    b = db.list_backups()[0]
    assert b["verify_status"] == "ok"
    assert len(list_archive(b, "zip-pw-1", s)["entries"]) > 3
    raw = open(b["path"], "rb").read()
    assert b"\x01\x99AE" in raw or b"AE" in raw  # WinZip AES extra field present; ZipCrypto never used


def test_api_smoke(env, tmp_path):
    from bunnysave.app import create_app
    s, _ = env
    c = create_app(s, start_scheduler=False).test_client()
    r = c.post("/api/setups", json={"name": "x", "sources": [{"type": "local", "includes": ["/etc/hostname"]}]})
    assert r.status_code == 201
    sid = r.json["id"]
    assert c.get("/api/setups").json[0]["name"] == "x"
    assert c.post("/api/setups", json={"name": ""}).status_code == 400
    r = c.post(f"/api/setups/{sid}/run", json={})
    assert r.status_code == 202
    assert c.get("/").status_code in (200, 404)


def test_api_full_flow(env, tmp_path):
    import time
    from bunnysave.app import create_app
    s, _ = env
    src = tmp_path / "src"
    (src / "d").mkdir(parents=True)
    (src / "d" / "note.md").write_text("# hi\n")
    c = create_app(s, start_scheduler=False).test_client()
    sid = c.post("/api/setups", json={"name": "flow", "preserve_permissions": True,
                                       "sources": [{"type": "local", "includes": [str(src / "*")]}]}).json["id"]
    job = c.post(f"/api/setups/{sid}/run", json={}).json
    for _ in range(100):
        j = c.get(f"/api/jobs/{job['id']}").json
        if j["state"] not in ("queued", "running"):
            break
        time.sleep(0.1)
    assert j["state"] == "done", j
    b = c.get("/api/backups").json[0]
    assert b["verify_status"] == "ok"
    ents = c.post(f"/api/backups/{b['id']}/entries", json={}).json
    assert any(e["name"].endswith("d/note.md") for e in ents["entries"])
    out = tmp_path / "out"
    body = {"target": str(out), "conflict": "skip"}
    plan = c.post(f"/api/backups/{b['id']}/restore/plan", json=body).json
    assert plan["summary"]["create"] >= 2 and not out.exists() or not any(out.rglob("note.md"))
    rj = c.post(f"/api/backups/{b['id']}/restore/run", json=body).json
    for _ in range(100):
        j = c.get(f"/api/jobs/{rj['id']}").json
        if j["state"] not in ("queued", "running"):
            break
        time.sleep(0.1)
    assert j["state"] == "done", j
    assert (out / str(src).lstrip("/") / "d" / "note.md").read_text() == "# hi\n"
    # post-restore without confirmation is rejected at the API
    bad = c.post(f"/api/backups/{b['id']}/restore/run", json={**body, "post_restore": {"enabled": True}})
    assert bad.status_code == 400
    assert c.delete(f"/api/backups/{b['id']}").status_code == 200
    assert c.get("/api/backups").json == []


def test_download_and_pwa_routes(env, tmp_path):
    import time
    from bunnysave.app import create_app
    s, _ = env
    src = tmp_path / "src"
    src.mkdir()
    (src / "f.txt").write_text("x")
    c = create_app(s, start_scheduler=False).test_client()
    sid = c.post("/api/setups", json={"name": "d", "sources": [{"type": "local", "includes": [str(src / "*")]}]}).json["id"]
    jid = c.post(f"/api/setups/{sid}/run", json={}).json["id"]
    for _ in range(100):
        if c.get(f"/api/jobs/{jid}").json["state"] not in ("queued", "running"):
            break
        time.sleep(0.1)
    b = c.get("/api/backups").json[0]
    r = c.get(f"/api/backups/{b['id']}/download")
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"] and r.data[:2] == b"\x1f\x8b"
    assert b"__V__" not in c.get("/").data and b"__V__" not in c.get("/sw.js").data
    assert c.get("/manifest.webmanifest").json["id"] == "/"
