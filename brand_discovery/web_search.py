"""Web search via one official search API (configurable)."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from .config import Config
from .db import Database
from .quota import QuotaManager


class WebSearchClient:
    def __init__(self, config: Config, db: Database, quota: QuotaManager, api_key: Optional[str] = None,
                 transport: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
                 dry_run: bool = False, fixtures_dir: str = "fixtures"):
        self.config = config
        self.db = db
        self.quota = quota
        self.api_key = api_key or os.environ.get("WEB_SEARCH_API_KEY", "")
        self.transport = transport
        self.dry_run = dry_run
        self.fixtures_dir = fixtures_dir
        self.provider = config.web.get("search_api", "serpapi")

    def search(self, query: str, num_results: int = 10) -> List[Dict[str, Any]]:
        self.quota.guard("web_search", 1)
        if self.transport:
            data = self.transport(query, {"num": num_results})
        elif self.dry_run:
            import hashlib, os as _os
            key = "websearch_" + query
            h = hashlib.sha256(key.encode()).hexdigest()[:16]
            path = _os.path.join(self.fixtures_dir, f"websearch_{h}.json")
            if not _os.path.exists(path):
                return []
            with open(path) as f:
                data = json.load(f)
        else:
            data = self._real_search(query, num_results)
        self.quota.charge("web_search", 1)
        return self._parse(data)

    def _real_search(self, query: str, num_results: int) -> Dict[str, Any]:
        if self.provider == "serpapi":
            url = "https://serpapi.com/search.json?" + urllib.parse.urlencode({
                "q": query, "num": num_results, "api_key": self.api_key,
            })
            with urllib.request.urlopen(url, timeout=30) as resp:
                return json.loads(resp.read().decode())
        # generic: google custom search
        url = "https://www.googleapis.com/customsearch/v1?" + urllib.parse.urlencode({
            "q": query, "num": num_results, "key": self.api_key,
        })
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.loads(resp.read().decode())

    def _parse(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        out = []
        for item in data.get("organic_results", []) or data.get("items", []) or []:
            out.append({
                "title": item.get("title", ""),
                "link": item.get("link", "") or item.get("url", ""),
                "snippet": item.get("snippet", "") or item.get("description", ""),
            })
        return out
