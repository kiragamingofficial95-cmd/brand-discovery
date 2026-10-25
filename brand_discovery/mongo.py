"""Optional MongoDB mirror for published brand data (dashboard read model)."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from pymongo import MongoClient, ASCENDING
    from pymongo.errors import PyMongoError
    _PYMONGO = True
except Exception:  # pragma: no cover
    _PYMONGO = False
    MongoClient = None  # type: ignore
    PyMongoError = Exception  # type: ignore


class MongoWriter:
    """Best-effort writer. Never raises into the pipeline."""

    def __init__(self, uri: Optional[str] = None, db_name: str = "brand_discovery",
                 brands_collection: str = "brands", runs_collection: str = "runs"):
        self.uri = uri or os.environ.get("MONGODB_URI") or os.environ.get("MONGO_URI")
        self.db_name = os.environ.get("MONGODB_DB", db_name)
        self.brands_collection = os.environ.get("MONGODB_BRANDS_COLLECTION", brands_collection)
        self.runs_collection = os.environ.get("MONGODB_RUNS_COLLECTION", runs_collection)
        self._client = None
        self._db = None
        self.enabled = bool(self.uri and _PYMONGO)

    def _connect(self):
        if self._db is not None:
            return self._db
        if not self.enabled:
            return None
        try:
            self._client = MongoClient(self.uri, serverSelectionTimeoutMS=8000)
            self._client.admin.command("ping")
            self._db = self._client[self.db_name]
            # indexes
            self._db[self.brands_collection].create_index("domain", unique=True)
            self._db[self.brands_collection].create_index([("niche", ASCENDING), ("score", -1 if False else ASCENDING)])
            self._db[self.runs_collection].create_index("generated_at")
            return self._db
        except Exception as e:
            print(f"[mongo] connection failed: {e}")
            self.enabled = False
            return None

    def upsert_run(self, run_id: int, generated_at: str, accepted: List[Dict[str, Any]],
                   report: Dict[str, Any], yt_units: int, web_calls: int, brands_found: int) -> bool:
        db = self._connect()
        if db is None:
            return False
        try:
            # upsert each brand
            col = db[self.brands_collection]
            for b in accepted:
                domain = (b.get("domain") or "").lower()
                if not domain:
                    continue
                doc = {
                    "domain": domain,
                    "name": b.get("name") or domain,
                    "website": b.get("website") or ("https://" + domain),
                    "niche": b.get("niche"),
                    "sub_niche": b.get("sub_niche"),
                    "score": int(b.get("score", 0) or 0),
                    "saturated": bool(b.get("saturated", False)),
                    "older_evidence": bool(b.get("older_evidence", False)),
                    "sponsor_count": int(b.get("sponsor_count", 0) or 0),
                    "creators_90d": int(b.get("creators_90d", 0) or 0),
                    "report_count": int(b.get("report_count", 0) or 0),
                    "last_reported": b.get("last_reported"),
                    "evidence": b.get("evidence", []) or [],
                    "evidence_count": len(b.get("evidence", []) or []),
                    "generated_at": generated_at,
                    "run_id": run_id,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                col.update_one({"domain": domain}, {"$set": doc, "$setOnInsert": {"first_seen": datetime.now(timezone.utc).isoformat()}}, upsert=True)

            # run snapshot
            db[self.runs_collection].insert_one({
                "run_id": run_id,
                "generated_at": generated_at,
                "brands_found": brands_found,
                "total_brands": (report or {}).get("total_brands"),
                "duplicate_rate": (report or {}).get("duplicate_rate"),
                "re_reported": (report or {}).get("re_reported"),
                "youtube_units_used": yt_units,
                "web_calls_used": web_calls,
                "brands_per_niche": (report or {}).get("brands_per_niche", {}),
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            return True
        except Exception as e:
            print(f"[mongo] write failed: {e}")
            return False

    def close(self):
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass