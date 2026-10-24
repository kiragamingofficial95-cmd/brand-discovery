"""Brand scoring 0-100."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, Any, Optional

from .config import Config
from .db import Database


def score_brand(brand: Dict[str, Any], db: Database, config: Config,
                has_creator_angle: bool = True, today: Optional[date] = None,
                scraper_mode: bool = False) -> int:
    today = today or date.today()
    sc = config.scoring
    min_score = config.thresholds.get("scraper_min_score", 30) if scraper_mode else config.thresholds.get("min_score", 60)
    score = int(sc.get("base", 0))

    # distinct creators in 90d
    creators = int(brand.get("creators_90d", 0) or 0)
    w = int(sc.get("distinct_creators_90d_weight", 8))
    score += min(creators, 10) * w  # cap contribution

    # recency: evidence within 30 days
    evs = brand.get("evidence", []) or []
    recent = False
    for e in evs:
        d = e.get("date")
        if d:
            try:
                dd = date.fromisoformat(str(d)[:10])
                if (today - dd).days <= 30:
                    recent = True
            except ValueError:
                pass
    if recent:
        score += int(sc.get("recency_weight", 10))

    # promo code or paid flag
    has_promo = any(e.get("strength") == "strong" and ("promo" in (e.get("note", "") + e.get("source_type", "")).lower() or "paid" in (e.get("note", "")).lower()) for e in evs)
    if any("promo code" in (e.get("note", "").lower()) or "paid promotion flag" in (e.get("note", "").lower()) for e in evs):
        has_promo = True
    # scraper mode: any strong YouTube evidence counts as promo
    if scraper_mode and any(e.get("strength") == "strong" and e.get("source_type") == "youtube" for e in evs):
        has_promo = True
    if has_promo:
        score += int(sc.get("promo_code_or_paid_flag", 15))

    # two source agreement
    sources = {e.get("source_type") for e in evs if e.get("source_type")}
    if len(sources) >= 2:
        score += int(sc.get("two_source_agreement", 12))

    # momentum: week-over-week rise in sponsor count
    momentum = float(brand.get("momentum", 0.0) or 0.0)
    mw = int(sc.get("momentum_weight", 10))
    score += int(min(momentum, 1.0) * mw) if momentum > 0 else 0

    # saturation penalty
    if brand.get("saturated"):
        score -= int(sc.get("saturation_penalty", 15))

    # no creator angle penalty
    if not has_creator_angle and not scraper_mode:
        score -= int(sc.get("no_creator_angle_penalty", 20))

    final = max(0, min(100, score))
    return final