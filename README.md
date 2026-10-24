# Brand Discovery Agent

Discovers brands that pay creators to promote them, across five niches: AI, SaaS, tech, health and wellness, tourism.

## Architecture

- `brand_discovery/` Python 3.11+ package (stdlib only).
- SQLite state in `data/brand_discovery.sqlite` (tables: channels, videos, brands, brand_evidence, queries, feedback, quota_log, runs, kv).
- Config in `config.toml`.
- Dry-run mode replays saved API responses from `fixtures/`.

## Setup

1. Set env vars: `YOUTUBE_BACKEND` (official|scraper, default scraper), `YOUTUBE_BASE_URL` (default http://localhost:8080/youtube/v3), `WEB_SEARCH_API_KEY` (optional). For official backend, also set `YOUTUBE_API_KEY`.
2. Optional blocklist: `data/blocklist.txt` (one domain per line) of already-emailed brands.
3. Run `python -m brand_discovery seed` to seed starter queries.
4. Run `python -m brand_discovery run` (or `--dry-run`).

## Phases

- Phase 1: build system (this repo).
- Phase 2: evaluate detection on 100 labeled videos; require >=85% brand extraction accuracy before going live (`brand_discovery.eval`).
- Phase 3: 7-day warm-up, target 5-8/day (`warmup=true` in config).
- Phase 4: full operation, 15+/day.

## GitHub Actions (click-to-run)

The workflow file is provided as `github-workflow-run.yml` at repo root because the initial push token lacked the `workflow` scope. To enable "Run workflow":

1. In GitHub, open the repo -> Add file -> Create new file.
2. Name it `.github/workflows/run.yml`.
3. Paste the contents of `github-workflow-run.yml`.
4. Commit.
5. (Optional) Go to Settings -> Secrets and variables -> Actions, add `WEB_SEARCH_API_KEY`. YouTube uses the self-made scraper (no key).
6. Open Actions tab -> select "brand-discovery" -> Run workflow.

Alternatively, grant workflow scope locally and push:
```
gh auth refresh --scopes workflow
git mv github-workflow-run.yml .github/workflows/run.yml
git commit -m "Enable workflow"
git push
```

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
