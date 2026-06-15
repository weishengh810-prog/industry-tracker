# Trial Score Mode Design

## Goal

Provide an explicitly provisional industry ranking while fewer than 28 valid
daily archives exist. The provisional score must compare each metric across
industries before combining dimensions, so market returns, paper counts, and
repository counts are never added as raw values.

At 28 archive days, the system automatically stops all trial fallback behavior
and returns to the existing growth-only momentum scoring rules.

## Scope

This change affects:

- Pipeline history-day calculation
- Industry scoring
- Generated reports and charts
- SQLite score storage through the existing schema
- FastAPI and static metadata mode labels
- GitHub Pages mode and provisional-score disclosure
- Tests and documentation

The FastAPI route structure, ECS service configuration, GitHub Pages data-file
contract, and primary dimension weights remain unchanged.

## History-Day Source

`scripts/run_pipeline.py` counts valid archive directories named
`YYYY-MM-DD` under `archives/` and passes that count as `history_days` to
`score_industries()`.

The threshold is:

- `history_days < 28`: trial scoring is enabled.
- `history_days >= 28`: formal momentum scoring is enabled and trial fallback
  is disabled.

The same valid-date counting rule is used by static metadata and FastAPI
metadata so the score mode and `archive_days / 28` progress cannot disagree.

## Metric-Level Trial Scoring

Trial scoring applies only to the four primary metrics:

- `market_return_3m`
- `market_return_4w`
- `arxiv_paper_count_4w`
- `github_repo_count_4w`

For each primary metric and industry:

1. Use `growth_rate_4w` when it is finite and its `momentum_status` is `ok`.
2. Otherwise, use the latest daily cross-sectional value when it is finite and
   its daily status is usable.
3. Do not substitute zero for missing, invalid, or failed-source values.

Usable daily statuses are `ok`, `sample`, and `no_match`. A `no_match` value of
zero remains a real observed cross-sectional value. `missing_config`,
`source_error`, and `insufficient_data` are not usable fallbacks.

Each metric independently converts its selected values into cross-sectional
percentile scores. At least three industries must have a usable selected value
for that metric; otherwise the metric remains excluded.

The output preserves the raw latest daily value and the existing growth-rate
column. A new per-metric source column records whether the score used:

- `growth_rate_4w`
- `latest_value`
- `unavailable`

## Dimension and Composite Scores

The existing aggregation remains:

- Capital momentum: 35%
- Technology activity: 65%

Within each dimension, available primary metric percentile scores are averaged.
Across dimensions, the original 35:65 weights are renormalized over dimensions
that are available for that industry.

Missing metrics are not assigned zero. Auxiliary metrics remain observational
and do not enter the composite score.

## Formal Momentum Stage

When `history_days >= 28`:

- Only finite `growth_rate_4w` values with `momentum_status=ok` can be scored.
- Latest daily values are never used as fallback.
- The existing complete and partial momentum modes remain.
- Missing metrics and dimensions are omitted rather than scored as zero.
- Available dimension weights are renormalized as before.

This means 28 days ends trial behavior; it does not guarantee complete mode.

## Status Contract

During trial mode:

- `scoring_mode`: `试运行评分模式`
- Ranked rows: `ranking_status=trial`
- Rows with no available composite score: `ranking_status=insufficient_history`

During formal scoring:

- Complete mode: `scoring_mode=完整 momentum 模式`,
  `ranking_status=ranked`
- Partial mode: `scoring_mode=部分 momentum 模式`,
  ranked rows use `ranking_status=partial`
- No usable formal score: the existing insufficient-history state remains

The existing SQLite schema can store these string values without migration.

## Metadata and Page Behavior

Both FastAPI metadata and static `meta.json` derive `ranking_mode` from the
latest stored score rows:

- Any latest row marked `trial` means `试运行评分模式`.
- Otherwise, preserve complete, partial, or insufficient formal mode logic.

The GitHub Pages status strip continues to show archive progress, such as
`4 / 28 天`, and adds a visible trial disclosure:

`试运行评分 / 历史不足，仅供观察`

Ranking cards display trial composite scores normally rather than the previous
blank insufficient-history state. At 28 days, the disclosure disappears
automatically because metadata switches to a formal momentum mode.

The static page continues to fetch only:

- `./data/meta.json`
- `./data/ranking.json`
- `./data/history.csv`

## Reports

Generated reports describe trial scores as provisional and disclose that each
metric uses an independent cross-sectional percentile before dimension
aggregation. Formal-mode reports continue to state that scoring uses only
valid momentum growth rates.

## Testing

Tests must prove:

1. Trial mode prefers valid growth over the latest daily value.
2. Trial mode falls back to the latest usable daily value when growth is
   unavailable.
3. Different metric units are independently percentile-ranked before
   aggregation.
4. Trial mode excludes invalid daily fallback statuses and non-finite values.
5. `history_days=27` enables trial fallback.
6. `history_days=28` disables trial fallback.
7. Formal mode still supports partial scoring and weight renormalization.
8. Pipeline archive counting passes the expected `history_days`.
9. Static and FastAPI metadata return `试运行评分模式` for trial rows.
10. GitHub Pages displays the trial disclosure and retains the 28-day progress.
11. Existing static isolation and sensitive-content checks continue to pass.

## Non-Goals

- No raw-value aggregation across metrics
- No trial fallback after 28 archive days
- No database schema migration
- No FastAPI route or ECS deployment changes
- No additional GitHub Pages data files
