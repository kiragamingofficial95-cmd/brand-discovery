"""Quota manager for YouTube Data API and web search."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional

from .config import Config
from .db import Database


class QuotaExceeded(Exception):
    pass


class QuotaManager:
    def __init__(self, db: Database, config: Config, service: str = "youtube"):
        self.db = db
        self.config = config
        self.service = service
        self._run_id: Optional[int] = None

    def set_run(self, run_id: int) -> None:
        self._run_id = run_id

    def _pacific_midnight(self) -> datetime:
        # midnight Pacific = 08:00 UTC (PST) / 07:00 UTC (PDT). Approximate with fixed offset -8.
        # For correctness we just reset based on date in UTC-8.
        now = datetime.now(timezone.utc)
        pst = now - timedelta(hours=8)
        midnight_pst = pst.replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight_pst + timedelta(hours=8)  # back to UTC

    def _window_start_iso(self) -> str:
        midnight_utc = self._pacific_midnight()
        # start of current PT day in UTC
        start_pt = (datetime.now(timezone.utc) - timedelta(hours=8)).replace(hour=0, minute=0, second=0, microsecond=0)
        start_utc = start_pt + timedelta(hours=8)
        return start_utc.isoformat()

    def daily_limit(self) -> int:
        if self.service == "youtube":
            return int(self.config.quotas.get("youtube_daily_units", 10000))
        return int(self.config.quotas.get("web_search_daily_limit", 100))

    def hard_stop(self) -> int:
        if self.service == "youtube":
            return int(self.config.quotas.get("youtube_hard_stop", 8000))
        return self.daily_limit()

    def used_today(self) -> int:
        return self.db.quota_used_today(self.service, self._window_start_iso())

    def remaining(self) -> int:
        return max(0, self.daily_limit() - self.used_today())

    def can_afford(self, cost: int) -> bool:
        return (self.used_today() + cost) <= self.hard_stop()

    def charge(self, operation: str, cost: int) -> None:
        if not self.can_afford(cost):
            raise QuotaExceeded(f"{self.service} quota would exceed hard stop ({self.hard_stop()})")
        self.db.log_quota(self.service, operation, cost, self._run_id)

    def guard(self, operation: str, cost: int) -> None:
        """Call before making API request; raises QuotaExceeded if not affordable."""
        if not self.can_afford(cost):
            raise QuotaExceeded(f"{self.service} hard stop reached")
