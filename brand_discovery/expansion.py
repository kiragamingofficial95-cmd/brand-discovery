"""Query expansion and yield tracking."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from .config import Config
from .db import Database


POOR_RUN_THRESHOLD = 0.5  # new brands per 100 units below this counts as poor? configurable-ish


def seed_queries(db: Database, config: Config) -> int:
    existing = {(q["text"], q["niche"], q["sub_niche"]) for q in db.list_queries()}
    count = 0
    now = datetime.utcnow().isoformat()
    for niche in config.niches:
        for sub in config.subniches.get(niche, []):
            for text in config.starter_queries(sub):
                key = (text, niche, sub)
                if key in existing:
                    continue
                db.insert_query({"text": text, "niche": niche, "sub_niche": sub, "source": "youtube",
                                "created_at": now, "depth": 0})
                count += 1
    return count


def least_recently_scanned(db: Database, source: str = "youtube", limit: int = 50) -> List[Dict]:
    qs = [q for q in db.list_queries(source=source, retired=False)]
    qs.sort(key=lambda q: (q.get("last_run") or "", q.get("id", 0)))
    return qs[:limit]


def week_slices(days_back: int = 90, slice_days: int = 7) -> List[Tuple[str, str]]:
    """Return list of (publishedAfter, publishedBefore) ISO strings slicing last days_back into weeks."""
    now = datetime.now(timezone.utc)
    out = []
    start = now - timedelta(days=days_back)
    cur = start
    while cur < now:
        nxt = min(cur + timedelta(days=slice_days), now)
        out.append((cur.isoformat(), nxt.isoformat()))
        cur = nxt
    return out


def vary_params() -> List[Dict]:
    orders = ["relevance", "date", "viewCount", "rating"]
    regions = ["", "US", "GB", "DE", "ES", "FR", "PT", "BR", "IN", "JP"]
    langs = ["", "en", "de", "es", "fr", "pt"]
    durations = ["", "short", "medium", "long"]
    out = []
    for o in orders:
        for r in regions:
            for l in langs:
                for d in durations:
                    out.append({"order": o, "regionCode": r, "relevanceLanguage": l, "videoDuration": d})
    return out


def update_query_yield(db: Database, qid: int, new_brands: int, units: int) -> None:
    qrows = [q for q in db.list_queries() if q["id"] == qid]
    if not qrows:
        return
    q = qrows[0]
    runs = q.get("runs", 0) + 1
    yield_val = (new_brands / max(units, 1)) * 100.0
    # running average
    prev = q.get("new_brands_per_100_units", 0.0) or 0.0
    new_avg = (prev * (runs - 1) + yield_val) / runs if runs > 0 else yield_val
    poor = q.get("poor_runs", 0)
    if yield_val < 0.5:
        poor += 1
    fields = {"last_run": datetime.utcnow().isoformat(), "runs": runs,
              "new_brands_per_100_units": new_avg, "poor_runs": poor}
    if poor >= 3:
        fields["retired"] = True
    db.update_query(qid, **fields)


def retire_poor(db: Database) -> int:
    n = 0
    for q in db.list_queries(retired=False):
        if q.get("poor_runs", 0) >= 3:
            db.update_query(q["id"], retired=True)
            n += 1
    return n


def make_replacement_queries(db: Database, config: Config, sponsored_videos: List[Dict]) -> int:
    """Create new queries from tags/titles of sponsored videos."""
    existing = {(q["text"].lower(), q["niche"]) for q in db.list_queries()}
    count = 0
    now = datetime.utcnow().isoformat()
    for v in sponsored_videos:
        # use tags
        for tag in (v.get("tags") or [])[:5]:
            for niche in config.niches:
                text = f"{tag} sponsored"
                if (text.lower(), niche) in existing:
                    continue
                # only add if tag somewhat relevant? add anyway, drift control later
                db.insert_query({"text": text, "niche": niche, "sub_niche": "", "source": "youtube",
                                "created_at": now, "depth": 1})
                existing.add((text.lower(), niche))
                count += 1
                if count > 50:
                    return count
    return count


def competitor_queries(brand_name: str) -> List[str]:
    return [f"{brand_name} alternatives", f"{brand_name} vs", f"best {brand_name} competitors"]


def max_depth_ok(depth: int, config: Config) -> bool:
    return depth <= int(config.thresholds.get("expansion_max_depth", 2))
