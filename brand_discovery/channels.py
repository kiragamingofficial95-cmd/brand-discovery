"""Channel pool management."""
from __future__ import annotations

from typing import Dict, List

from .config import Config
from .db import Database


def uc_to_uu(channel_id: str) -> str:
    if channel_id.startswith("UC"):
        return "UU" + channel_id[2:]
    return channel_id


def in_size_band(subs: int, config: Config) -> bool:
    mn = int(config.thresholds.get("min_channel_subs", 10000))
    mx = int(config.thresholds.get("max_channel_subs", 500000))
    return mn <= subs <= mx


def rescan_interval_days(upload_rate_per_week: float, config: Config) -> int:
    mn = int(config.thresholds.get("rescan_min_days", 3))
    mx = int(config.thresholds.get("rescan_max_days", 7))
    if upload_rate_per_week >= 5:
        return mn
    if upload_rate_per_week >= 2:
        return (mn + mx) // 2
    return mx


def due_channels(db: Database, now_iso: str) -> List[Dict]:
    return db.channels_due_for_rescan(now_iso)


def pool_size_by_niche(db: Database) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for ch in db.list_channels():
        out[ch.get("niche", "")] = out.get(ch.get("niche", ""), 0) + 1
    return out
