# Trial Score Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan.

**Goal:** Add a history-aware trial scoring mode before 28 valid archive days, then switch automatically to growth-only complete or partial momentum scoring.

**Architecture:** `run_pipeline.py` counts valid daily archive directories and passes `history_days` into the pure scoring function. The scorer chooses a source independently for each primary metric, computes cross-industry percentiles per metric, and aggregates available dimensions with normalized 35% / 65% weights. Static and FastAPI metadata derive the same three user-facing modes from persisted score rows, while GitHub Pages continues to read only `./data/*`.

**Tech Stack:** Python, pandas, pytest, static HTML/CSS/JavaScript, SQLite

---

### Task 1: Add History-Day Plumbing

**Files:**
- Modify: `scripts/common.py`
- Modify: `scripts/run_pipeline.py`
- Modify: `scripts/score_industries.py`
- Test: `tests/test_pipeline.py`
- Test: `tests/test_score_industries.py`

1. Add failing tests proving archive counting accepts only exact `YYYY-MM-DD` directories and `run_pipeline.py` passes the count into `score_industries()`.
2. Run:

   ```bash
   python -m pytest tests/test_pipeline.py tests/test_score_industries.py -v
   ```

   Expected: failure because `history_days` is not accepted or passed.
3. Add shared archive-date helpers in `scripts/common.py`.
4. Extend `score_industries(..., history_days=28)` so existing direct callers retain formal momentum behavior unless they explicitly request trial mode.
5. Make `run_pipeline.py` calculate the current valid archive count and pass it explicitly.
6. Re-run the focused tests and confirm they pass.

### Task 2: Implement Trial Scoring With Per-Metric Percentiles

**Files:**
- Modify: `scripts/score_industries.py`
- Test: `tests/test_score_industries.py`

1. Add failing tests for:
   - `history_days < 28` preferring valid `growth_rate_4w`;
   - trial fallback to latest usable daily value when growth is unavailable;
   - independent percentiles for differently scaled metrics;
   - invalid daily statuses remaining unavailable;
   - `history_days == 28` prohibiting latest-value fallback;
   - missing formal metrics producing partial momentum instead of zero scores;
   - source columns identifying `growth_rate_4w`, `latest_value`, or `unavailable`.
2. Run:

   ```bash
   python -m pytest tests/test_score_industries.py -v
   ```

   Expected: new assertions fail.
3. Refactor metric scoring so each primary metric selects its own eligible source series before percentile ranking.
4. Keep the minimum comparison group at three industries.
5. Preserve dimension aggregation and renormalize only across dimensions that have usable metric scores.
6. Persist:
   - `scoring_mode=试运行评分模式`, `ranking_status=trial` for ranked trial rows;
   - `scoring_mode=完整 momentum 模式`, `ranking_status=ranked` for complete formal rows;
   - `scoring_mode=部分 momentum 模式`, `ranking_status=partial` for incomplete formal rows.
7. Re-run the focused tests until green.

### Task 3: Keep Reports and Documentation Honest

**Files:**
- Modify: `scripts/generate_report.py`
- Modify: `README.md`
- Test: `tests/test_generate_report.py`

1. Add a failing report test requiring `试运行评分 / 历史不足，仅供观察` when the latest score rows are trial rows.
2. Run:

   ```bash
   python -m pytest tests/test_generate_report.py -v
   ```

   Expected: failure because reports currently describe growth-only scoring.
3. Make report methodology and status text conditional on persisted scoring mode.
4. Update README scoring documentation to describe:
   - trial fallback before 28 days;
   - per-metric percentiles;
   - the 28-day formal switch;
   - complete versus partial formal momentum;
   - no latest-value fallback after the switch.
5. Re-run the report tests.

### Task 4: Align Static and Dynamic Metadata

**Files:**
- Modify: `scripts/export_static.py`
- Modify: `web/app.py`
- Modify: `docs/index.html`
- Test: `tests/test_export_static.py`
- Test: `tests/test_web_app.py`
- Test: `tests/test_static_frontend.py`

1. Add failing tests proving:
   - trial score rows export as `ranking_mode=试运行评分模式`;
   - FastAPI metadata reports the same mode;
   - the static page contains the exact disclosure `试运行评分 / 历史不足，仅供观察`;
   - the disclosure is controlled by `meta.ranking_mode`;
   - the existing `archive_days / 28` progress remains present.
2. Run:

   ```bash
   python -m pytest tests/test_export_static.py tests/test_web_app.py tests/test_static_frontend.py -v
   ```

   Expected: new trial-mode assertions fail.
3. Centralize metadata mode derivation around row `scoring_mode` / `ranking_status` values, checking trial before complete or partial formal modes.
4. Add a visible trial disclosure card or badge in `docs/index.html` without introducing any new fetch path.
5. Keep every static fetch and download path under `./data/`.
6. Re-run the focused tests.

### Task 5: Refresh Artifacts and Verify End to End

**Files:**
- Modify if generated: `data/processed/industry_scores.csv`
- Modify if generated: `reports/*`
- Modify if generated: `docs/data/meta.json`
- Modify if generated: `docs/data/ranking.json`
- Modify if generated: `docs/data/history.csv`

1. Score the existing processed inputs with the current archive count, regenerate reports, store the scores, and export static data without rerunning collectors.
2. Run focused validation:

   ```bash
   python -m pytest tests/test_score_industries.py tests/test_pipeline.py tests/test_generate_report.py tests/test_export_static.py tests/test_web_app.py tests/test_static_frontend.py -v
   ```

3. Run the repository verification:

   ```bash
   python -m pytest -v
   python scripts/check_static_publish.py
   rg -n "/api/" docs/index.html
   ```

4. Confirm:
   - trial artifacts have non-null temporary rankings before day 28 when enough cross-sectional values exist;
   - `meta.json` reports trial mode and retains the progress count;
   - no `/api/` reference or credential signature exists under `docs/`.
5. Review the final diff for scope and commit the implementation separately from generated static data if those files changed.
