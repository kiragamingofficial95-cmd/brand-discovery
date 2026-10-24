"""CLI entry point."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .config import Config
from .db import Database
from .quota import QuotaManager
from .youtube import YouTubeClient
from .web_search import WebSearchClient
from .http import Fetcher
from .blocklist import Blocklist
from .pipeline import Pipeline


def build_components(config_path="config.toml", dry_run=False):
    cfg = Config.load(config_path)
    db_path = cfg.app.get("db_path", "data/brand_discovery.sqlite")
    db = Database(db_path)
    yt_quota = QuotaManager(db, cfg, "youtube")
    web_quota = QuotaManager(db, cfg, "web")
    yt = YouTubeClient(
        api_key=os.environ.get("YOUTUBE_API_KEY", ""),
        quota=yt_quota,
        dry_run=dry_run or cfg.app.get("dry_run", False),
        fixtures_dir=cfg.app.get("dry_run_fixtures_dir", "fixtures"),
    )
    web = WebSearchClient(
        config=cfg, db=db, quota=web_quota,
        api_key=os.environ.get("WEB_SEARCH_API_KEY", ""),
        dry_run=dry_run or cfg.app.get("dry_run", False),
        fixtures_dir=cfg.app.get("dry_run_fixtures_dir", "fixtures"),
    )
    fetcher = Fetcher(cfg, cache_dir=cfg.app.get("cache_dir", "cache"))
    blocklist = Blocklist(cfg.app.get("blocklist_path", "data/blocklist.txt"))
    return cfg, db, yt, web, fetcher, blocklist


def cmd_run(args):
    cfg, db, yt, web, fetcher, blocklist = build_components(args.config, args.dry_run)
    # kill switch
    if Path("KILL").exists():
        print("Kill switch active (KILL file present). Aborting.")
        return
    pipe = Pipeline(cfg, db, yt, web, fetcher, blocklist, dry_run=args.dry_run)
    result = pipe.run()
    print(f"Run complete: {result['brands_found']} brands found")
    # write CSV
    import csv
    reports_dir = Path(cfg.app.get("reports_dir", "reports"))
    reports_dir.mkdir(parents=True, exist_ok=True)
    out = reports_dir / f"report_{datetime_now()}.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "website", "niche", "sub_niche", "score", "older_evidence"])
        for b in result["accepted"]:
            w.writerow([b.get("name"), b.get("website"), b.get("niche"), b.get("sub_niche"), b.get("score"), b.get("older_evidence")])
    print(f"CSV written: {out}")


def datetime_now():
    from datetime import datetime
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")


def cmd_seed(args):
    cfg, db, *_ = build_components(args.config, True)
    from .expansion import seed_queries
    n = seed_queries(db, cfg)
    print(f"Seeded {n} queries")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="brand-discovery")
    parser.add_argument("--config", default="config.toml")
    sub = parser.add_subparsers(dest="cmd")
    r = sub.add_parser("run")
    r.add_argument("--dry-run", action="store_true")
    r.set_defaults(func=cmd_run)
    s = sub.add_parser("seed")
    s.set_defaults(func=cmd_seed)
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
