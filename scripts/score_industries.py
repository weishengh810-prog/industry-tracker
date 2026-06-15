from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.common import LONG_COLUMNS, PROCESSED_DIR, REPORTS_DIR, write_csv

PRIMARY_DIMENSIONS = {
    "capital_momentum": {
        "weight": 0.35,
        "metrics": ["market_return_3m", "market_return_4w"],
    },
    "tech_activity": {
        "weight": 0.65,
        "metrics": [
            "arxiv_paper_count_4w",
            "github_repo_count_4w",
        ],
    },
}
PRIMARY_METRICS = [
    metric
    for dimension in PRIMARY_DIMENSIONS.values()
    for metric in dimension["metrics"]
]
AUXILIARY_METRICS = [
    "market_volume_change_4w",
    "nvd_cve_count_4w",
]
TRACKED_METRICS = PRIMARY_METRICS + AUXILIARY_METRICS
MOMENTUM_REQUIRED_COLUMNS = {
    "industry",
    "metric",
    "growth_rate_4w",
    "momentum_status",
}
MIN_ELIGIBLE_INDUSTRIES = 3
TRIAL_HISTORY_DAYS = 28
USABLE_DAILY_STATUSES = {"ok", "sample", "no_match"}

COMPLETE_MODE = "完整 momentum 模式"
PARTIAL_MODE = "部分 momentum 模式"
TRIAL_MODE = "试运行评分模式"
INSUFFICIENT_MODE = "历史数据不足，暂不排名"


def _latest_daily(long_frame: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in LONG_COLUMNS if column not in long_frame]
    if missing:
        raise ValueError(f"Long table missing columns: {missing}")

    latest = long_frame[LONG_COLUMNS].copy()
    latest["date"] = pd.to_datetime(latest["date"], errors="coerce")
    if latest["date"].isna().any():
        raise ValueError("Long table has invalid dates")
    return (
        latest.sort_values("date", kind="stable")
        .drop_duplicates(["industry", "metric"], keep="last")
        .reset_index(drop=True)
    )


def _prepare_momentum(
    momentum_frame: pd.DataFrame | None,
) -> pd.DataFrame:
    if momentum_frame is None or momentum_frame.empty:
        return pd.DataFrame(columns=sorted(MOMENTUM_REQUIRED_COLUMNS))

    missing = sorted(MOMENTUM_REQUIRED_COLUMNS - set(momentum_frame.columns))
    if missing:
        raise ValueError(f"Momentum table missing columns: {missing}")

    momentum = momentum_frame.copy()
    momentum["growth_rate_4w"] = pd.to_numeric(
        momentum["growth_rate_4w"],
        errors="coerce",
    )
    return (
        momentum.sort_index(kind="stable")
        .drop_duplicates(["industry", "metric"], keep="last")
        .reset_index(drop=True)
    )


def _add_metric_columns(
    result: pd.DataFrame,
    latest: pd.DataFrame,
    momentum: pd.DataFrame,
    trial_mode: bool,
) -> list[str]:
    excluded_metrics = []

    for metric in TRACKED_METRICS:
        daily_rows = latest[latest["metric"] == metric].set_index("industry")
        daily_values = pd.to_numeric(
            daily_rows.get("value", pd.Series(dtype=float)),
            errors="coerce",
        )
        daily_statuses = daily_rows.get("status", pd.Series(dtype=object))
        result[metric] = result["industry"].map(daily_values)
        result[f"{metric}_status"] = (
            result["industry"].map(daily_statuses).fillna("missing")
        )

        metric_rows = momentum[momentum["metric"] == metric].set_index(
            "industry"
        )
        growth = pd.to_numeric(
            metric_rows.get(
                "growth_rate_4w",
                pd.Series(dtype=float),
            ),
            errors="coerce",
        )
        statuses = metric_rows.get(
            "momentum_status",
            pd.Series(dtype=object),
        )
        result[f"{metric}_growth_rate_4w"] = result["industry"].map(growth)
        result[f"{metric}_momentum_status"] = (
            result["industry"].map(statuses).fillna("missing")
        )

        if metric not in PRIMARY_METRICS:
            continue

        score_column = f"{metric}_score"
        source_column = f"{metric}_score_source"
        result[score_column] = np.nan
        result[source_column] = "unavailable"

        growth_values = result[f"{metric}_growth_rate_4w"]
        growth_statuses = result[f"{metric}_momentum_status"]
        growth_eligible = growth_statuses.eq("ok") & np.isfinite(
            growth_values
        )
        selected_values = growth_values.where(growth_eligible)
        selected_sources = pd.Series(
            np.where(growth_eligible, "growth_rate_4w", "unavailable"),
            index=result.index,
            dtype=object,
        )

        if trial_mode:
            daily_values = result[metric]
            daily_statuses = result[f"{metric}_status"]
            daily_eligible = daily_statuses.isin(
                USABLE_DAILY_STATUSES
            ) & np.isfinite(daily_values)
            fallback = ~growth_eligible & daily_eligible
            selected_values = selected_values.where(
                ~fallback,
                daily_values,
            )
            selected_sources = selected_sources.where(
                ~fallback,
                "latest_value",
            )

        eligible_values = selected_values.dropna()
        if eligible_values.index.nunique() < MIN_ELIGIBLE_INDUSTRIES:
            excluded_metrics.append(metric)
            continue

        result[score_column] = (
            eligible_values.rank(method="average", pct=True) * 100
        )
        result[source_column] = selected_sources.where(
            selected_values.notna(),
            "unavailable",
        )

    return excluded_metrics


def _add_dimension_scores(result: pd.DataFrame) -> None:
    for dimension, config in PRIMARY_DIMENSIONS.items():
        score_columns = [
            f"{metric}_score" for metric in config["metrics"]
        ]
        result[dimension] = result[score_columns].mean(axis=1, skipna=True)
        result[f"{dimension}_score"] = result[dimension]

    available_weight = pd.Series(0.0, index=result.index)
    weighted_score = pd.Series(0.0, index=result.index)
    for dimension, config in PRIMARY_DIMENSIONS.items():
        available = result[dimension].notna()
        weight = config["weight"]
        available_weight = available_weight.add(available.astype(float) * weight)
        weighted_score = weighted_score.add(
            result[dimension].fillna(0.0) * weight
        )

    result["available_weight"] = available_weight.round(10)
    result["composite_score"] = weighted_score.div(
        available_weight.where(available_weight.gt(0))
    )


def _add_status_columns(
    result: pd.DataFrame,
    excluded_metrics: list[str],
    trial_mode: bool,
) -> None:
    excluded = ";".join(excluded_metrics)
    result["excluded_metrics"] = excluded
    result["insufficient_metrics"] = result.apply(
        lambda row: ";".join(
            metric
            for metric in PRIMARY_METRICS
            if pd.isna(row[f"{metric}_score"])
        ),
        axis=1,
    )
    result["missing_metrics"] = result["insufficient_metrics"]
    result["data_status"] = result.apply(
        lambda row: "; ".join(
            f"{metric}:{row[f'{metric}_momentum_status']}"
            for metric in TRACKED_METRICS
        ),
        axis=1,
    )
    result["auxiliary_metrics"] = ";".join(AUXILIARY_METRICS)
    result["external_signal_score"] = np.nan

    has_ranking = result["composite_score"].notna().any()
    all_metrics_comparable = not excluded_metrics
    all_industries_have_both_dimensions = result[
        list(PRIMARY_DIMENSIONS)
    ].notna().all(axis=1).all()
    if not has_ranking:
        mode = INSUFFICIENT_MODE
    elif trial_mode:
        mode = TRIAL_MODE
    elif all_metrics_comparable and all_industries_have_both_dimensions:
        mode = COMPLETE_MODE
    else:
        mode = PARTIAL_MODE

    result["scoring_mode"] = mode
    result["ranking_status"] = np.where(
        result["composite_score"].isna(),
        "insufficient_history",
        np.where(
            mode == TRIAL_MODE,
            "trial",
            "ranked" if mode == COMPLETE_MODE else "partial",
        ),
    )


def _ordered_columns() -> list[str]:
    columns = [
        "rank",
        "industry",
        "data_date",
        "composite_score",
        "capital_momentum",
        "capital_momentum_score",
        "tech_activity",
        "tech_activity_score",
        "external_signal_score",
        "available_weight",
        "ranking_status",
        "scoring_mode",
    ]
    for metric in TRACKED_METRICS:
        columns.extend(
            [
                metric,
                f"{metric}_status",
                f"{metric}_growth_rate_4w",
                f"{metric}_momentum_status",
            ]
        )
        if metric in PRIMARY_METRICS:
            columns.extend(
                [
                    f"{metric}_score",
                    f"{metric}_score_source",
                ]
            )
    columns.extend(
        [
            "excluded_metrics",
            "insufficient_metrics",
            "auxiliary_metrics",
            "missing_metrics",
            "data_status",
        ]
    )
    return columns


def score_industries(
    long_frame: pd.DataFrame,
    momentum_frame: pd.DataFrame | None = None,
    output_path: Path | None = None,
    history_days: int = TRIAL_HISTORY_DAYS,
) -> pd.DataFrame:
    if long_frame.empty:
        raise ValueError("Cannot score an empty long table")

    latest = _latest_daily(long_frame)
    momentum = _prepare_momentum(momentum_frame)
    result = pd.DataFrame(
        {"industry": sorted(latest["industry"].dropna().unique())}
    )
    result["data_date"] = latest["date"].max().date().isoformat()
    trial_mode = history_days < TRIAL_HISTORY_DAYS

    excluded_metrics = _add_metric_columns(
        result,
        latest,
        momentum,
        trial_mode,
    )
    _add_dimension_scores(result)
    _add_status_columns(result, excluded_metrics, trial_mode)

    result["rank"] = (
        result["composite_score"]
        .rank(method="min", ascending=False)
        .where(result["composite_score"].notna())
        .astype("Int64")
    )
    result = result.sort_values(
        ["composite_score", "industry"],
        ascending=[False, True],
        na_position="last",
    ).reset_index(drop=True)
    result = result[_ordered_columns()]

    if output_path is not None:
        write_csv(result, Path(output_path))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Score industry momentum.")
    parser.add_argument(
        "--input",
        type=Path,
        default=PROCESSED_DIR / "industry_metrics_long.csv",
    )
    parser.add_argument(
        "--momentum",
        type=Path,
        default=PROCESSED_DIR / "momentum_features.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPORTS_DIR / "industry_score.csv",
    )
    parser.add_argument(
        "--history-days",
        type=int,
        default=TRIAL_HISTORY_DAYS,
        help="Valid archive-day count; values below 28 enable trial scoring.",
    )
    args = parser.parse_args()

    momentum_frame = (
        pd.read_csv(args.momentum) if args.momentum.exists() else None
    )
    score_industries(
        pd.read_csv(args.input),
        momentum_frame=momentum_frame,
        output_path=args.output,
        history_days=args.history_days,
    )


if __name__ == "__main__":
    main()
