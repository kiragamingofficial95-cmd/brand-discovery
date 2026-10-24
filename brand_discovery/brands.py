"""Brand normalization, dedup and saturation helpers."""
from __future__ import annotations

from typing import Dict, List, Optional

from .links import extract_brand_domain, root_domain
from .db import Database


def normalize_domain(value: str) -> str:
    value = (value or "").strip().lower()
    if "://" in value:
        return extract_brand_domain(value)
    if "." in value and " " not in value:
        return root_domain(value)
    return value


def merge_evidence(existing: List[Dict], new: List[Dict]) -> List[Dict]:
    seen = {(e.get("url"), e.get("date")) for e in existing}
    out = list(existing)
    for e in new:
        key = (e.get("url"), e.get("date"))
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out


def is_new_brand(db: Database, domain: str) -> bool:
    return db.get_brand(domain.lower()) is None


def distinct_creators_for_brand(db: Database, domain: str) -> int:
    # count videos mentioning brand across distinct channels
    channels = set()
    for v in db.list_videos():
        if domain.lower() in [b.lower() for b in v.get("sponsor_brands", [])]:
            channels.add(v.get("channel_id"))
    return len(channels)


def saturation_threshold(db: Database) -> int:
    brands = db.list_brands()
    if not brands:
        return 10**9
    counts = sorted(b.get("sponsor_count", 0) for b in brands)
    # top 10%
    idx = max(0, int(len(counts) * 0.9))
    return counts[idx] if idx < len(counts) else counts[-1]


def is_saturated(db: Database, domain: str) -> bool:
    b = db.get_brand(domain.lower())
    if not b:
        return False
    thr = saturation_threshold(db)
    return int(b.get("sponsor_count", 0)) >= thr


def re_report_allowed(db: Database, domain: str, new_creators_since: int, today_iso: str) -> bool:
    b = db.get_brand(domain.lower())
    if not b:
        return True
    last = b.get("last_reported")
    if not last:
        return True
    # 45 days
    from datetime import datetime, timedelta
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        now_dt = datetime.fromisoformat(today_iso.replace("Z", "+00:00"))
    except Exception:
        return True
    if (now_dt - last_dt).days < 45:
        return False
    if new_creators_since < 2:
        return False
    return True
