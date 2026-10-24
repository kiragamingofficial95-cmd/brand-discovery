"""SQLite persistence layer."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
    channel_id TEXT PRIMARY KEY,
    title TEXT,
    niche TEXT,
    sub_niche TEXT,
    uploads_playlist TEXT,
    subscriber_count INTEGER DEFAULT 0,
    video_count INTEGER DEFAULT 0,
    last_scanned TEXT,
    scan_interval_days INTEGER DEFAULT 5,
    featured_channels TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY,
    channel_id TEXT,
    title TEXT,
    description TEXT,
    published_at TEXT,
    paid_product_placement INTEGER DEFAULT 0,
    tags TEXT DEFAULT '[]',
    sponsor_detected INTEGER DEFAULT 0,
    sponsor_brands TEXT DEFAULT '[]',
    pinned_comment TEXT DEFAULT '',
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS brands (
    domain TEXT PRIMARY KEY,
    name TEXT,
    niche TEXT,
    sub_niche TEXT,
    website TEXT,
    score INTEGER DEFAULT 0,
    saturated INTEGER DEFAULT 0,
    older_evidence INTEGER DEFAULT 0,
    creators_90d INTEGER DEFAULT 0,
    sponsor_count INTEGER DEFAULT 0,
    momentum REAL DEFAULT 0.0,
    first_seen TEXT,
    last_reported TEXT,
    report_count INTEGER DEFAULT 0,
    evidence_json TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS brand_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_domain TEXT,
    url TEXT,
    date TEXT,
    strength TEXT,
    source_type TEXT,
    note TEXT,
    checked_in_run INTEGER DEFAULT 0,
    FOREIGN KEY (brand_domain) REFERENCES brands(domain)
);

CREATE TABLE IF NOT EXISTS queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT,
    niche TEXT,
    sub_niche TEXT,
    source TEXT,
    created_at TEXT,
    last_run TEXT,
    runs INTEGER DEFAULT 0,
    poor_runs INTEGER DEFAULT 0,
    new_brands_per_100_units REAL DEFAULT 0.0,
    retired INTEGER DEFAULT 0,
    depth INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_domain TEXT,
    mark TEXT,
    note TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS quota_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    service TEXT,
    operation TEXT,
    units INTEGER,
    run_id INTEGER
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT,
    finished_at TEXT,
    status TEXT,
    youtube_units INTEGER DEFAULT 0,
    web_calls INTEGER DEFAULT 0,
    brands_found INTEGER DEFAULT 0,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def conn(self):
        c = self._connect()
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def _init(self):
        with self.conn() as c:
            c.executescript(SCHEMA)

    # ---- channels ----
    def upsert_channel(self, ch: Dict[str, Any]) -> None:
        with self.conn() as c:
            c.execute(
                """INSERT INTO channels(channel_id,title,niche,sub_niche,uploads_playlist,subscriber_count,video_count,last_scanned,scan_interval_days,featured_channels)
                   VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(channel_id) DO UPDATE SET
                     title=excluded.title, niche=excluded.niche, sub_niche=excluded.sub_niche,
                     uploads_playlist=excluded.uploads_playlist, subscriber_count=excluded.subscriber_count,
                     video_count=excluded.video_count, last_scanned=excluded.last_scanned,
                     scan_interval_days=excluded.scan_interval_days, featured_channels=excluded.featured_channels""",
                (
                    ch["channel_id"], ch.get("title", ""), ch.get("niche", ""), ch.get("sub_niche", ""),
                    ch.get("uploads_playlist", ""), ch.get("subscriber_count", 0), ch.get("video_count", 0),
                    ch.get("last_scanned"), ch.get("scan_interval_days", 5),
                    json.dumps(ch.get("featured_channels", [])),
                ),
            )

    def get_channel(self, channel_id: str) -> Optional[Dict[str, Any]]:
        with self.conn() as c:
            r = c.execute("SELECT * FROM channels WHERE channel_id=?", (channel_id,)).fetchone()
            return dict(r) if r else None

    def list_channels(self, niche: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.conn() as c:
            if niche:
                rows = c.execute("SELECT * FROM channels WHERE niche=?", (niche,)).fetchall()
            else:
                rows = c.execute("SELECT * FROM channels").fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["featured_channels"] = json.loads(d.get("featured_channels") or "[]")
                out.append(d)
            return out

    def channels_due_for_rescan(self, now_iso: str) -> List[Dict[str, Any]]:
        rows = self.list_channels()
        out = []
        for ch in rows:
            last = ch.get("last_scanned")
            if last is None:
                out.append(ch)
                continue
            # simple day diff via date
            try:
                from datetime import datetime as dt
                d0 = dt.fromisoformat(last.replace("Z", "+00:00"))
                d1 = dt.fromisoformat(now_iso.replace("Z", "+00:00"))
                days = (d1 - d0).days
            except Exception:
                days = 999
            if days >= ch.get("scan_interval_days", 5):
                out.append(ch)
        return out

    # ---- videos ----
    def upsert_video(self, v: Dict[str, Any]) -> None:
        with self.conn() as c:
            c.execute(
                """INSERT INTO videos(video_id,channel_id,title,description,published_at,paid_product_placement,tags,sponsor_detected,sponsor_brands,pinned_comment,raw_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(video_id) DO UPDATE SET
                     title=excluded.title, description=excluded.description, published_at=excluded.published_at,
                     paid_product_placement=excluded.paid_product_placement, tags=excluded.tags,
                     sponsor_detected=excluded.sponsor_detected, sponsor_brands=excluded.sponsor_brands,
                     pinned_comment=excluded.pinned_comment, raw_json=excluded.raw_json""",
                (
                    v["video_id"], v.get("channel_id"), v.get("title", ""), v.get("description", ""),
                    v.get("published_at"), 1 if v.get("paid_product_placement") else 0,
                    json.dumps(v.get("tags", [])), 1 if v.get("sponsor_detected") else 0,
                    json.dumps(v.get("sponsor_brands", [])), v.get("pinned_comment", ""),
                    json.dumps(v.get("raw_json", {})),
                ),
            )

    def list_videos(self, channel_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.conn() as c:
            if channel_id:
                rows = c.execute("SELECT * FROM videos WHERE channel_id=?", (channel_id,)).fetchall()
            else:
                rows = c.execute("SELECT * FROM videos").fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["tags"] = json.loads(d.get("tags") or "[]")
                d["sponsor_brands"] = json.loads(d.get("sponsor_brands") or "[]")
                d["paid_product_placement"] = bool(d.get("paid_product_placement"))
                d["sponsor_detected"] = bool(d.get("sponsor_detected"))
                out.append(d)
            return out

    # ---- brands ----
    def upsert_brand(self, b: Dict[str, Any]) -> None:
        with self.conn() as c:
            c.execute(
                """INSERT INTO brands(domain,name,niche,sub_niche,website,score,saturated,older_evidence,creators_90d,sponsor_count,momentum,first_seen,last_reported,report_count,evidence_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(domain) DO UPDATE SET
                     name=excluded.name, niche=excluded.niche, sub_niche=excluded.sub_niche, website=excluded.website,
                     score=excluded.score, saturated=excluded.saturated, older_evidence=excluded.older_evidence,
                     creators_90d=excluded.creators_90d, sponsor_count=excluded.sponsor_count,
                     momentum=excluded.momentum, last_reported=excluded.last_reported,
                     report_count=excluded.report_count, evidence_json=excluded.evidence_json""",
                (
                    b["domain"], b.get("name", ""), b.get("niche", ""), b.get("sub_niche", ""),
                    b.get("website", ""), b.get("score", 0), 1 if b.get("saturated") else 0,
                    1 if b.get("older_evidence") else 0, b.get("creators_90d", 0), b.get("sponsor_count", 0),
                    b.get("momentum", 0.0), b.get("first_seen"), b.get("last_reported"), b.get("report_count", 0),
                    json.dumps(b.get("evidence", [])),
                ),
            )

    def get_brand(self, domain: str) -> Optional[Dict[str, Any]]:
        with self.conn() as c:
            r = c.execute("SELECT * FROM brands WHERE domain=?", (domain.lower(),)).fetchone()
            if not r:
                return None
            d = dict(r)
            d["evidence"] = json.loads(d.get("evidence_json") or "[]")
            d["saturated"] = bool(d.get("saturated"))
            d["older_evidence"] = bool(d.get("older_evidence"))
            return d

    def list_brands(self) -> List[Dict[str, Any]]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM brands").fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["evidence"] = json.loads(d.get("evidence_json") or "[]")
                d["saturated"] = bool(d.get("saturated"))
                d["older_evidence"] = bool(d.get("older_evidence"))
                out.append(d)
            return out

    def add_evidence(self, brand_domain: str, ev: Dict[str, Any]) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO brand_evidence(brand_domain,url,date,strength,source_type,note,checked_in_run) VALUES(?,?,?,?,?,?,?)",
                (brand_domain, ev.get("url"), ev.get("date"), ev.get("strength"), ev.get("source_type"), ev.get("note", ""), 1 if ev.get("checked_in_run") else 0),
            )

    # ---- queries ----
    def insert_query(self, q: Dict[str, Any]) -> int:
        with self.conn() as c:
            cur = c.execute(
                "INSERT INTO queries(text,niche,sub_niche,source,created_at,last_run,runs,poor_runs,new_brands_per_100_units,retired,depth) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (q.get("text"), q.get("niche"), q.get("sub_niche"), q.get("source", "youtube"),
                 q.get("created_at"), q.get("last_run"), q.get("runs", 0), q.get("poor_runs", 0),
                 q.get("new_brands_per_100_units", 0.0), 1 if q.get("retired") else 0, q.get("depth", 0)),
            )
            return cur.lastrowid

    def list_queries(self, source: Optional[str] = None, retired: Optional[bool] = None) -> List[Dict[str, Any]]:
        with self.conn() as c:
            sql = "SELECT * FROM queries"
            params: List[Any] = []
            conds = []
            if source is not None:
                conds.append("source=?")
                params.append(source)
            if retired is not None:
                conds.append("retired=?")
                params.append(1 if retired else 0)
            if conds:
                sql += " WHERE " + " AND ".join(conds)
            rows = c.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def update_query(self, qid: int, **fields: Any) -> None:
        if not fields:
            return
        cols = []
        vals = []
        for k, v in fields.items():
            if k in ("retired",):
                v = 1 if v else 0
            cols.append(f"{k}=?")
            vals.append(v)
        vals.append(qid)
        with self.conn() as c:
            c.execute(f"UPDATE queries SET {','.join(cols)} WHERE id=?", vals)

    # ---- feedback ----
    def add_feedback(self, brand_domain: str, mark: str, note: str = "") -> None:
        with self.conn() as c:
            c.execute("INSERT INTO feedback(brand_domain,mark,note,created_at) VALUES(?,?,?,?)",
                      (brand_domain, mark, note, datetime.utcnow().isoformat()))

    def list_feedback(self) -> List[Dict[str, Any]]:
        with self.conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM feedback").fetchall()]

    # ---- quota log ----
    def log_quota(self, service: str, operation: str, units: int, run_id: Optional[int] = None) -> None:
        with self.conn() as c:
            c.execute("INSERT INTO quota_log(ts,service,operation,units,run_id) VALUES(?,?,?,?,?)",
                      (datetime.utcnow().isoformat(), service, operation, units, run_id))

    def quota_used_today(self, service: str, since_iso: str) -> int:
        with self.conn() as c:
            r = c.execute("SELECT COALESCE(SUM(units),0) FROM quota_log WHERE service=? AND ts>=?", (service, since_iso)).fetchone()
            return int(r[0]) if r else 0

    # ---- runs ----
    def start_run(self) -> int:
        with self.conn() as c:
            cur = c.execute("INSERT INTO runs(started_at,status) VALUES(?,?)", (datetime.utcnow().isoformat(), "running"))
            return cur.lastrowid

    def finish_run(self, run_id: int, status: str, yt_units: int, web_calls: int, brands_found: int, notes: str = "") -> None:
        with self.conn() as c:
            c.execute("UPDATE runs SET finished_at=?,status=?,youtube_units=?,web_calls=?,brands_found=?,notes=? WHERE id=?",
                      (datetime.utcnow().isoformat(), status, yt_units, web_calls, brands_found, notes, run_id))

    def list_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self.conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]

    # ---- kv (state flags) ----
    def kv_get(self, key: str) -> Optional[str]:
        with self.conn() as c:
            r = c.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
            return r["value"] if r else None

    def kv_set(self, key: str, value: str) -> None:
        with self.conn() as c:
            c.execute("INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
