"""Operations helpers: heartbeat, kill switch, backups."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional


KILL_FILE = "KILL"


def kill_switch_active() -> bool:
    return Path(KILL_FILE).exists()


def create_kill_switch() -> None:
    Path(KILL_FILE).write_text("stopped", encoding="utf-8")


def remove_kill_switch() -> None:
    p = Path(KILL_FILE)
    if p.exists():
        p.unlink()


def backup_sqlite(db_path: str, backup_dir: str = "backups") -> Optional[str]:
    src = Path(db_path)
    if not src.exists():
        return None
    d = Path(backup_dir)
    d.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    dst = d / f"{src.name}.{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.bak"
    shutil.copy2(src, dst)
    return str(dst)


def prune_youtube_data(db, max_age_days: int = 30) -> int:
    """Delete raw video rows older than max_age_days per YouTube API storage limits."""
    from datetime import datetime, timedelta
    cutoff = (datetime.utcnow() - timedelta(days=max_age_days)).isoformat()
    with db.conn() as c:
        cur = c.execute("DELETE FROM videos WHERE published_at IS NOT NULL AND published_at < ?", (cutoff,))
        return cur.rowcount


def heartbeat_ok(db) -> bool:
    # check last run within expected interval (run every 3-4 hours)
    runs = db.list_runs(limit=1)
    if not runs:
        return False
    last = runs[0]
    if last.get("status") != "success":
        return False
    return True
