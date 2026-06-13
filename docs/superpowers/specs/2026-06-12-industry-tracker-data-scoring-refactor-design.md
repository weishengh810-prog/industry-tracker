# Industry Tracker Data and Scoring Refactor Design

## 1. Objective

Refactor the industry tracker to use public, free, unauthenticated data sources
that are reachable from an overseas cloud server. Replace mainland China ETF
proxies, add technical activity collectors, build historical momentum features,
and score industries using comparable momentum signals.

The implementation must preserve:

- `LONG_COLUMNS`: `industry,date,metric,value,source,status`
- Offline execution with deterministic sample CSV files
- Existing `source_error` degradation behavior
- Independent collector failures that do not stop later pipeline stages

The final pipeline is:

```text
news_daily.csv
policy_daily.csv
market_daily.csv
arxiv_daily.csv
github_daily.csv
nvd_daily.csv
-> build_dataset
-> build_momentum_features
-> score_industries
-> generate_report
```

## 2. Configuration and Sources

Each industry in `config/industries.json` keeps its Chinese `keywords` and adds
`keywords_en` for overseas English-language sources.

Market proxies:

| Industry | Ticker |
| --- | --- |
| 人工智能 | AIQ |
| 半导体 | SMH |
| 新能源汽车 | DRIV |
| 储能 | BATT |
| 机器人 | ROBO |
| 低空经济 | ARKX |
| 跨境电商 | EMQQ |
| 医药健康 | IXJ |
| 消费零售 | CHIQ |
| 物流供应链 | SHPP |
| 旅游 | AWAY |
| 网络安全 | CIBR |

`SHPP` is a temporary low-liquidity proxy. The report must disclose this risk.

The configured `gov.cn` and `miit.gov.cn` policy sources are removed. The
`policy_heat` collector remains for schema compatibility and future sources,
but it does not participate in the primary score. When online policy sources
are empty, it writes one `missing_config` row per industry. Explicit offline
mode still reads the policy sample.

## 3. Daily Metrics and Validation

Daily collector outputs retain exactly `LONG_COLUMNS`.

Allowed daily metrics:

- `news_heat`
- `policy_heat`
- `market_return_3m`
- `market_return_4w`
- `market_volume_change_4w`
- `arxiv_paper_count_4w`
- `github_repo_count_4w`
- `nvd_cve_count_4w`

Allowed daily statuses remain:

- `ok`
- `sample`
- `no_match`
- `missing_config`
- `source_error`
- `insufficient_data`

`insufficient_history` is not a daily status. It is used only in
`momentum_features.csv`.

Offline samples:

- `market_daily.csv` contains all three market metrics.
- `arxiv_daily.csv` contains `arxiv_paper_count_4w`.
- `github_daily.csv` contains `github_repo_count_4w`.
- `nvd_daily.csv` contains `nvd_cve_count_4w`.

## 4. Collector Orchestration

`_run_collector` and `_source_error_frame` accept either one metric string or a
list of metric strings. A script-level collector crash writes one
`source_error` row for every industry and every declared metric, then allows
the pipeline to continue.

All collectors, including existing collectors, run through `_run_collector`.
Collector failure must not stop `build_dataset`, `build_momentum_features`,
`score_industries`, or `generate_report`.

## 5. Market Collector

Each ticker request downloads at least 120 calendar days of daily history.
One download produces:

- `market_return_3m`: price return over approximately the latest 90 calendar
  days, using available observations at the window boundaries.
- `market_return_4w`: price return over the latest 28 calendar days.
- `market_volume_change_4w`: mean volume in the latest 28 calendar days divided
  by mean volume in the preceding 28 calendar days, minus one.

Price and volume calculations are independent. Missing, all-zero, or unusably
low volume produces `insufficient_data` for
`market_volume_change_4w` without affecting either return metric. A ticker
request failure produces `source_error` for all three metrics for that ticker.

## 6. Technical Activity Collectors

All new collectors use `data/cache/{source}_YYYY-MM-DD.json`. A valid cache is
read before any request. A damaged cache is ignored and normal requests
continue. Offline mode reads sample CSV files and neither requests nor sleeps.

### arXiv

- Endpoint: `https://export.arxiv.org/api/query`
- Industries: 人工智能、半导体、机器人、医药健康
- Query terms: first two `keywords_en`
- Window: previous 28 days
- Metric: `arxiv_paper_count_4w`
- Delay: at least 3 seconds after each request
- Empty result: `no_match`
- Other industries: `missing_config`

### GitHub

- Endpoint: unauthenticated GitHub Search API
- Industries: 人工智能、半导体、机器人、网络安全
- Query: first two `keywords_en`, joined with `OR`, plus a repository creation
  cutoff for the previous 28 days
- Metric: `github_repo_count_4w`
- Limit: no more than 50 requests per hour
- Delay: random 60 to 75 seconds after each request
- Empty result: `no_match`
- Other industries: `missing_config`

### NVD

- Endpoint: `https://services.nvd.nist.gov/rest/json/cves/2.0`
- Industry: 网络安全 only
- Window: previous 28 days
- Metric: `nvd_cve_count_4w`
- Delay: at least 6 seconds after each request
- Query parameters: hard-coded in the collector
- Other industries: `missing_config`

An internally handled NVD request failure gives 网络安全 `source_error` while
all other industries remain `missing_config`. Only an uncaught script-level
failure invokes `_run_collector` and creates all-industry `source_error` rows.

## 7. Momentum Features

`build_momentum_features.py` reads:

- `data/processed/industry_metrics_long.csv`
- `archives/*/processed/industry_metrics_long.csv`

It combines and deduplicates records by `industry + metric + date`, preferring
the current processed table when duplicate records exist.

Output fields:

```text
industry,metric,growth_rate_4w,z_score_12w,freshness_days,momentum_status
```

Each `industry + metric` is evaluated independently.

The latest daily record controls eligibility. If its status is not
`ok`, `sample`, or `no_match`, that status is copied to `momentum_status` and
older history is not used to calculate momentum.

`growth_rate_4w`:

```text
(mean of latest 28 calendar days / mean of preceding 28 calendar days) - 1
```

Both windows must have usable observations and cover their complete calendar
period. The feature therefore needs approximately 56 days of accumulated
history. A zero denominator or incomplete history produces a null value and
`insufficient_history`.

`z_score_12w`:

```text
(latest value - mean over latest 84 calendar days)
/ standard deviation over latest 84 calendar days
```

Incomplete 84-day history or zero standard deviation produces a null value and
`insufficient_history`; it must never produce a synthetic zero.

`freshness_days` is the number of calendar days between the latest usable
record and the build date.

## 8. Scoring

Only `growth_rate_4w` values with `momentum_status=ok` are eligible. Absolute
daily values are never mixed into momentum scoring.

Before a bottom-level metric receives a cross-sectional percentile score, at
least three industries must have an eligible value for that metric. Metrics
below this threshold do not participate in the primary score and appear only
in the report's auxiliary observation section.

First-version primary dimensions:

- `capital_momentum`: 35%
  - Percentile scores from `market_return_3m`
  - Percentile scores from `market_return_4w`
  - Mean of available eligible bottom-level scores
- `tech_activity`: 65%
  - Percentile scores from `arxiv_paper_count_4w`
  - Percentile scores from `github_repo_count_4w`
  - Mean of available eligible bottom-level scores

`market_volume_change_4w` is auxiliary and never enters `capital_momentum`.

`nvd_cve_count_4w` covers only 网络安全, so it cannot produce a meaningful
cross-sectional score. It is shown as a cybersecurity-specific signal and does
not enter the first-version primary score.

An `external_signal` field and report section may be reserved, but its proposed
30% weight is disabled until comparable specialist metrics cover at least
three industries. When it is enabled in a future version, the intended
weights are capital 35%, technology 35%, and external signals 30%.

Available primary dimensions are renormalized using the existing missing-weight
logic. If no primary dimension is available, `composite_score` and `rank` are
null and `ranking_status` is `insufficient_history`.

## 9. Reporting

The report dynamically identifies one of:

- `完整 momentum 模式`
- `部分 momentum 模式`
- `历史数据不足，暂不排名`

The last mode explains that approximately 56 days of accumulated data are
needed before the first formal four-week momentum ranking can be produced.

The report includes:

- Bottom-level metrics currently in `insufficient_history`
- `market_volume_change_4w` as an auxiliary observation
- NVD as a cybersecurity-specific auxiliary signal
- Any metric excluded because fewer than three industries were eligible
- A low-liquidity ETF proxy warning for `SHPP`
- Existing missing data and degradation disclosures

Required disclaimer:

> 本系统比较的是行业相对自身历史的加速程度，不是行业绝对规模。
> 小行业若快速升温可能排名靠前；大行业若增速放缓排名会下降。
> ETF 为全球市场代理，不代表中国行业真实基本面。
> 数据来源：公开 ETF 行情、arXiv 学术论文、GitHub 开源仓库、NVD 漏洞数据库。

## 10. Verification

Tests cover:

- `_run_collector` string and multi-metric compatibility
- Null or failed ticker degradation
- Independent volume failure
- Empty arXiv and GitHub results
- NVD local failure semantics
- Valid daily metric and status whitelists
- Complete offline samples
- Independent momentum history eligibility
- Zero growth denominator
- Insufficient 12-week z-score history
- Missing momentum file and no-ranking behavior
- Minimum three-industry percentile threshold
- Use of growth rates rather than daily values
- Exclusion of volume and NVD from the primary score
- Continued pipeline execution after collector crashes

Required final commands:

```text
python scripts/fetch_market.py --offline
python scripts/run_pipeline.py --offline
pytest -v
```

Online market verification must obtain data for at least eight configured
tickers.
