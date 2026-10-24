"""YouTube Data API v3 client."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
import time
from typing import Any, Callable, Dict, List, Optional

BASE = "https://www.googleapis.com/youtube/v3"


class YouTubeClient:
    def __init__(self, api_key: str = "", quota=None, dry_run: bool = False, fixtures_dir: str = "fixtures",
                 transport: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
                 max_retries: int = 5, base_url: str = "https://www.googleapis.com/youtube/v3",
                 use_api_key: bool = True, timeout: int = 30):
        self.api_key = api_key
        self.quota = quota
        self.dry_run = dry_run
        self.fixtures_dir = fixtures_dir
        self.transport = transport or self._default_transport
        self.max_retries = max_retries
        self.base_url = base_url.rstrip("/")
        self.use_api_key = use_api_key
        self.timeout = timeout

    def _default_transport(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        # dry run: load fixture
        if self.dry_run:
            import hashlib, os
            key = endpoint + json.dumps(params, sort_keys=True)
            h = hashlib.sha256(key.encode()).hexdigest()[:16]
            path = os.path.join(self.fixtures_dir, f"youtube_{endpoint}_{h}.json")
            if not os.path.exists(path):
                raise FileNotFoundError(f"dry-run fixture missing: {path}")
            with open(path) as f:
                return json.load(f)
        url = self.base_url + "/" + endpoint + "?" + urllib.parse.urlencode(params)
        last_err = None
        for attempt in range(self.max_retries):
            try:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                body = e.read().decode(errors="replace")
                if e.code in (429,) or 500 <= e.code < 600:
                    last_err = body
                    # check quotaExceeded
                    if "quotaExceeded" in body:
                        raise RuntimeError("quotaExceeded")
                    time.sleep(2 ** attempt)
                    continue
                if "quotaExceeded" in body:
                    raise RuntimeError("quotaExceeded")
                raise
            except Exception as e:
                last_err = str(e)
                time.sleep(2 ** attempt)
        raise RuntimeError(last_err or "transport failed")

    def _call(self, endpoint: str, params: Dict[str, Any], cost: int, operation: str) -> Dict[str, Any]:
        if self.quota is not None:
            self.quota.guard(operation, cost)
        call_params = dict(params)
        if not self.dry_run and self.use_api_key and self.api_key:
            call_params["key"] = self.api_key
        try:
            data = self.transport(endpoint, call_params if not self.dry_run else params)
        except RuntimeError as e:
            if "quotaExceeded" in str(e):
                raise
            raise
        if self.quota is not None:
            self.quota.charge(operation, cost)
        return data

    def search(self, q: str, part: str = "snippet", max_results: int = 25, **kwargs) -> Dict[str, Any]:
        params = {"part": part, "q": q, "maxResults": max_results, "type": "video"}
        for k in ("order", "regionCode", "relevanceLanguage", "videoDuration", "publishedAfter", "publishedBefore"):
            if kwargs.get(k):
                params[k] = kwargs[k]
        return self._call("search", params, 100, "search")

    def videos_list(self, ids: List[str], part: str = "snippet,paidProductPlacementDetails") -> Dict[str, Any]:
        params = {"part": part, "id": ",".join(ids), "maxResults": 50}
        return self._call("videos", params, 1, "videos.list")

    def channels_list(self, ids: List[str], part: str = "snippet,statistics,contentDetails") -> Dict[str, Any]:
        params = {"part": part, "id": ",".join(ids), "maxResults": 50}
        return self._call("channels", params, 1, "channels.list")

    def playlist_items_list(self, playlist_id: str, max_results: int = 50, page_token: Optional[str] = None) -> Dict[str, Any]:
        params = {"part": "snippet,contentDetails", "playlistId": playlist_id, "maxResults": max_results}
        if page_token:
            params["pageToken"] = page_token
        return self._call("playlistItems", params, 1, "playlistItems.list")

    def comment_threads_list(self, video_id: str, max_results: int = 5, order: str = "relevance") -> Dict[str, Any]:
        params = {"part": "snippet", "videoId": video_id, "maxResults": max_results, "order": order, "textFormat": "plainText"}
        return self._call("commentThreads", params, 1, "commentThreads.list")

    # helpers to parse
    @staticmethod
    def parse_search_items(data: Dict[str, Any]) -> List[Dict[str, Any]]:
        return data.get("items", [])

    @staticmethod
    def parse_video_items(data: Dict[str, Any]) -> List[Dict[str, Any]]:
        return data.get("items", [])

    @staticmethod
    def parse_channel_items(data: Dict[str, Any]) -> List[Dict[str, Any]]:
        return data.get("items", [])
