# Industry Tracker Data and Scoring Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace prohibited market and policy sources, add cached public technical-activity collectors, calculate per-metric historical momentum, and rank industries only from comparable momentum signals.

**Architecture:** Six independent collectors write strict `LONG_COLUMNS` daily CSV files. A canonical builder validates and combines them, a new momentum builder joins current and archived observations, and scoring uses only eligible four-week growth percentiles with a three-industry minimum. The pipeline keeps the existing `_run_collector` degradation boundary and always continues to dataset, momentum, scoring, and report generation.

**Tech Stack:** Python 3.10+, pandas, requests, feedparser, yfinance, matplotlib, pytest

---

## File Map

- Modify `config/industries.json`: add `keywords_en` and replace all market proxies.
- Modify `config/sources.json`: remove prohibited policy sources.
- Modify `scripts/common.py`: metric whitelist, cache path, momentum path constants.
- Modify `scripts/fetch_policy.py`: online empty-source `missing_config` behavior.
- Modify `scripts/run_pipeline.py`: multi-metric degradation and new pipeline stages.
- Modify `scripts/fetch_market.py`: three independent market metrics from 120-day history.
- Create `scripts/source_cache.py`: shared daily JSON cache read/write helper.
- Create `scripts/fetch_arxiv.py`: cached arXiv paper counts.
- Create `scripts/fetch_github_activity.py`: cached GitHub repository counts.
- Create `scripts/fetch_nvd.py`: cached network-security CVE count.
- Modify `scripts/build_dataset.py`: validate and combine six raw files.
- Create `scripts/build_momentum_features.py`: per-industry and per-metric history features.
- Rewrite `scripts/score_industries.py`: momentum-only percentile scoring.
- Modify `scripts/generate_report.py`: scoring mode and auxiliary signal disclosures.
- Modify `data/samples/market_daily.csv`: all three market metrics.
- Create `data/samples/arxiv_daily.csv`.
- Create `data/samples/github_daily.csv`.
- Create `data/samples/nvd_daily.csv`.
- Modify/add tests under `tests/` for each behavior.
- Modify `README.md`: sources, metrics, scoring, history threshold, and execution flow.

### Task 1: Configuration, Whitelists, Policy Degradation, and Multi-Metric Fallback

**Files:**
- Modify: `config/industries.json`
- Modify: `config/sources.json`
- Modify: `scripts/common.py`
- Modify: `scripts/fetch_policy.py`
- Modify: `scripts/run_pipeline.py`
- Modify: `tests/test_common.py`
- Modify: `tests/test_fetch_policy.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Write failing configuration and degradation tests**

Add these tests:

```python
from scripts.common import VALID_METRICS, load_industries, load_sources
from scripts.run_pipeline import _source_error_frame


def test_industries_use_english_keywords_and_us_market_proxies():
    industries = load_industries()
    tickers = {
        item["name"]: item["market_proxy"]["ticker"]
        for item in industries
    }
    assert all(item["keywords_en"] for item in industries)
    assert tickers["人工智能"] == "AIQ"
    assert tickers["物流供应链"] == "SHPP"
    assert not any(ticker.endswith((".SZ", ".SS")) for ticker in tickers.values())


def test_prohibited_policy_sources_are_removed():
    urls = [source["url"] for source in load_sources()["policy"]]
    assert not any("gov.cn" in url or "miit.gov.cn" in url for url in urls)


def test_new_daily_metrics_are_whitelisted():
    assert {
        "market_return_4w",
        "market_volume_change_4w",
        "arxiv_paper_count_4w",
        "github_repo_count_4w",
        "nvd_cve_count_4w",
    } <= VALID_METRICS


def test_source_error_frame_expands_multiple_metrics():
    frame = _source_error_frame(["market_return_3m", "market_return_4w"], "market")
    assert len(frame) == 24
    assert set(frame["metric"]) == {"market_return_3m", "market_return_4w"}
    assert set(frame["status"]) == {"source_error"}


def test_source_error_frame_keeps_single_metric_compatibility():
    frame = _source_error_frame("news_heat", "news")
    assert len(frame) == 12
    assert set(frame["metric"]) == {"news_heat"}
    assert set(frame["status"]) == {"source_error"}
```

Add a policy test:

```python
def test_online_policy_with_no_sources_returns_missing_config(tmp_path):
    frame = collect_policy(
        offline=False,
        fallback_samples=True,
        sources=[],
        output_path=tmp_path / "policy.csv",
    )
    assert len(frame) == 12
    assert set(frame["status"]) == {"missing_config"}
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```text
pytest tests/test_common.py tests/test_fetch_policy.py tests/test_pipeline.py -v
```

Expected: failures for missing `keywords_en`, prohibited policy URLs, missing
metric whitelist entries, list metrics not supported, and empty policy sources
falling through to sample behavior.

- [ ] **Step 3: Apply the minimal configuration and runtime changes**

Update every industry with these exact English keywords and ticker values:

```python
SOURCE_CONFIG = {
    "人工智能": ("AIQ", ["artificial intelligence", "large language model", "generative AI"]),
    "半导体": ("SMH", ["semiconductor", "chip", "integrated circuit"]),
    "新能源汽车": ("DRIV", ["electric vehicle", "EV battery", "autonomous driving"]),
    "储能": ("BATT", ["energy storage", "battery storage", "grid storage"]),
    "机器人": ("ROBO", ["robotics", "industrial robot", "humanoid robot"]),
    "低空经济": ("ARKX", ["drone", "eVTOL", "urban air mobility"]),
    "跨境电商": ("EMQQ", ["cross-border e-commerce", "global marketplace", "overseas warehouse"]),
    "医药健康": ("IXJ", ["pharmaceutical", "biotech", "medical device"]),
    "消费零售": ("CHIQ", ["consumer retail", "e-commerce", "consumer goods"]),
    "物流供应链": ("SHPP", ["logistics", "supply chain", "freight"]),
    "旅游": ("AWAY", ["tourism", "travel", "hospitality"]),
    "网络安全": ("CIBR", ["cybersecurity", "information security", "network security"]),
}
```

Set:

```json
{
  "policy": []
}
```

Extend `VALID_METRICS` exactly with the five new daily metrics while leaving
`VALID_STATUSES` unchanged.

Implement the orchestration compatibility as:

```python
def _source_error_frame(
    metrics: str | list[str],
    source: str,
) -> pd.DataFrame:
    metric_names = [metrics] if isinstance(metrics, str) else metrics
    return pd.DataFrame(
        [
            {
                "industry": item["name"],
                "date": date.today().isoformat(),
                "metric": metric,
                "value": None,
                "source": source,
                "status": "source_error",
            }
            for item in load_industries()
            for metric in metric_names
        ],
        columns=LONG_COLUMNS,
    )
```

Change `_run_collector`'s `metric` annotation to `str | list[str]` and pass it
unchanged to `_source_error_frame`.

In `collect_policy`, handle an empty online source list before attempting
fallback samples:

```python
if not configured_sources:
    frame = pd.DataFrame(
        [
            {
                "industry": item["name"],
                "date": date.today().isoformat(),
                "metric": "policy_heat",
                "value": None,
                "source": "",
                "status": "missing_config",
            }
            for item in industries
        ],
        columns=LONG_COLUMNS,
    )
```

Explicit `offline=True` continues to load `policy_daily.csv`.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```text
pytest tests/test_common.py tests/test_fetch_policy.py tests/test_pipeline.py -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```text
git add config/industries.json config/sources.json scripts/common.py scripts/fetch_policy.py scripts/run_pipeline.py tests/test_common.py tests/test_fetch_policy.py tests/test_pipeline.py
git commit -m "refactor: update source configuration and collector fallback"
```

### Task 2: Three-Metric Market Collector and Offline Sample

**Files:**
- Modify: `scripts/fetch_market.py`
- Modify: `data/samples/market_daily.csv`
- Modify: `tests/test_fetch_market.py`

- [ ] **Step 1: Write failing market tests**

Create deterministic frames with daily dates and test:

```python
def test_market_rows_calculate_returns_when_volume_is_missing():
    index = pd.date_range("2026-01-01", periods=120, freq="D")
    frame = pd.DataFrame(
        {
            "Close": range(100, 220),
            "Volume": [float("nan")] * 120,
        },
        index=index,
    )
    rows = market_rows(
        {
            "name": "人工智能",
            "market_proxy": {"ticker": "AIQ", "name": "AI ETF"},
        },
        downloader=lambda *args, **kwargs: frame,
    )
    by_metric = {row["metric"]: row for row in rows}
    assert by_metric["market_return_3m"]["status"] == "ok"
    assert by_metric["market_return_4w"]["status"] == "ok"
    assert by_metric["market_volume_change_4w"]["status"] == "insufficient_data"


def test_market_volume_below_liquidity_floor_is_insufficient_data():
    index = pd.date_range("2026-01-01", periods=120, freq="D")
    frame = pd.DataFrame(
        {"Close": range(100, 220), "Volume": [500] * 120},
        index=index,
    )
    rows = market_rows(
        CONFIGURED_INDUSTRY,
        downloader=lambda *args, **kwargs: frame,
    )
    by_metric = {row["metric"]: row for row in rows}
    assert by_metric["market_volume_change_4w"]["status"] == "insufficient_data"


def test_market_download_failure_returns_three_source_errors():
    def fail(*args, **kwargs):
        raise RuntimeError("download failed")

    rows = market_rows(CONFIGURED_INDUSTRY, downloader=fail)
    assert {row["metric"] for row in rows} == {
        "market_return_3m",
        "market_return_4w",
        "market_volume_change_4w",
    }
    assert {row["status"] for row in rows} == {"source_error"}


def test_market_offline_sample_contains_all_market_metrics(tmp_path):
    frame = collect_market(offline=True, output_path=tmp_path / "market.csv")
    assert set(frame["metric"]) == {
        "market_return_3m",
        "market_return_4w",
        "market_volume_change_4w",
    }
```

Retain the null-proxy test and require three `missing_config` rows.

- [ ] **Step 2: Run tests and verify RED**

Run:

```text
pytest tests/test_fetch_market.py -v
```

Expected: failure because `market_rows` and the new metrics do not exist.

- [ ] **Step 3: Implement independent market metric calculations**

Replace the single-row function with `market_rows(...) -> list[dict]`. Define
`MIN_AVERAGE_VOLUME = 1_000` shares per day as the unusably-low liquidity
floor. Download at least 120 calendar days using explicit dates:

```python
end_date = date.today() + timedelta(days=1)
start_date = end_date - timedelta(days=121)
frame = downloader(
    ticker,
    start=start_date.isoformat(),
    end=end_date.isoformat(),
    interval="1d",
    progress=False,
    auto_adjust=False,
)
```

Add helpers that:

```python
def _window_return(
    prices: pd.Series,
    calendar_days: int,
) -> float | None:
    latest_date = pd.Timestamp(prices.index[-1])
    window_start = latest_date - pd.Timedelta(days=calendar_days - 1)
    window = prices[prices.index >= window_start]
    if len(window) < 2:
        return None
    return float(window.iloc[-1] / window.iloc[0] - 1)


def _volume_change_4w(volumes: pd.Series) -> float | None:
    latest_date = pd.Timestamp(volumes.index[-1])
    recent = volumes[
        volumes.index >= latest_date - pd.Timedelta(days=27)
    ].dropna()
    previous = volumes[
        (volumes.index >= latest_date - pd.Timedelta(days=55))
        & (volumes.index < latest_date - pd.Timedelta(days=27))
    ].dropna()
    recent = recent[recent > 0]
    previous = previous[previous > 0]
    if (
        recent.empty
        or previous.empty
        or previous.mean() < MIN_AVERAGE_VOLUME
        or recent.mean() < MIN_AVERAGE_VOLUME
    ):
        return None
    return float(recent.mean() / previous.mean() - 1)
```

Use approximately 90 calendar days for `market_return_3m`, 28 calendar days
for `market_return_4w`, and independent status assignment for each row.
`collect_market` flattens all returned row lists.

Update the sample to contain 36 rows: 12 industries times three metrics.

- [ ] **Step 4: Run market tests and offline command**

Run:

```text
pytest tests/test_fetch_market.py -v
python scripts/fetch_market.py --offline
```

Expected: tests pass and command exits zero with a strict six-column CSV.

- [ ] **Step 5: Commit**

```text
git add scripts/fetch_market.py data/samples/market_daily.csv tests/test_fetch_market.py
git commit -m "feat: add four-week market momentum metrics"
```

### Task 3: Shared Daily JSON Cache Helper

**Files:**
- Create: `scripts/source_cache.py`
- Create: `tests/test_source_cache.py`
- Modify: `scripts/common.py`

- [ ] **Step 1: Write failing cache tests**

```python
def test_daily_cache_round_trip(tmp_path):
    path = daily_cache_path("github", cache_dir=tmp_path, today=date(2026, 6, 12))
    write_json_cache(path, {"人工智能": 3})
    assert read_json_cache(path) == {"人工智能": 3}


def test_damaged_cache_is_ignored(tmp_path):
    path = tmp_path / "arxiv_2026-06-12.json"
    path.write_text("{bad json", encoding="utf-8")
    assert read_json_cache(path) is None
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```text
pytest tests/test_source_cache.py -v
```

Expected: import failure because the helper does not exist.

- [ ] **Step 3: Implement the cache helper**

Create:

```python
def daily_cache_path(
    source: str,
    cache_dir: Path = CACHE_DIR,
    today: date | None = None,
) -> Path:
    cache_date = today or date.today()
    return cache_dir / f"{source}_{cache_date.isoformat()}.json"


def read_json_cache(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def write_json_cache(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
```

Add `CACHE_DIR = DATA_DIR / "cache"` and include `data/cache` in directory
creation.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```text
pytest tests/test_source_cache.py tests/test_common.py -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```text
git add scripts/common.py scripts/source_cache.py tests/test_source_cache.py
git commit -m "feat: add daily collector cache helper"
```

### Task 4: Cached arXiv Collector

**Files:**
- Create: `scripts/fetch_arxiv.py`
- Create: `data/samples/arxiv_daily.csv`
- Create: `tests/test_fetch_arxiv.py`
- Modify: `tests/test_entrypoints.py`

- [ ] **Step 1: Write failing arXiv tests**

Test offline shape, empty results, English queries, cache reuse, and delay
injection:

```python
def test_arxiv_empty_result_is_no_match(tmp_path):
    response = FakeResponse(
        b"<?xml version='1.0'?><feed xmlns='http://www.w3.org/2005/Atom'></feed>"
    )
    frame = collect_arxiv(
        industries=[AI_INDUSTRY],
        requester=lambda *args, **kwargs: response,
        sleeper=lambda seconds: None,
        cache_dir=tmp_path,
        output_path=tmp_path / "arxiv.csv",
    )
    assert frame.loc[0, "status"] == "no_match"
    assert frame.loc[0, "value"] == 0


def test_arxiv_uses_cache_without_requesting(tmp_path):
    cache = daily_cache_path("arxiv", tmp_path)
    write_json_cache(cache, {"人工智能": 4})
    frame = collect_arxiv(
        industries=[AI_INDUSTRY],
        requester=lambda *args, **kwargs: pytest.fail("unexpected request"),
        cache_dir=tmp_path,
        output_path=tmp_path / "arxiv.csv",
    )
    assert frame.loc[0, "value"] == 4
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```text
pytest tests/test_fetch_arxiv.py tests/test_entrypoints.py -v
```

Expected: import/entrypoint failures.

- [ ] **Step 3: Implement the arXiv collector**

Implement `collect_arxiv` with dependency-injected `requester`, `sleeper`,
`cache_dir`, and `today`. Only the four approved industries are requested.
Build an Atom query using the first two `keywords_en` and submitted-date range.
Count Atom `<entry>` nodes. Put the injected/default three-second sleep in a
`finally` block so every attempted request is followed by the required delay,
including failed and empty responses.

Rows use:

```python
{
    "metric": "arxiv_paper_count_4w",
    "value": count,
    "source": "arXiv API",
    "status": "ok" if count else "no_match",
}
```

Uncovered industries use null value and `missing_config`. Online request errors
are caught per industry and produce `source_error`. Cache the per-industry
counts/status payload after collection. Offline mode reads the sample CSV.

- [ ] **Step 4: Run tests and direct offline command**

Run:

```text
pytest tests/test_fetch_arxiv.py tests/test_entrypoints.py -v
python scripts/fetch_arxiv.py --offline
```

Expected: all pass and the command exits zero.

- [ ] **Step 5: Commit**

```text
git add scripts/fetch_arxiv.py data/samples/arxiv_daily.csv tests/test_fetch_arxiv.py tests/test_entrypoints.py
git commit -m "feat: add cached arxiv activity collector"
```

### Task 5: Cached GitHub Activity Collector

**Files:**
- Create: `scripts/fetch_github_activity.py`
- Create: `data/samples/github_daily.csv`
- Create: `tests/test_fetch_github_activity.py`
- Modify: `tests/test_entrypoints.py`

- [ ] **Step 1: Write failing GitHub tests**

```python
def test_github_empty_result_is_no_match(tmp_path):
    response = FakeResponse({"total_count": 0})
    frame = collect_github_activity(
        industries=[AI_INDUSTRY],
        requester=lambda *args, **kwargs: response,
        sleeper=lambda seconds: None,
        random_uniform=lambda low, high: 60,
        cache_dir=tmp_path,
        output_path=tmp_path / "github.csv",
    )
    assert frame.loc[0, "status"] == "no_match"


def test_github_sleeps_between_60_and_75_seconds(tmp_path):
    delays = []
    collect_github_activity(
        industries=[AI_INDUSTRY],
        requester=lambda *args, **kwargs: FakeResponse({"total_count": 2}),
        sleeper=delays.append,
        random_uniform=lambda low, high: 67,
        cache_dir=tmp_path,
        output_path=tmp_path / "github.csv",
    )
    assert delays == [67]
```

Also verify the query contains English keywords and `created:>YYYY-MM-DD`, and
that a same-day cache prevents requests and sleeping.

- [ ] **Step 2: Run tests and verify RED**

Run:

```text
pytest tests/test_fetch_github_activity.py tests/test_entrypoints.py -v
```

Expected: import/entrypoint failures.

- [ ] **Step 3: Implement the GitHub collector**

Request `https://api.github.com/search/repositories` with an `Accept` header and
query:

```text
("keyword one" OR "keyword two") created:>YYYY-MM-DD
```

Use `total_count`, map zero to `no_match`, and put
`sleep(random.uniform(60, 75))` in a `finally` block after every attempted
request. Only four industries are covered, so one pipeline run makes four
requests and remains below 50 requests/hour.
Catch failures per industry as `source_error`, cache results for the day, and
use deterministic offline samples without request or sleep.

- [ ] **Step 4: Run tests and direct offline command**

Run:

```text
pytest tests/test_fetch_github_activity.py tests/test_entrypoints.py -v
python scripts/fetch_github_activity.py --offline
```

Expected: all pass and the command exits zero.

- [ ] **Step 5: Commit**

```text
git add scripts/fetch_github_activity.py data/samples/github_daily.csv tests/test_fetch_github_activity.py tests/test_entrypoints.py
git commit -m "feat: add cached github activity collector"
```

### Task 6: Cached NVD Collector with Local Failure Scope

**Files:**
- Create: `scripts/fetch_nvd.py`
- Create: `data/samples/nvd_daily.csv`
- Create: `tests/test_fetch_nvd.py`
- Modify: `tests/test_entrypoints.py`

- [ ] **Step 1: Write failing NVD tests**

```python
def test_nvd_request_failure_only_marks_cybersecurity_as_source_error(tmp_path):
    def fail(*args, **kwargs):
        raise RuntimeError("NVD unavailable")

    frame = collect_nvd(
        requester=fail,
        sleeper=lambda seconds: None,
        cache_dir=tmp_path,
        output_path=tmp_path / "nvd.csv",
    )
    statuses = frame.set_index("industry")["status"]
    assert statuses["网络安全"] == "source_error"
    assert set(statuses.drop("网络安全")) == {"missing_config"}


def test_nvd_sleeps_at_least_six_seconds(tmp_path):
    delays = []
    collect_nvd(
        requester=lambda *args, **kwargs: FakeResponse({"totalResults": 3}),
        sleeper=delays.append,
        cache_dir=tmp_path,
        output_path=tmp_path / "nvd.csv",
    )
    assert delays == [6]
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```text
pytest tests/test_fetch_nvd.py tests/test_entrypoints.py -v
```

Expected: import/entrypoint failures.

- [ ] **Step 3: Implement the NVD collector**

Request the fixed CVE 2.0 endpoint with hard-coded `pubStartDate` and
`pubEndDate` parameters covering 28 days. Read `totalResults`. Put the
six-second delay in a `finally` block so every attempted request is followed by
the required pause. Only the cybersecurity row receives the result; every
other industry is `missing_config`. Catch request and parsing exceptions inside
the collector and set only cybersecurity to `source_error`. Cache the daily
payload and support deterministic offline sample loading.

- [ ] **Step 4: Run tests and direct offline command**

Run:

```text
pytest tests/test_fetch_nvd.py tests/test_entrypoints.py -v
python scripts/fetch_nvd.py --offline
```

Expected: all pass and the command exits zero.

- [ ] **Step 5: Commit**

```text
git add scripts/fetch_nvd.py data/samples/nvd_daily.csv tests/test_fetch_nvd.py tests/test_entrypoints.py
git commit -m "feat: add cached nvd signal collector"
```

### Task 7: Six-File Dataset and Per-Metric Momentum Features

**Files:**
- Modify: `scripts/build_dataset.py`
- Create: `scripts/build_momentum_features.py`
- Modify: `tests/test_build_dataset.py`
- Create: `tests/test_build_momentum_features.py`
- Modify: `tests/test_entrypoints.py`

- [ ] **Step 1: Write failing dataset and momentum tests**

Extend the dataset test to create and require all six raw files.

Add momentum tests with generated daily observations:

```python
def test_growth_zero_denominator_is_insufficient_history(tmp_path):
    dates = pd.date_range("2026-04-18", periods=56, freq="D")
    values = [0] * 28 + [2] * 28
    long_frame = make_metric_rows("A", "market_return_4w", dates, values)
    result = build_momentum_features(
        long_frame=long_frame,
        archives_dir=tmp_path / "archives",
    )
    row = result.iloc[0]
    assert pd.isna(row["growth_rate_4w"])
    assert row["momentum_status"] == "insufficient_history"


def test_short_z_score_history_is_not_zero(tmp_path):
    dates = pd.date_range("2026-05-18", periods=26, freq="D")
    long_frame = make_metric_rows("A", "github_repo_count_4w", dates, range(26))
    row = build_momentum_features(
        long_frame=long_frame,
        archives_dir=tmp_path / "archives",
    ).iloc[0]
    assert pd.isna(row["z_score_12w"])
    assert row["momentum_status"] == "insufficient_history"


def test_growth_can_be_ok_before_twelve_week_z_score_is_available(tmp_path):
    frame = make_56_day_rows("A", "market_return_4w")
    row = build_momentum_features(
        long_frame=frame,
        archives_dir=tmp_path / "archives",
    ).iloc[0]
    assert pd.notna(row["growth_rate_4w"])
    assert pd.isna(row["z_score_12w"])
    assert row["momentum_status"] == "ok"


def test_history_eligibility_is_independent_per_industry_and_metric(tmp_path):
    enough = make_56_day_rows("A", "market_return_4w")
    short = make_20_day_rows("B", "market_return_4w")
    result = build_momentum_features(
        long_frame=pd.concat([enough, short]),
        archives_dir=tmp_path / "archives",
    ).set_index(["industry", "metric"])
    assert result.loc[("A", "market_return_4w"), "momentum_status"] == "ok"
    assert (
        result.loc[("B", "market_return_4w"), "momentum_status"]
        == "insufficient_history"
    )


def test_latest_error_status_blocks_old_history(tmp_path):
    frame = pd.concat(
        [
            make_56_day_rows("A", "market_return_4w"),
            make_row("A", "2026-06-12", "market_return_4w", None, "source_error"),
        ]
    )
    row = build_momentum_features(
        long_frame=frame,
        archives_dir=tmp_path / "archives",
    ).iloc[0]
    assert row["momentum_status"] == "source_error"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```text
pytest tests/test_build_dataset.py tests/test_build_momentum_features.py tests/test_entrypoints.py -v
```

Expected: missing raw files and missing momentum module failures.

- [ ] **Step 3: Implement dataset expansion and momentum calculation**

Set:

```python
RAW_FILES = (
    "news_daily.csv",
    "policy_daily.csv",
    "market_daily.csv",
    "arxiv_daily.csv",
    "github_daily.csv",
    "nvd_daily.csv",
)
```

In the new module:

1. Load the current long table and every matching archive path.
2. Add a priority column so current rows win duplicate
   `industry + metric + date` records.
3. Sort each group by date.
4. Check the latest raw status before filtering usable history.
5. Define current window `[latest-27 days, latest]`, previous window
   `[latest-55 days, latest-28 days]`, and 84-day z-score window.
6. Require non-empty current and previous windows and an earliest usable date
   no later than `latest-55 days`.
7. Calculate growth unless the previous mean is zero.
8. Calculate z-score only when the earliest usable date is no later than
   `latest-83 days` and the standard deviation is nonzero.
9. Mark `momentum_status=ok` when growth is available. A missing z-score alone
   does not invalidate usable four-week growth.
10. Write the exact six-column momentum output.

Expose both a dataframe API for tests and a CLI that reads/writes default
paths.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```text
pytest tests/test_build_dataset.py tests/test_build_momentum_features.py tests/test_entrypoints.py -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```text
git add scripts/build_dataset.py scripts/build_momentum_features.py tests/test_build_dataset.py tests/test_build_momentum_features.py tests/test_entrypoints.py
git commit -m "feat: build per-metric momentum features"
```

### Task 8: Momentum-Only Scoring with Eligibility Threshold

**Files:**
- Rewrite: `scripts/score_industries.py`
- Rewrite: `tests/test_score_industries.py`

- [ ] **Step 1: Write failing scoring tests**

Cover the required score behavior:

```python
def test_score_uses_growth_rate_instead_of_daily_value():
    momentum = make_momentum(
        metric="market_return_4w",
        growth={"A": 0.3, "B": 0.2, "C": 0.1},
    )
    daily = make_daily(
        metric="market_return_4w",
        values={"A": 1, "B": 2, "C": 3},
    )
    result = score_industries(daily, momentum)
    scores = result.set_index("industry")["market_return_4w_score"]
    assert scores["A"] > scores["C"]


def test_metric_with_fewer_than_three_eligible_industries_is_excluded():
    momentum = make_momentum(
        metric="arxiv_paper_count_4w",
        growth={"A": 0.2, "B": 0.1},
    )
    result = score_industries(make_daily_industries("A", "B"), momentum)
    assert result["arxiv_paper_count_4w_score"].isna().all()


def test_volume_and_nvd_do_not_affect_primary_score():
    base = score_industries(DAILY, PRIMARY_MOMENTUM)
    augmented = score_industries(
        DAILY,
        pd.concat([PRIMARY_MOMENTUM, EXTREME_VOLUME_AND_NVD]),
    )
    pd.testing.assert_series_equal(
        base.set_index("industry")["composite_score"],
        augmented.set_index("industry")["composite_score"],
    )


def test_missing_momentum_produces_no_ranking():
    result = score_industries(DAILY, momentum_frame=None)
    assert result["composite_score"].isna().all()
    assert result["rank"].isna().all()
    assert set(result["ranking_status"]) == {"insufficient_history"}


def test_available_dimensions_are_renormalized():
    result = score_industries(DAILY, CAPITAL_ONLY_MOMENTUM)
    scored = result.dropna(subset=["composite_score"])
    assert set(scored["available_weight"]) == {0.35}
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```text
pytest tests/test_score_industries.py -v
```

Expected: signature and behavior failures because scoring still uses daily
absolute values.

- [ ] **Step 3: Implement minimal momentum scoring**

Use:

```python
PRIMARY_DIMENSIONS = {
    "capital_momentum": {
        "weight": 0.35,
        "metrics": ["market_return_3m", "market_return_4w"],
    },
    "tech_activity": {
        "weight": 0.65,
        "metrics": ["arxiv_paper_count_4w", "github_repo_count_4w"],
    },
}
MIN_ELIGIBLE_INDUSTRIES = 3
```

For each bottom-level metric:

1. Select `momentum_status == "ok"` and numeric `growth_rate_4w`.
2. If fewer than three industries remain, leave all score values null and add
   the metric to an excluded-metrics field.
3. Otherwise percentile-rank growth across industries.

Average available bottom-level percentile scores into each dimension. Combine
available dimensions with original-weight renormalization. Preserve auxiliary
daily values for volume and NVD in the score output, but never include them in
the numerator. Include a null `external_signal_score` column as an explicit
reserved field; it does not carry weight in this version.

Set `ranking_status` per row to `ranked`, `partial`, or
`insufficient_history`, and expose a global `scoring_mode` column using the
approved Chinese mode labels.

The CLI treats a missing momentum file as `None`, writes a valid no-ranking
score CSV, and exits zero.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```text
pytest tests/test_score_industries.py -v
```

Expected: all scoring tests pass.

- [ ] **Step 5: Commit**

```text
git add scripts/score_industries.py tests/test_score_industries.py
git commit -m "refactor: score comparable industry momentum"
```

### Task 9: Report, Pipeline Integration, Offline End-to-End Verification, and README

**Files:**
- Modify: `scripts/generate_report.py`
- Modify: `scripts/run_pipeline.py`
- Modify: `tests/test_generate_report.py`
- Modify: `tests/test_pipeline.py`
- Modify: `tests/test_entrypoints.py`
- Modify: `README.md`
- Modify: `.gitignore`

- [ ] **Step 1: Write failing report and pipeline tests**

Add report assertions:

```python
def test_report_discloses_momentum_mode_and_auxiliary_signals(tmp_path):
    generate_report(SCORES, report_path=report, chart_path=chart)
    text = report.read_text(encoding="utf-8")
    assert "部分 momentum 模式" in text
    assert "market_volume_change_4w" in text
    assert "网络安全专项信号" in text
    assert "SHPP" in text
    assert "至少 3 个行业" in text
    assert "不代表中国行业真实基本面" in text


def test_report_handles_insufficient_history_without_ranking(tmp_path):
    generate_report(NO_RANKING_SCORES, report_path=report, chart_path=chart)
    text = report.read_text(encoding="utf-8")
    assert "历史数据不足，暂不排名" in text
    assert "约 56 天" in text
    assert chart.exists()
```

Extend pipeline tests to monkeypatch one new collector to raise and assert all
outputs still exist:

```python
def test_new_collector_crash_does_not_stop_offline_pipeline(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "scripts.run_pipeline.collect_arxiv",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    outputs = run_pipeline(offline=True, project_root=tmp_path)
    assert outputs["momentum"].exists()
    assert outputs["score"].exists()
    assert outputs["report"].exists()
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```text
pytest tests/test_generate_report.py tests/test_pipeline.py tests/test_entrypoints.py -v
```

Expected: missing columns, stages, and entrypoints.

- [ ] **Step 3: Integrate all collectors and report behavior**

In `run_pipeline.py`:

1. Add paths and `_run_collector` calls for arXiv, GitHub, and NVD.
2. Pass all three market metrics as a list.
3. Build the canonical dataset.
4. Call `build_momentum_features`.
5. Pass momentum features to `score_industries`.
6. Generate the report even when all scores are null.
7. Return a `momentum` output path.

Update `generate_report` to read dynamic `scoring_mode`, list excluded and
insufficient-history metrics, show market volume and NVD auxiliary tables, and
emit the exact approved disclaimer. The chart handles an empty ranking without
failure.

Add all new scripts to entrypoint tests. Ignore generated cache files while
retaining `data/cache/.gitkeep`.

Update README source restrictions, metric schema, 56-day ranking threshold,
first-version 35/65 weights, cache rules, offline commands, and pipeline order.

- [ ] **Step 4: Run focused tests**

Run:

```text
pytest tests/test_generate_report.py tests/test_pipeline.py tests/test_entrypoints.py -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Run all required acceptance commands**

Run:

```text
python scripts/fetch_market.py --offline
python scripts/run_pipeline.py --offline
pytest -v
```

Expected: all commands exit zero and the full test suite passes.

- [ ] **Step 6: Run online market acceptance**

Run the online market collector with sample fallback disabled and inspect the
result:

```text
python scripts/fetch_market.py --no-fallback-samples
```

Expected: at least eight distinct configured tickers have an `ok` price metric.
If network restrictions block the request, record that the online acceptance
could not be verified locally; do not weaken offline or unit-test acceptance.

- [ ] **Step 7: Commit**

```text
git add .gitignore README.md data/cache/.gitkeep scripts/generate_report.py scripts/run_pipeline.py tests/test_generate_report.py tests/test_pipeline.py tests/test_entrypoints.py
git commit -m "feat: integrate momentum scoring pipeline"
```

### Task 10: Final Regression and Scope Audit

**Files:**
- Review all modified files

- [ ] **Step 1: Verify schema and prohibited-source constraints**

Run:

```text
rg -n "gov\\.cn|miit\\.gov\\.cn|\\.SZ|\\.SS" config scripts README.md
rg -n "insufficient_history" data/samples scripts/fetch_*.py
```

Expected: no prohibited sources or A-share tickers; no
`insufficient_history` in daily collectors or sample CSV files.

- [ ] **Step 2: Verify generated schemas**

Run a short dataframe inspection that asserts:

```python
assert list(pd.read_csv("data/processed/industry_metrics_long.csv").columns) == LONG_COLUMNS
assert list(pd.read_csv("data/processed/momentum_features.csv").columns) == [
    "industry",
    "metric",
    "growth_rate_4w",
    "z_score_12w",
    "freshness_days",
    "momentum_status",
]
```

- [ ] **Step 3: Run final verification again**

Run:

```text
python scripts/fetch_market.py --offline
python scripts/run_pipeline.py --offline
pytest -v
git diff --check
git status --short --branch
```

Expected: commands pass, no whitespace errors, and only intentional generated
or documentation changes remain.
