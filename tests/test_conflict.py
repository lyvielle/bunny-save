import pytest

from bunnysave.conflict import decide_conflict, rename_target
from bunnysave.restore import UnsafePath, clean_rel


@pytest.mark.parametrize("policy,exists,edir,ndir,expected", [
    ("overwrite", False, False, False, "create"),
    ("skip", False, False, False, "create"),
    ("overwrite", True, False, False, "overwrite"),
    ("skip", True, False, False, "skip"),
    ("rename", True, False, False, "rename_then_create"),
    ("overwrite", True, True, True, "merge_dir"),
    ("skip", True, True, True, "merge_dir"),
    ("overwrite", True, True, False, "rename_then_create"),   # never delete a directory
    ("overwrite", True, False, True, "rename_then_create"),
])
def test_decide(policy, exists, edir, ndir, expected):
    assert decide_conflict(policy, exists, edir, ndir) == expected


def test_unknown_policy():
    with pytest.raises(ValueError):
        decide_conflict("nuke", True, False, False)


def test_rename_target_unique():
    taken = {"/a.bak-1", "/a.bak-1-2"}
    assert rename_target("/a", "1", lambda p: p in taken) == "/a.bak-1-3"


def test_path_traversal_rejected():
    for bad in ("../x", "a/../../x", ".."):
        with pytest.raises(UnsafePath):
            clean_rel(bad)
    assert clean_rel("/etc/passwd") == "etc/passwd"
