"""Reporting."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from .config import Config
from .db import Database


def build_daily_report(config: Config, db: Database, accepted: List[Dict[str, Any]],
                       yt_quota, web_quota) -> Dict[str, Any]:
    # brands per niche
    per_niche: Dict[str, int] = {}
    for b in accepted:
        per_niche[b.get("niche", "unknown")] = per_niche.get(b.get("niche", "unknown"), 0) + 1
    # duplicate rate: brands already reported before this run / total
    total = len(accepted)
    rer = sum(1 for b in accepted if (b.get("report_count", 0) or 0) > 1)
    dup_rate = (rer / total) if total else 0.0
    # best queries
    qs = sorted(db.list_queries(source="youtube", retired=False),
                key=lambda q: q.get("new_brands_per_100_units", 0.0), reverse=True)[:10]
    best_queries = [{"text": q.get("text"), "yield": q.get("new_brands_per_100_units")} for q in qs]
    # rejected agencies count
    rejected = [b for b in db.list_brands() if False]
    # quota used
    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "brands_per_niche": per_niche,
        "total_brands": total,
        "duplicate_rate": round(dup_rate, 3),
        "re_reported": rer,
        "best_queries": best_queries,
        "youtube_units_used": yt_quota.used_today(),
        "web_calls_used": web_quota.used_today(),
        "rejected_agencies": [],  # populated by denylist audit
        "manual_sources": config.web.get("manual_sources", []),
        "brands": [
            {
                "name": b.get("name"),
                "website": b.get("website"),
                "niche": b.get("niche"),
                "sub_niche": b.get("sub_niche"),
                "score": b.get("score"),
                "older_evidence": b.get("older_evidence"),
                "evidence": b.get("evidence", []),
                "why_fits": f"Fits {b.get('niche')}/{b.get('sub_niche')} via {len(b.get('evidence', []))} evidence signals; score {b.get('score')}.",
            }
            for b in accepted
        ],
    }
    return report
