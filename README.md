# Brand Discovery Agent

Discovers brands that pay creators to promote them, across five niches: AI, SaaS, tech, health and wellness, tourism.

## Architecture

- `brand_discovery/` Python 3.11+ package (stdlib only).
- SQLite state in `data/brand_discovery.sqlite` (tables: channels, videos, brands, brand_evidence, queries, feedback, quota_log, runs, kv).
- Config in `config.toml`.
- Dry-run mode replays saved API responses from `fixtures/`.

## Setup

1. Set env vars: `YOUTUBE_API_KEY`, `WEB_SEARCH_API_KEY`.
2. Optional blocklist: `data/blocklist.txt` (one domain per line) of already-emailed brands.
3. Run `python -m brand_discovery seed` to seed starter queries.
4. Run `python -m brand_discovery run` (or `--dry-run`).

## Phases

- Phase 1: build system (this repo).
- Phase 2: evaluate detection on 100 labeled videos; require >=85% brand extraction accuracy before going live (`brand_discovery.eval`).
- Phase 3: 7-day warm-up, target 5-8/day (`warmup=true` in config).
- Phase 4: full operation, 15+/day.

## Operations

- Runs every 3-4 hours via cron/GitHub Actions/free cloud server.
- SQLite on persistent storage with backups (`brand_discovery.ops.backup_sqlite`).
- Daily CSV/Google Sheet in `reports/`.
- Heartbeat: `brand_discovery.ops.heartbeat_ok`.
- Kill switch: create `KILL` file to stop runs.

## YouTube quota

- 10,000 units/day, hard stop 8,000, search budget ~4,000.
- Quota resets midnight Pacific.
- If insufficient, request more via Google's official quota extension form. Never use extra projects to bypass.

## Testing

```
python -m unittest discover -s tests
```
