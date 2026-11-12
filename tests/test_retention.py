from datetime import datetime, timedelta, timezone

from bunnysave.retention import select_for_deletion

NOW = datetime(2026, 6, 30, 12, tzinfo=timezone.utc)


def mk(n, step_days=1):
    return [(f"b{i}", NOW - timedelta(days=i * step_days, hours=1)) for i in range(n)]


def test_keep_all():
    assert select_for_deletion(mk(10), {"type": "keep_all"}, NOW) == set()


def test_last_n():
    d = select_for_deletion(mk(10), {"type": "last", "n": 3}, NOW)
    assert d == {f"b{i}" for i in range(3, 10)}


def test_days():
    d = select_for_deletion(mk(10), {"type": "days", "n": 4}, NOW)
    assert d == {f"b{i}" for i in range(4, 10)}


def test_newest_never_deleted():
    old = [("only", NOW - timedelta(days=999))]
    assert select_for_deletion(old, {"type": "days", "n": 1}, NOW) == set()


def test_gfs():
    items = mk(60)  # 60 daily backups
    pol = {"type": "gfs", "daily": 7, "weekly": 4, "monthly": 2, "yearly": 0}
    deleted = select_for_deletion(items, pol, NOW)
    kept = {b for b, _ in items} - deleted
    assert {f"b{i}" for i in range(7)} <= kept  # 7 dailies
    assert len(kept) < len(items) and len(kept) >= 7 + 3  # plus some weeklies/monthlies
    assert "b30" in deleted or "b31" in deleted  # mid-range non-representatives pruned
