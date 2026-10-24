"""HTTP fetching with caching, robots.txt respect, rate limiting and backoff."""
from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path
from typing import Optional, Tuple

from .config import Config


class Fetcher:
    def __init__(self, config: Config, cache_dir: str = "cache"):
        self.config = config
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._last_request: dict[str, float] = {}
        self._robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}

    def _cache_path(self, url: str) -> Path:
        h = hashlib.sha256(url.encode()).hexdigest()
        return self.cache_dir / (h + ".html")

    def _delay(self, host: str) -> None:
        delay = float(self.config.quotas.get("web_request_delay_seconds", 2.5))
        last = self._last_request.get(host, 0.0)
        wait = delay - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        self._last_request[host] = time.time()

    def _robots_allowed(self, url: str, user_agent: str = "BrandDiscoveryBot") -> bool:
        parsed = urllib.parse.urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base not in self._robots_cache:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(base + "/robots.txt")
            try:
                rp.read()
            except Exception:
                # if robots unreachable, be conservative: allow
                pass
            self._robots_cache[base] = rp
        try:
            return self._robots_cache[base].can_fetch(user_agent, url)
        except Exception:
            return True

    def fetch(self, url: str, use_cache: bool = True, max_retries: int = 5) -> Tuple[Optional[str], int, Optional[str]]:
        """Return (content, status_code, error). Respects robots.txt."""
        if not self._robots_allowed(url):
            return None, 0, "robots_disallowed"
        cp = self._cache_path(url)
        if use_cache and cp.exists():
            try:
                return cp.read_text(encoding="utf-8", errors="replace"), 200, None
            except Exception:
                pass
        host = urllib.parse.urlparse(url).netloc
        self._delay(host)
        last_err = None
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "BrandDiscoveryBot/1.0"})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = resp.read()
                    text = data.decode("utf-8", errors="replace")
                    try:
                        cp.write_text(text, encoding="utf-8")
                    except Exception:
                        pass
                    return text, resp.status, None
            except urllib.error.HTTPError as e:
                if e.code in (429,) or 500 <= e.code < 600:
                    last_err = f"http_{e.code}"
                    time.sleep(2 ** attempt)
                    continue
                return None, e.code, f"http_{e.code}"
            except Exception as e:
                last_err = str(e)
                time.sleep(2 ** attempt)
        return None, 0, last_err or "failed"
