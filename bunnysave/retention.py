"""Pure retention logic. Input: [(id, datetime)], policy dict. Output: ids to delete."""
from datetime import timedelta


def _keep_newest_per_bucket(items_desc, keyfn, count):
    kept, seen = set(), []
    for bid, ts in items_desc:
        k = keyfn(ts)
        if k not in seen:
            if len(seen) >= count:
                continue
            seen.append(k)
            kept.add(bid)
    return kept


def select_for_deletion(backups, policy, now):
    """The newest backup is never selected."""
    items = sorted(backups, key=lambda x: x[1], reverse=True)
    if not items:
        return set()
    t = policy.get("type", "keep_all")
    keep = {items[0][0]}
    if t == "keep_all":
        return set()
    if t == "last":
        keep |= {b for b, _ in items[:max(1, int(policy["n"]))]}
    elif t == "days":
        cutoff = now - timedelta(days=int(policy["n"]))
        keep |= {b for b, ts in items if ts >= cutoff}
    elif t == "gfs":
        keep |= _keep_newest_per_bucket(items, lambda d: d.date(), int(policy.get("daily", 0)))
        keep |= _keep_newest_per_bucket(items, lambda d: tuple(d.isocalendar())[:2], int(policy.get("weekly", 0)))
        keep |= _keep_newest_per_bucket(items, lambda d: (d.year, d.month), int(policy.get("monthly", 0)))
        keep |= _keep_newest_per_bucket(items, lambda d: d.year, int(policy.get("yearly", 0)))
    else:
        return set()
    return {b for b, _ in items} - keep
