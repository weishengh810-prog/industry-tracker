# GitHub Pages Static Publishing Design

## Goal

Add a GitHub Pages-compatible static dashboard under `docs/` while retaining the
existing FastAPI application and its `/api/...` routes for ECS deployment.

## Architecture

The existing pipeline remains the source of truth:

```text
pipeline outputs
    -> scripts/store_to_db.py
    -> web/industry.db
    -> scripts/export_static.py
    -> docs/data/meta.json
    -> docs/data/ranking.json
    -> docs/data/history.csv
    -> docs/index.html
```

FastAPI continues to read `web/industry.db` and serve the dynamic dashboard.
GitHub Pages serves only files under `docs/`; its page never calls FastAPI.

## Static Data Contract

### `docs/data/meta.json`

Contains page-level state equivalent to the current `/api/meta` response:

- `last_updated`
- `ranking_mode`
- `insufficient_industries`
- `archive_days`
- `days_until_full_mode`

Archive progress counts valid `YYYY-MM-DD` archive directories.

### `docs/data/ranking.json`

Contains the latest score date's industries in ranking order. Each item contains:

- Latest score and ranking fields
- Score and ranking changes against the preceding score date
- `latest_metrics.daily_metrics`, containing the latest daily metric rows
- `latest_metrics.momentum_features`, containing the latest momentum feature rows

The stable nested structure avoids field-name collisions while preserving the
industry detail view without adding a fourth static data file or calling
`/api/industry/{name}`. The browser joins the two arrays by metric name when it
renders the latest metric status.

### `docs/data/history.csv`

Contains all rows from `industry_scores`, ordered by date and industry, with:

- `date`
- `industry`
- `composite_score`
- `ranking`
- `ranking_status`
- `capital_momentum_score`
- `tech_activity_score`
- `external_signal_score`
- `score_change`
- `ranking_change`

The static page parses this file in the browser for the history comparison chart
and per-industry 30-day detail chart, including optional component-score trends.
`score_change` and `ranking_change` compare each row with the preceding score
date for the same industry. The same file is the CSV download target.

## Export Behavior

`scripts/export_static.py` accepts optional database and output paths for tests,
with defaults of `web/industry.db` and `docs/data`.

The exporter:

1. Creates the output directory.
2. Reads SQLite directly without requiring FastAPI to run.
3. Writes deterministic, sorted output.
4. Uses UTF-8 JSON with `ensure_ascii=False`.
5. Replaces output files rather than appending, so repeated runs are idempotent.
6. Produces valid empty outputs when tables contain no data.
7. Fails clearly when the database file or required schema is unavailable.

The daily job runs `store_to_db.py` before export, so normal production execution
always refreshes SQLite from current pipeline artifacts first.

## Static Frontend

`docs/index.html` reuses the layout, colors, responsive behavior, Alpine.js, and
Chart.js structure of `web/static/index.html`.

It reads only:

- `./data/meta.json`
- `./data/ranking.json`
- `./data/history.csv`

All data and download paths are relative so the page works under a repository
subpath such as `/industry-tracker/`. The history CSV is parsed with a small
browser-side parser that handles quoted CSV fields.

The page retains:

- Last update
- Current scoring mode
- Archive accumulation progress
- Industry ranking cards
- Industry detail and 30-day score trend
- Multi-industry history comparison
- CSV history download

The dynamic FastAPI page remains unchanged and keeps its API-backed downloads.

## Daily Publishing

The existing `scripts/daily_update.sh` keeps its current pipeline, archive, and
artifact commit behavior. After pipeline completion it explicitly runs:

```bash
python scripts/store_to_db.py
python scripts/export_static.py
```

It stages `docs/` together with the existing daily artifacts. The current
`git commit ... || echo "No changes to commit"` behavior remains, and `git push`
runs afterward. No credentials are stored in the repository; ECS must use an SSH
deploy key or another securely configured Git credential.

Because GitHub Pages publishes `docs/` publicly, that directory contains only
the dashboard, generated public data, and non-sensitive documentation. Private
keys, tokens, passwords, server addresses, and deployment credentials must not
be written to `docs/` or any other tracked file.

## Testing

Tests cover:

- Creation and schema of all three static data files
- Chinese JSON text remaining unescaped
- Ranking changes and nested latest daily/momentum metric detail
- Complete, deterministic history export with component scores and changes
- Repeated export without duplicate rows or exceptions
- `docs/index.html` containing only `./data/...` fetch targets and no `/api/`
- Daily script ordering and no-change commit behavior
- Existing FastAPI tests remaining unchanged and passing

The final verification runs the focused new tests, then the complete pytest suite.

## Alternatives Considered

1. Add per-industry JSON files. This simplifies detail loading but violates the
   agreed three-file contract and increases generated file count.
2. Put all history and detail into `ranking.json`. This avoids CSV parsing but
   duplicates history data and weakens the direct CSV download requirement.
3. Use the selected design: embed only latest metric detail in `ranking.json`
   and keep score history in `history.csv`. This satisfies the three-file
   contract with minimal duplication.
