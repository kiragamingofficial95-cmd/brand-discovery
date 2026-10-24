"""Fallback: enrich video metadata from the public watch page (no transcripts)."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, Optional

VIDEO_URL = "https://www.youtube.com/watch?v={vid}"


def _unescape(raw: str) -> str:
    try:
        return json.loads('"' + raw + '"')
    except Exception:
        return raw.encode().decode("unicode_escape", "replace")


def parse_watch_page(html: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    m = re.search(r'"attributedDescription":\{"content":"(.*?)"(?:,"commandRuns"|,"styleRuns"|,"isExpandable"|\})', html, re.S)
    if m:
        out["description"] = _unescape(m.group(1))
    m = re.search(r'"publishDate":\{"simpleText":"([^"]+)"\}', html)
    if m:
        text = m.group(1)
        out["publish_date_text"] = text
        dm = re.search(r"([A-Z][a-z]{2}) (\d{1,2}), (\d{4})", text)
        if dm:
            try:
                dt = datetime.strptime(f"{dm.group(1)} {dm.group(2)}, {dm.group(3)}", "%b %d, %Y")
                out["published_at"] = dt.strftime("%Y-%m-%dT00:00:00Z")
            except ValueError:
                pass
    m = re.search(r'"channelId":"(UC[\w-]{22})"', html)
    if m:
        out["channel_id"] = m.group(1)
    m = re.search(r'"title":\{"runs":\[\{"text":"(.*?)"\}\]', html)
    if m:
        out["title"] = _unescape(m.group(1))
    return out


def fetch_watch_page(video_id: str, fetcher) -> Dict[str, Any]:
    html, status, err = fetcher.fetch(VIDEO_URL.format(vid=video_id))
    if not html:
        return {}
    return parse_watch_page(html)
