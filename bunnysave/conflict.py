"""Restore conflict policy (pure)."""

POLICIES = ("overwrite", "skip", "rename")


def decide_conflict(policy, exists, existing_is_dir, entry_is_dir):
    """Return one of: create, merge_dir, overwrite, skip, rename_then_create.
    Directories are never deleted or replaced: they are merged or moved aside."""
    if policy not in POLICIES:
        raise ValueError(f"unknown conflict policy {policy!r}")
    if not exists:
        return "create"
    if existing_is_dir and entry_is_dir:
        return "merge_dir"
    if policy == "skip":
        return "skip"
    if policy == "rename":
        return "rename_then_create"
    # overwrite
    if existing_is_dir or entry_is_dir:
        return "rename_then_create"  # type mismatch: move aside, never rm -r
    return "overwrite"


def rename_target(dest, stamp, exists_fn):
    cand = f"{dest}.bak-{stamp}"
    n = 1
    while exists_fn(cand):
        n += 1
        cand = f"{dest}.bak-{stamp}-{n}"
    return cand
