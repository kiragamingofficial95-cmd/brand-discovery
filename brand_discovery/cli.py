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


def build_components(config_path="config.toml", dry_run=False, fast=False):
    cfg = Config.load(config_path)
    # apply fast mode limits
    if fast:
        cfg.raw.setdefault("quotas", {})
        cfg.raw["quotas"]["max_youtube_searches_per_run"] = 8
        cfg.raw["quotas"]["max_queries_per_run"] = 5
        cfg.raw["quotas"]["scraper_request_timeout_seconds"] = 15
        cfg.raw["quotas"]["scraper_max_retries"] = 1
        cfg.raw["thresholds"] = cfg.raw.get("thresholds", {})
        cfg.raw["thresholds"]["min_score"] = 10
        cfg.raw["thresholds"]["scraper_min_score"] = 10
    db_path = cfg.app.get("db_path", "data/brand_discovery.sqlite")
    db = Database(db_path)
    backend = os.environ.get("YOUTUBE_BACKEND", cfg.youtube.get("backend", "official"))
    base_url = os.environ.get("YOUTUBE_BASE_URL", cfg.youtube.get("base_url", "https://www.googleapis.com/youtube/v3"))
    use_key = backend == "official"
    enforce_quota = backend == "official"
    yt_quota = QuotaManager(db, cfg, "youtube", enforce=enforce_quota)
    web_quota = QuotaManager(db, cfg, "web")
    yt = YouTubeClient(
        api_key=os.environ.get("YOUTUBE_API_KEY", "") if use_key else "",
        quota=yt_quota,
        dry_run=dry_run or cfg.app.get("dry_run", False),
        fixtures_dir=cfg.app.get("dry_run_fixtures_dir", "fixtures"),
        base_url=base_url,
        use_api_key=use_key,
        timeout=int(cfg.quotas.get("scraper_request_timeout_seconds", 20)) if not use_key else 30,
        max_retries=int(cfg.quotas.get("scraper_max_retries", 2)) if not use_key else 5,
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
    cfg, db, yt, web, fetcher, blocklist = build_components(args.config, args.dry_run, args.fast)
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
    # write latest.json for dashboard
    import json
    docs_data = Path(cfg.app.get("reports_dir", "reports")).parent / "docs" / "data"
    if not docs_data.exists():
        docs_data = Path("docs/data")
    docs_data.mkdir(parents=True, exist_ok=True)
    (docs_data / "latest.json").write_text(json.dumps(result["report"], indent=2, default=str), encoding="utf-8")
    print(f"Dashboard data written: {docs_data / 'latest.json'}")
    if getattr(args, "serve", False):
        _serve_dashboard(docs_data.parent.parent, getattr(args, "port", 8000), open_browser=True,
                        tunnel=not getattr(args, "no_tunnel", False))


def datetime_now():
    from datetime import datetime
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")


def cmd_seed(args):
    cfg, db, *_ = build_components(args.config, True)
    from .expansion import seed_queries
    n = seed_queries(db, cfg)
    print(f"Seeded {n} queries")


def _start_tunnel(port: int):
    """Start a temporary public tunnel (cloudflared or localtunnel). Returns (proc, url)."""
    import subprocess, shutil, re, time, threading
    # try cloudflared
    cf = shutil.which("cloudflared")
    if cf:
        proc = subprocess.Popen([cf, "tunnel", "--url", f"http://localhost:{port}"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        url = _capture_url(proc, r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", timeout=30)
        if url:
            return proc, url
        proc.terminate()
    # try npx localtunnel
    npx = shutil.which("npx")
    if npx:
        proc = subprocess.Popen([npx, "--yes", "localtunnel", "--port", str(port)],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        url = _capture_url(proc, r"https://[a-zA-Z0-9-]+\.loca\.lt", timeout=40)
        if url:
            return proc, url
        proc.terminate()
    return None, None


def _capture_url(proc, pattern, timeout=30):
    import re, time
    deadline = time.time() + timeout
    buf = ""
    while time.time() < deadline:
        # read available
        try:
            line = proc.stdout.readline()
        except Exception:
            line = ""
        if line:
            buf += line
            m = re.search(pattern, buf)
            if m:
                return m.group(0)
        else:
            time.sleep(0.5)
            if proc.poll() is not None:
                break
    m = re.search(pattern, buf)
    return m.group(0) if m else None


def _serve_dashboard(docs_dir: Path, port: int = 8000, open_browser: bool = False, tunnel: bool = True):
    import http.server, socketserver, webbrowser, threading, time
    docs_dir = Path(docs_dir)
    if not docs_dir.exists():
        docs_dir.mkdir(parents=True, exist_ok=True)
    handler = http.server.SimpleHTTPRequestHandler
    class H(handler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(docs_dir), **kw)
    httpd = socketserver.TCPServer(("", port), H)
    local_url = f"http://localhost:{port}/"
    print(f"Dashboard local at {local_url}")
    public_url = None
    tunnel_proc = None
    if tunnel:
        tunnel_proc, public_url = _start_tunnel(port)
        if public_url:
            print(f"Dashboard public (temp) at {public_url}")
            if open_browser:
                threading.Timer(1.0, lambda: webbrowser.open(public_url)).start()
        else:
            print("No tunnel tool found (install cloudflared or npx). Using local URL.")
            if open_browser:
                threading.Timer(1.0, lambda: webbrowser.open(local_url)).start()
    else:
        if open_browser:
            threading.Timer(1.0, lambda: webbrowser.open(local_url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()
        if tunnel_proc:
            tunnel_proc.terminate()


def cmd_serve(args):
    cfg, *_ = build_components(args.config, True)
    docs_dir = Path(cfg.app.get("reports_dir", "reports")).parent / "docs"
    if not docs_dir.exists():
        docs_dir = Path("docs")
    _serve_dashboard(docs_dir, args.port, open_browser=not args.no_browser,
                    tunnel=not getattr(args, "no_tunnel", False))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="brand-discovery")
    parser.add_argument("--config", default="config.toml")
    sub = parser.add_subparsers(dest="cmd")
    r = sub.add_parser("run")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--serve", action="store_true", help="Start local dashboard after run")
    r.add_argument("--port", type=int, default=8000)
    r.add_argument("--no-tunnel", action="store_true", help="Disable public tunnel")
    r.add_argument("--fast", action="store_true", help="Fast mode: fewer queries, lower threshold")
    r.set_defaults(func=cmd_run)
    s = sub.add_parser("seed")
    s.set_defaults(func=cmd_seed)
    sv = sub.add_parser("serve")
    sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("--no-browser", action="store_true")
    sv.add_argument("--no-tunnel", action="store_true")
    sv.set_defaults(func=cmd_serve)
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
