"""Evidence rating and acceptance rules."""
from __future__ import annotations

from datetime import date, timedelta
from typing import List, Dict, Any, Optional, Tuple

VALID_STRENGTHS = {"strong", "medium", "weak"}


def age_days(ev: Dict[str, Any], today: Optional[date] = None) -> Optional[int]:
    d = ev.get("date")
    if not d:
        return None
    today = today or date.today()
    try:
        dd = date.fromisoformat(str(d)[:10])
    except ValueError:
        return None
    return (today - dd).days


def normalize_strength(ev: Dict[str, Any]) -> str:
    s = ev.get("strength", "weak")
    if s not in VALID_STRENGTHS:
        s = "weak"
    if not ev.get("date"):
        if s == "strong":
            s = "medium"
    return s


def is_live_checked(ev: Dict[str, Any]) -> bool:
    return bool(ev.get("checked_in_run", False))


def youtube_in_window(ev: Dict[str, Any], window_days: int, today: Optional[date] = None) -> bool:
    if ev.get("source_type") != "youtube":
        return True
    ad = age_days(ev, today)
    if ad is None:
        return False
    return ad <= window_days


def evidence_valid(ev: Dict[str, Any], today: Optional[date] = None, window_days: int = 90, scraper_mode: bool = False) -> bool:
    today = today or date.today()
    ad = age_days(ev, today)
    max_age = 730 if scraper_mode else 365
    if ad is not None:
        if ad > max_age:
            return False
        if ad < 0:
            return False
    if not scraper_mode:
        if not youtube_in_window(ev, window_days, today):
            return False
    if not ev.get("date"):
        if ev.get("source_type") == "youtube":
            return False
        if not is_live_checked(ev):
            return False
    return True


def brand_accepted(evidence: List[Dict[str, Any]], today: Optional[date] = None,
                   window_days: int = 90, scraper_mode: bool = False) -> Tuple[bool, str]:
    today = today or date.today()
    valid = [e for e in evidence if evidence_valid(e, today, window_days, scraper_mode)]
    for e in valid:
        e["strength"] = normalize_strength(e)
    strong = [e for e in valid if e.get("strength") == "strong"]
    medium = [e for e in valid if e.get("strength") == "medium"]
    if len(strong) >= 1:
        return True, "one_strong"
    if len(medium) >= 2:
        return True, "two_medium"
    if scraper_mode and (len(strong) + len(medium)) >= 1:
        return True, "scraper_one_medium"
    return False, "insufficient_evidence"


def older_evidence_flag(evidence: List[Dict[str, Any]], window_days: int, today: Optional[date] = None) -> bool:
    today = today or date.today()
    if window_days <= 90:
        return False
    for e in evidence:
        if e.get("source_type") == "youtube":
            ad = age_days(e, today)
            if ad is not None and 90 < ad <= window_days:
                return True
    return False