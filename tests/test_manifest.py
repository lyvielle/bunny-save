import json

from bunnysave.manifest import MANIFEST_PATH, build_manifest, dumps


def test_manifest_fields_and_no_secrets():
    src = [{"id": "s1", "type": "sftp", "host": "100.64.0.5", "username": "u", "password": "hunter2",
            "key_passphrase": "x", "includes": [{"path": "/opt/a", "skeleton": True}], "excludes": ["*.tmp"]}]
    m = build_manifest("n", "2026-01-01T00:00:00Z", "box", src, True, [{"command": "echo hi", "timeout": 5}],
                       "tar.gz", skeleton_paths=["/opt/a"], stats={"entries": 3})
    for k in ("name", "timestamp", "hostname", "bunnysave_version", "sources", "excludes", "skeleton",
              "preserve_permissions", "post_restore_commands"):
        assert k in m
    assert m["excludes"] == ["*.tmp"] and m["skeleton"] == ["/opt/a"] and m["preserve_permissions"] is True
    blob = dumps(m).decode()
    assert "hunter2" not in blob and "key_passphrase" not in blob
    assert json.loads(blob)["name"] == "n"
    assert MANIFEST_PATH == ".bunnysave/manifest.json"
