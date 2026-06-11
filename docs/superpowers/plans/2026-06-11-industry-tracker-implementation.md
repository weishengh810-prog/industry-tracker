# Industry Tracker MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a configurable, degradable Python pipeline that collects news, policy, and market-proxy data for 12 industries and produces a scored CSV, Markdown report, and chart online or offline.

**Architecture:** Three collectors write independent raw CSV files with a shared schema. Processing modules combine them into a canonical long table, score available dimensions with renormalized weights, and generate transparent outputs that disclose samples and missing data. A pipeline runner coordinates stages without coupling collectors to each other.

**Tech Stack:** Python 3.10+, pandas, requests, feedparser, beautifulsoup4, yfinance, matplotlib, pytest

---

## File Map

- `config/industries.json`: industries, keywords, and optional market proxies.
- `config/sources.json`: configurable public news and policy sources.
- `scripts/common.py`: project paths, logging, JSON/CSV helpers, constants.
- `scripts/content_collector.py`: shared feed/page parsing and keyword matching.
- `scripts/fetch_news.py`: independent news collector.
- `scripts/fetch_policy.py`: independent policy collector.
- `scripts/fetch_market.py`: independent yfinance market-proxy collector.
- `scripts/build_dataset.py`: canonical long-table builder.
- `scripts/score_industries.py`: percentile scoring and missing-weight normalization.
- `scripts/generate_report.py`: Markdown and chart output.
- `scripts/run_pipeline.py`: resilient stage orchestration.
- `data/samples/*.csv`: deterministic offline inputs.
- `tests/`: unit and offline integration tests.
- `run_all.ps1`, `run_all.sh`: platform entry points.
- `README.md`: Chinese installation, operation, scheduling, data, and extension guide.

### Task 1: Bootstrap Configuration and Shared Runtime

**Files:**
- Create: `config/industries.json`
- Create: `config/sources.json`
- Create: `scripts/__init__.py`
- Create: `scripts/common.py`
- Create: `requirements.txt`
- Create: `.gitignore`
- Test: `tests/test_common.py`

- [ ] **Step 1: Write the failing configuration test**

```python
from scripts.common import LONG_COLUMNS, load_industries


def test_industry_config_has_12_entries_and_allows_empty_proxy():
    industries = load_industries()
    assert len(industries) == 12
    assert {"name", "keywords", "market_proxy"} <= industries[0].keys()
    assert any(item["market_proxy"] is None for item in industries)
    assert LONG_COLUMNS == ["industry", "date", "metric", "value", "source", "status"]
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m pytest tests/test_common.py -v`

Expected: FAIL because `scripts.common` does not exist.

- [ ] **Step 3: Add the minimal runtime and configuration**

Implement `PROJECT_ROOT = Path(__file__).resolve().parents[1]`, path constants, `LONG_COLUMNS`, `ensure_directories()`, `setup_logging()`, `load_json()`, `load_industries()`, and `write_csv()`. Configure exactly 12 industries; use `null` for low-altitude economy and cross-border e-commerce market proxies. Add configurable RSS/page sources and pinned minimum dependency versions.

- [ ] **Step 4: Run the test and verify GREEN**

Run: `python -m pytest tests/test_common.py -v`

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add .gitignore requirements.txt config scripts/__init__.py scripts/common.py tests/test_common.py
git commit -m "chore: bootstrap industry tracker configuration"
```

### Task 2: Implement Shared Content Matching and News Collection

**Files:**
- Create: `scripts/content_collector.py`
- Create: `scripts/fetch_news.py`
- Create: `data/samples/news_daily.csv`
- Test: `tests/test_content_collector.py`
- Test: `tests/test_fetch_news.py`

- [ ] **Step 1: Write failing matching and offline tests**

```python
from scripts.content_collector import match_industries
from scripts.fetch_news import collect_news


def test_match_industries_is_case_insensitive_and_deduplicated():
    industries = [{"name": "人工智能", "keywords": ["AI", "大模型", "ai"]}]
    assert match_industries("AI 大模型加速发展", industries) == ["人工智能"]


def test_collect_news_offline_marks_sample(tmp_path):
    output = tmp_path / "news.csv"
    frame = collect_news(offline=True, output_path=output)
    assert output.exists()
    assert set(frame["metric"]) == {"news_heat"}
    assert set(frame["status"]) == {"sample"}
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/test_content_collector.py tests/test_fetch_news.py -v`

Expected: FAIL because collector modules do not exist.

- [ ] **Step 3: Implement feed parsing, matching, aggregation, and sample fallback**

Implement:

```python
def match_industries(title: str, industries: list[dict]) -> list[str]:
    normalized = title.casefold()
    return [
        item["name"]
        for item in industries
        if any(keyword.casefold() in normalized for keyword in item["keywords"])
    ]
```

Add `fetch_feed_entries(source, timeout=15)` and aggregate matched titles by industry/date into the long schema. Include zero `no_match` rows for configured industries not matched by a successful source. `collect_news(offline=False, fallback_samples=True, output_path=...)` must catch each source error, log it, continue, and use the sample only when no online source produced usable rows.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest tests/test_content_collector.py tests/test_fetch_news.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/content_collector.py scripts/fetch_news.py data/samples/news_daily.csv tests/test_content_collector.py tests/test_fetch_news.py
git commit -m "feat: add resilient news collector"
```

### Task 3: Implement Independent Policy Collection

**Files:**
- Create: `scripts/fetch_policy.py`
- Create: `data/samples/policy_daily.csv`
- Test: `tests/test_fetch_policy.py`

- [ ] **Step 1: Write failing policy tests**

```python
from scripts.fetch_policy import collect_policy


def test_collect_policy_offline_marks_sample(tmp_path):
    output = tmp_path / "policy.csv"
    frame = collect_policy(offline=True, output_path=output)
    assert output.exists()
    assert set(frame["metric"]) == {"policy_heat"}
    assert set(frame["status"]) == {"sample"}


def test_policy_source_failure_falls_back_without_raising(tmp_path):
    output = tmp_path / "policy.csv"
    frame = collect_policy(
        offline=False,
        fallback_samples=True,
        output_path=output,
        sources=[{"name": "broken", "url": "http://127.0.0.1:1", "type": "rss"}],
    )
    assert not frame.empty
    assert set(frame["status"]) == {"sample"}
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/test_fetch_policy.py -v`

Expected: FAIL because `scripts.fetch_policy` does not exist.

- [ ] **Step 3: Implement policy RSS/page collection**

Reuse only parsing and matching helpers from `content_collector`; do not call `fetch_news`. Support `rss` and `html` source types, with HTML selectors supplied in `sources.json`. Aggregate to `policy_heat`, log per-source failures, and apply the same explicit offline/fallback behavior as news.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest tests/test_fetch_policy.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/fetch_policy.py data/samples/policy_daily.csv tests/test_fetch_policy.py
git commit -m "feat: add resilient policy collector"
```

### Task 4: Implement Independent Market Proxy Collection

**Files:**
- Create: `scripts/fetch_market.py`
- Create: `data/samples/market_daily.csv`
- Test: `tests/test_fetch_market.py`

- [ ] **Step 1: Write failing market-state tests**

```python
from scripts.fetch_market import collect_market, market_row


def test_market_row_marks_empty_proxy_as_missing_config():
    row = market_row({"name": "低空经济", "market_proxy": None}, offline=False)
    assert row["status"] == "missing_config"
    assert row["value"] is None


def test_collect_market_offline_preserves_missing_proxy(tmp_path):
    output = tmp_path / "market.csv"
    frame = collect_market(offline=True, output_path=output)
    assert output.exists()
    assert "sample" in set(frame["status"])
    assert "missing_config" in set(frame["status"])
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/test_fetch_market.py -v`

Expected: FAIL because `scripts.fetch_market` does not exist.

- [ ] **Step 3: Implement yfinance download and status mapping**

Implement `market_row(industry, offline=False, downloader=None)` and `collect_market(...)`. Use adjusted close when available, otherwise close. Return `insufficient_data` for fewer than two valid observations, `source_error` on download exceptions, and `missing_config` without invoking yfinance when the proxy is null. Offline samples must retain `missing_config` rows and label available proxy values `sample`.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest tests/test_fetch_market.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/fetch_market.py data/samples/market_daily.csv tests/test_fetch_market.py
git commit -m "feat: add market proxy collector"
```

### Task 5: Build the Canonical Long Table

**Files:**
- Create: `scripts/build_dataset.py`
- Test: `tests/test_build_dataset.py`

- [ ] **Step 1: Write failing schema test**

```python
import pandas as pd
from scripts.build_dataset import build_dataset
from scripts.common import LONG_COLUMNS


def test_build_dataset_enforces_order_and_valid_metrics(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    for name, metric in [
        ("news_daily.csv", "news_heat"),
        ("policy_daily.csv", "policy_heat"),
        ("market_daily.csv", "market_return_3m"),
    ]:
        pd.DataFrame([{
            "industry": "人工智能", "date": "2026-06-11", "metric": metric,
            "value": 1, "source": "sample", "status": "sample",
        }]).to_csv(raw / name, index=False)
    output = tmp_path / "long.csv"
    frame = build_dataset(raw_dir=raw, output_path=output)
    assert list(frame.columns) == LONG_COLUMNS
    assert set(frame["metric"]) == {"news_heat", "policy_heat", "market_return_3m"}
```

- [ ] **Step 2: Run test and verify RED**

Run: `python -m pytest tests/test_build_dataset.py -v`

Expected: FAIL because `scripts.build_dataset` does not exist.

- [ ] **Step 3: Implement strict normalization and concatenation**

Read all three required raw files, add absent columns as null, reject unknown metrics or statuses with `ValueError`, normalize dates to ISO strings, coerce values to numeric, order by date/industry/metric, and write UTF-8 CSV with `utf-8-sig`.

- [ ] **Step 4: Run test and verify GREEN**

Run: `python -m pytest tests/test_build_dataset.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_dataset.py tests/test_build_dataset.py
git commit -m "feat: build canonical industry metric table"
```

### Task 6: Score Industries with Missing-Weight Renormalization

**Files:**
- Create: `scripts/score_industries.py`
- Test: `tests/test_score_industries.py`

- [ ] **Step 1: Write failing scoring tests**

```python
import pandas as pd
from scripts.score_industries import score_industries


def test_scoring_renormalizes_available_weights():
    frame = pd.DataFrame([
        ["A", "2026-06-11", "news_heat", 10, "x", "ok"],
        ["A", "2026-06-11", "policy_heat", 5, "x", "ok"],
        ["A", "2026-06-11", "market_return_3m", None, "x", "missing_config"],
        ["B", "2026-06-11", "news_heat", 1, "x", "ok"],
        ["B", "2026-06-11", "policy_heat", 1, "x", "ok"],
        ["B", "2026-06-11", "market_return_3m", 0.1, "x", "ok"],
    ], columns=["industry", "date", "metric", "value", "source", "status"])
    result = score_industries(frame)
    row = result.set_index("industry").loc["A"]
    assert row["available_weight"] == 0.7
    assert row["missing_metrics"] == "market_return_3m"
    assert pd.notna(row["composite_score"])


def test_all_missing_industry_has_no_score():
    frame = pd.DataFrame([
        ["A", "2026-06-11", "market_return_3m", None, "x", "missing_config"],
    ], columns=["industry", "date", "metric", "value", "source", "status"])
    result = score_industries(frame)
    assert pd.isna(result.loc[0, "composite_score"])
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/test_score_industries.py -v`

Expected: FAIL because `scripts.score_industries` does not exist.

- [ ] **Step 3: Implement percentile scores and transparent output**

Use weights `news_heat=0.4`, `market_return_3m=0.3`, and `policy_heat=0.3`. Treat only `ok`, `sample`, and `no_match` as scoreable. Use `rank(pct=True) * 100` per metric; calculate the weighted numerator only from available scores and divide by available weight. Include raw values, component scores, `composite_score`, `available_weight`, `missing_metrics`, and combined `data_status`, then rank non-null scores descending.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest tests/test_score_industries.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/score_industries.py tests/test_score_industries.py
git commit -m "feat: score industries with missing data disclosure"
```

### Task 7: Generate the Markdown Report and Chart

**Files:**
- Create: `scripts/generate_report.py`
- Test: `tests/test_generate_report.py`

- [ ] **Step 1: Write failing disclosure test**

```python
import pandas as pd
from scripts.generate_report import generate_report


def test_report_discloses_proxy_and_degraded_data(tmp_path):
    scores = pd.DataFrame([{
        "rank": 1, "industry": "人工智能", "composite_score": 90.0,
        "news_heat": 8, "market_return_3m": 0.12, "policy_heat": 5,
        "news_heat_score": 100, "market_return_3m_score": 100,
        "policy_heat_score": 100, "available_weight": 1.0,
        "missing_metrics": "", "data_status": "sample",
    }])
    report = tmp_path / "report.md"
    chart = tmp_path / "chart.png"
    generate_report(scores, report_path=report, chart_path=chart)
    text = report.read_text(encoding="utf-8")
    assert "代理指标" in text
    assert "不代表行业真实市场规模" in text
    assert "sample" in text
    assert chart.exists()
```

- [ ] **Step 2: Run test and verify RED**

Run: `python -m pytest tests/test_generate_report.py -v`

Expected: FAIL because `scripts.generate_report` does not exist.

- [ ] **Step 3: Implement report sections and headless chart rendering**

Set matplotlib backend to `Agg`. Generate date metadata, complete ranking, Top 5 evidence, degraded/missing table, method, proxy disclaimer, and risk notes. Use a Chinese-capable font fallback list without failing when a font is absent. Plot only non-null scores.

- [ ] **Step 4: Run test and verify GREEN**

Run: `python -m pytest tests/test_generate_report.py -v`

Expected: all tests pass and a PNG exists.

- [ ] **Step 5: Commit**

```bash
git add scripts/generate_report.py tests/test_generate_report.py
git commit -m "feat: generate industry ranking report"
```

### Task 8: Orchestrate the Offline and Degradable Pipeline

**Files:**
- Create: `scripts/run_pipeline.py`
- Create: `run_all.ps1`
- Create: `run_all.sh`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write failing offline end-to-end test**

```python
from scripts.run_pipeline import run_pipeline


def test_offline_pipeline_generates_all_outputs(tmp_path):
    outputs = run_pipeline(offline=True, project_root=tmp_path)
    assert outputs["score"].exists()
    assert outputs["report"].exists()
    assert outputs["chart"].exists()
    assert outputs["long_table"].exists()
```

- [ ] **Step 2: Run test and verify RED**

Run: `python -m pytest tests/test_pipeline.py -v`

Expected: FAIL because `scripts.run_pipeline` does not exist.

- [ ] **Step 3: Implement orchestration and launchers**

`run_pipeline(offline=False, fallback_samples=True, project_root=PROJECT_ROOT)` must create directories, invoke collectors independently, continue after collector exceptions by writing `source_error` placeholder rows, then build, score, and report. Add CLI flags `--offline`, `--fallback-samples`, and `--no-fallback-samples`. PowerShell and shell launchers must resolve their own directory and forward all arguments to `python scripts/run_pipeline.py`.

- [ ] **Step 4: Run test and verify GREEN**

Run: `python -m pytest tests/test_pipeline.py -v`

Expected: all tests pass and all four artifacts exist.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_pipeline.py run_all.ps1 run_all.sh tests/test_pipeline.py
git commit -m "feat: orchestrate degradable industry pipeline"
```

### Task 9: Document, Install, and Verify the Complete MVP

**Files:**
- Create: `README.md`
- Modify: files required by verification findings only

- [ ] **Step 1: Write the Chinese operations guide**

Document Python environment setup, dependency installation, online mode, `--offline`, fallback behavior, independent script execution, Windows Task Scheduler notes, Linux crontab example, source configuration, long-table fields, scoring formula, proxy disclaimer, missing statuses, output files, and extension directions.

- [ ] **Step 2: Install dependencies**

Run: `python -m pip install -r requirements.txt`

Expected: exit code 0.

- [ ] **Step 3: Run the full automated test suite**

Run: `python -m pytest -v`

Expected: all tests pass.

- [ ] **Step 4: Run the real offline entry point**

Run: `powershell -ExecutionPolicy Bypass -File .\run_all.ps1 --offline`

Expected: exit code 0 and creation of:

```text
data/processed/industry_metrics_long.csv
reports/industry_score.csv
reports/industry_report.md
charts/industry_score_bar.png
logs/industry_tracker.log
```

- [ ] **Step 5: Validate artifacts and repository cleanliness**

Run:

```bash
python -c "import pandas as pd; f=pd.read_csv('data/processed/industry_metrics_long.csv'); assert list(f.columns)==['industry','date','metric','value','source','status']; print(f.shape)"
git diff --check
git status --short
```

Expected: schema assertion succeeds, `git diff --check` emits no errors, and only intentional generated/README changes are shown.

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: add industry tracker operations guide"
```
