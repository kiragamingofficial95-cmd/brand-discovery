"""Core data models for brand discovery."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from enum import Enum
from typing import Optional, List, Dict, Any


class EvidenceStrength(str, Enum):
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"


class Niche(str, Enum):
    AI = "AI"
    SAAS = "SaaS"
    TECH = "tech"
    HEALTH = "health and wellness"
    TOURISM = "tourism"


@dataclass
class Evidence:
    url: str
    date: Optional[str] = None  # ISO date or None
    strength: EvidenceStrength = EvidenceStrength.WEAK
    source_type: str = ""  # youtube, web, podcast, newsletter, press, ...
    note: str = ""
    checked_in_run: bool = False

    def is_dated(self) -> bool:
        return bool(self.date)

    def age_days(self, today: Optional[date] = None) -> Optional[int]:
        if not self.date:
            return None
        try:
            d = date.fromisoformat(self.date[:10])
        except ValueError:
            return None
        today = today or date.today()
        return (today - d).days


@dataclass
class Brand:
    domain: str  # root domain = brand ID
    name: str = ""
    niche: str = ""
    sub_niche: str = ""
    website: str = ""
    score: int = 0
    saturated: bool = False
    older_evidence: bool = False
    evidence: List[Evidence] = field(default_factory=list)
    creators_90d: int = 0
    first_seen: Optional[str] = None
    last_reported: Optional[str] = None
    report_count: int = 0
    sponsor_count: int = 0
    momentum: float = 0.0

    def key(self) -> str:
        return self.domain.lower().strip()


@dataclass
class Channel:
    channel_id: str
    title: str = ""
    niche: str = ""
    sub_niche: str = ""
    uploads_playlist: str = ""
    subscriber_count: int = 0
    video_count: int = 0
    last_scanned: Optional[str] = None
    scan_interval_days: int = 5
    featured_channels: List[str] = field(default_factory=list)


@dataclass
class Video:
    video_id: str
    channel_id: str
    title: str = ""
    description: str = ""
    published_at: Optional[str] = None
    paid_product_placement: bool = False
    tags: List[str] = field(default_factory=list)
    sponsor_detected: bool = False
    sponsor_brands: List[str] = field(default_factory=list)
    pinned_comment: str = ""


@dataclass
class Query:
    query_id: Optional[int] = None
    text: str = ""
    niche: str = ""
    sub_niche: str = ""
    source: str = "youtube"  # youtube | web
    created_at: Optional[str] = None
    last_run: Optional[str] = None
    runs: int = 0
    poor_runs: int = 0
    new_brands_per_100_units: float = 0.0
    retired: bool = False
    depth: int = 0


@dataclass
class RunRecord:
    run_id: Optional[int] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    status: str = "running"  # running | success | failed | missed
    youtube_units: int = 0
    web_calls: int = 0
    brands_found: int = 0
    notes: str = ""


@dataclass
class Feedback:
    brand_domain: str
    mark: str  # good | bad
    note: str = ""
    created_at: Optional[str] = None
