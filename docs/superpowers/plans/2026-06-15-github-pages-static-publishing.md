# GitHub Pages Static Publishing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export the existing SQLite-backed dashboard into three deterministic public data files and serve a GitHub Pages dashboard from `docs/` without changing the FastAPI API or ECS deployment.

**Architecture:** `scripts/export_static.py` reads `web/industry.db` directly and writes `meta.json`, `ranking.json`, and `history.csv`. The static page loads only relative `./data/...` paths, derives detail/history charts in the browser, and keeps the dynamic FastAPI application untouched. The existing daily shell script refreshes SQLite, exports the static site, and commits only when staged files changed.

**Tech Stack:** Python 3.10+, SQLite, standard-library JSON/CSV, pandas tests, Alpine.js, Chart.js, pytest, Bash, GitHub Pages.

---

## File Map

- Create `scripts/export_static.py`: deterministic SQLite-to-static export and CLI.
- Create `tests/test_export_static.py`: exporter contract, Unicode, nested metrics, changes, and idempotency.
- Create `docs/index.html`: GitHub Pages dashboard using only relative static data.
- Create `tests/test_static_frontend.py`: static path, feature, and API-isolation assertions.
- Create `docs/data/meta.json`: generated page metadata.
- Create `docs/data/ranking.json`: generated latest ranking with nested metric arrays.
- Create `docs/data/history.csv`: generated complete score history.
- Modify `scripts/daily_update.sh`: refresh DB, export static files, stage `docs/`, and conditionally commit/push.
- Create `tests/test_daily_update_script.py`: shell workflow ordering and no-change behavior.
- Modify `tests/test_entrypoints.py`: verify `export_static.py --help`.
- Modify `README.md`: dynamic/static deployment, Pages setup, manual export, cron, and credential safety.
- Modify `docs/superpowers/specs/2026-06-15-github-pages-static-publishing-design.md`: approved data-contract refinements.

### Task 1: Static Exporter

**Files:**
- Create: `tests/test_export_static.py`
- Create: `scripts/export_static.py`
- Modify: `tests/test_entrypoints.py`

- [ ] **Step 1: Write failing exporter tests**

Create a temporary SQLite database with `SCHEMA`, two score dates, latest daily
metrics, and latest momentum metrics. Call the wished-for API twice:

```python
from scripts.export_static import export_static

outputs = export_static(
    db_path,
    output_dir=tmp_path / "docs" / "data",
    project_root=tmp_path,
)
export_static(
    db_path,
    output_dir=tmp_path / "docs" / "data",
    project_root=tmp_path,
)
```

Assert:

```python
assert set(outputs) == {"meta", "ranking", "history"}
assert json.loads(outputs["meta"].read_text("utf-8"))["last_updated"] == "2026-06-14"
assert "人工智能" in outputs["ranking"].read_text("utf-8")
assert "\\u4eba" not in outputs["ranking"].read_text("utf-8")
assert ranking[0]["latest_metrics"] == {
    "daily_metrics": [...],
    "momentum_features": [...],
}
assert history.columns.tolist() == [
    "date",
    "industry",
    "composite_score",
    "ranking",
    "ranking_status",
    "capital_momentum_score",
    "tech_activity_score",
    "external_signal_score",
    "score_change",
    "ranking_change",
]
assert len(history) == expected_rows
```

Also assert `score_change = current - previous`, `ranking_change = previous -
current`, valid archive-directory counting, empty-table outputs, and direct CLI
availability by adding `export_static.py` to `tests/test_entrypoints.py`.

- [ ] **Step 2: Run exporter tests and verify RED**

Run:

```bash
python -m pytest tests/test_export_static.py tests/test_entrypoints.py -v
```

Expected: collection fails because `scripts.export_static` does not exist.

- [ ] **Step 3: Implement the minimal exporter**

Implement:

```python
HISTORY_COLUMNS = [
    "date",
    "industry",
    "composite_score",
    "ranking",
    "ranking_status",
    "capital_momentum_score",
    "tech_activity_score",
    "external_signal_score",
    "score_change",
    "ranking_change",
]


def export_static(
    db_path: Path | str = DEFAULT_DB_PATH,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    project_root: Path | str = PROJECT_ROOT,
) -> dict[str, Path]:
    target_db = Path(db_path).resolve()
    target_dir = Path(output_dir).resolve()
    root = Path(project_root).resolve()
    if not target_db.exists():
        raise FileNotFoundError(f"SQLite database not found: {target_db}")
    target_dir.mkdir(parents=True, exist_ok=True)

    history = _history_rows(target_db)
    ranking = _latest_ranking(target_db, history)
    meta = _meta(target_db, root)

    _write_json(target_dir / "meta.json", meta)
    _write_json(target_dir / "ranking.json", ranking)
    _write_history(target_dir / "history.csv", history)
    return {
        "meta": target_dir / "meta.json",
        "ranking": target_dir / "ranking.json",
        "history": target_dir / "history.csv",
    }
```

Use `sqlite3.Row`, deterministic `ORDER BY`, `json.dump(..., ensure_ascii=False,
indent=2)`, and `csv.DictWriter`. Calculate changes by keeping the preceding row
per industry. Build each ranking item's nested details as:

```python
"latest_metrics": {
    "daily_metrics": _latest_daily_metrics(db_path, industry),
    "momentum_features": _latest_momentum_features(db_path, industry),
}
```

Add `--db`, `--output-dir`, and `--project-root` argparse options.

- [ ] **Step 4: Run exporter tests and verify GREEN**

Run:

```bash
python -m pytest tests/test_export_static.py tests/test_entrypoints.py -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit exporter**

```bash
git add scripts/export_static.py tests/test_export_static.py tests/test_entrypoints.py
git commit -m "feat: export dashboard data for GitHub Pages"
```

### Task 2: Static Dashboard

**Files:**
- Create: `tests/test_static_frontend.py`
- Create: `docs/index.html`

- [ ] **Step 1: Write failing static frontend tests**

Assert that `docs/index.html`:

```python
assert 'fetch("./data/meta.json")' in html
assert 'fetch("./data/ranking.json")' in html
assert 'fetch("./data/history.csv")' in html
assert 'href="./data/history.csv"' in html
assert "/api/" not in html
assert "latest_metrics.daily_metrics" in html
assert "latest_metrics.momentum_features" in html
assert "capital_momentum_score" in html
assert "tech_activity_score" in html
assert "最后更新" in html
assert "当前评分模式" in html
assert "历史积累进度" in html
assert "historyChart" in html
assert "detailChart" in html
```

- [ ] **Step 2: Run frontend test and verify RED**

Run:

```bash
python -m pytest tests/test_static_frontend.py -v
```

Expected: fail because `docs/index.html` does not exist.

- [ ] **Step 3: Create the static page from the existing visual design**

Reuse the CSS and layout from `web/static/index.html`. Replace initialization
with:

```javascript
const [meta, ranking, historyText] = await Promise.all([
  this.fetchJson("./data/meta.json"),
  this.fetchJson("./data/ranking.json"),
  this.fetchText("./data/history.csv")
]);
this.meta = meta;
this.ranking = ranking;
this.history = this.parseCsv(historyText);
```

Implement a quote-aware CSV parser, convert blank numeric fields to `null`, and
convert the score/ranking/component/change columns to numbers. Build detail data
locally:

```javascript
const rankingItem = this.ranking.find(
  item => item.industry === this.selectedIndustry
);
const momentumByMetric = new Map(
  (rankingItem?.latest_metrics?.momentum_features || [])
    .map(item => [item.metric, item])
);
this.detail.latest_metrics = (
  rankingItem?.latest_metrics?.daily_metrics || []
).map(item => ({ ...item, ...(momentumByMetric.get(item.metric) || {}) }));
this.detail.score_history_30d = this.history
  .filter(item => item.industry === this.selectedIndustry)
  .slice(-30);
```

Render composite, capital momentum, and tech activity as separate detail chart
datasets. Use only relative links and keep the history CSV download at
`./data/history.csv`.

- [ ] **Step 4: Run frontend tests and verify GREEN**

Run:

```bash
python -m pytest tests/test_static_frontend.py tests/test_web_frontend.py -v
```

Expected: static and existing dynamic frontend tests pass.

- [ ] **Step 5: Commit static page**

```bash
git add docs/index.html tests/test_static_frontend.py
git commit -m "feat: add GitHub Pages dashboard"
```

### Task 3: Daily Static Publishing

**Files:**
- Create: `tests/test_daily_update_script.py`
- Modify: `scripts/daily_update.sh`

- [ ] **Step 1: Write failing daily script tests**

Read the shell script and assert:

```python
assert "python scripts/store_to_db.py" in script
assert "python scripts/export_static.py" in script
assert script.index("python scripts/run_pipeline.py") < script.index(
    "python scripts/store_to_db.py"
)
assert script.index("python scripts/store_to_db.py") < script.index(
    "python scripts/export_static.py"
)
assert "docs/" in script
assert "git diff --cached --quiet" in script
assert script.index("git commit") < script.index("git push")
```

- [ ] **Step 2: Run daily script test and verify RED**

Run:

```bash
python -m pytest tests/test_daily_update_script.py -v
```

Expected: fail because the export and conditional commit logic are absent.

- [ ] **Step 3: Extend the existing shell workflow**

Immediately after the pipeline command add:

```bash
python scripts/store_to_db.py
python scripts/export_static.py
```

Add `docs/` to the existing `git add` command. Replace unconditional commit/push
with:

```bash
if git diff --cached --quiet; then
  echo "No changes to commit"
else
  git commit -m "Daily update industry tracker report ${TODAY}"
  git push
fi
```

Keep the current `cd`, virtualenv activation, archive creation, copies, and
artifact staging intact.

- [ ] **Step 4: Run daily script tests and verify GREEN**

Run:

```bash
python -m pytest tests/test_daily_update_script.py tests/test_web_deploy_config.py -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit publishing workflow**

```bash
git add scripts/daily_update.sh tests/test_daily_update_script.py
git commit -m "feat: publish static dashboard after daily pipeline"
```

### Task 4: Documentation and Generated Public Data

**Files:**
- Modify: `README.md`
- Create: `docs/data/meta.json`
- Create: `docs/data/ranking.json`
- Create: `docs/data/history.csv`

- [ ] **Step 1: Add documentation assertions**

Extend `tests/test_static_frontend.py` or add a focused README test asserting the
README contains:

```python
assert "Settings" in readme
assert "Pages" in readme
assert "/docs" in readme
assert "FastAPI" in readme
assert "GitHub Pages" in readme
assert "SSH deploy key" in readme
assert "python scripts/export_static.py" in readme
assert "token" in readme.lower()
```

- [ ] **Step 2: Run the documentation test and verify RED**

Run:

```bash
python -m pytest tests/test_static_frontend.py -v
```

Expected: fail because deployment documentation is missing.

- [ ] **Step 3: Document operation and security**

Add README sections that explain:

- FastAPI dynamic API remains deployed on ECS.
- GitHub Pages is read-only and uses committed `docs/data/*`.
- Manual export:

```bash
python scripts/store_to_db.py
python scripts/export_static.py
```

- Pages setup: repository `Settings` -> `Pages`, select the current branch and
  `/docs` folder.
- Daily cron runs `scripts/daily_update.sh`.
- ECS push requires an SSH deploy key or another secure credential configured
  outside the repository.
- Private keys, tokens, passwords, and server credentials must never be written
  to tracked files or the public `docs/` directory.

- [ ] **Step 4: Generate the initial public data**

Run:

```bash
python scripts/store_to_db.py
python scripts/export_static.py
```

Inspect all three files and confirm they contain only public industry data and no
credential-like content.

- [ ] **Step 5: Run documentation and exporter tests**

Run:

```bash
python -m pytest tests/test_export_static.py tests/test_static_frontend.py -v
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit documentation and generated data**

```bash
git add README.md docs/data tests/test_static_frontend.py
git commit -m "docs: document GitHub Pages deployment"
```

### Task 5: Full Verification

**Files:**
- Verify all modified and created files.

- [ ] **Step 1: Verify no static API calls or secrets**

Run:

```bash
rg -n "/api/" docs/index.html
rg -n "PRIVATE KEY|BEGIN OPENSSH|ghp_|github_pat_|password\\s*=|token\\s*=" docs
```

Expected: both commands return no matches.

- [ ] **Step 2: Run the complete test suite**

Run:

```bash
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 3: Check the final diff**

Run:

```bash
git diff --check
git status --short --branch
```

Expected: no whitespace errors; only intentional implementation changes remain.

- [ ] **Step 4: Confirm FastAPI and ECS deployment are retained**

Run:

```bash
git diff 4dc180f -- web/app.py deploy/industry-tracker.service deploy/nginx.conf
```

Expected: no deletions or replacements of the dynamic API or ECS deployment
configuration.
