from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from scripts.common import PROCESSED_DIR, REPORTS_DIR, write_csv

WEIGHTS = {
    "news_heat": 0.4,
    "market_return_3m": 0.3,
    "policy_heat": 0.3,
}
SCOREABLE_STATUSES = {"ok", "sample", "no_match"}


def score_industries(
    long_frame: pd.DataFrame,
    output_path: Path | None = None,
) -> pd.DataFrame:
    if long_frame.empty:
        raise ValueError("Cannot score an empty long table")

    latest = (
        long_frame.assign(date=pd.to_datetime(long_frame["date"]))
        .sort_values("date")
        .drop_duplicates(["industry", "metric"], keep="last")
    )
    result = pd.DataFrame({"industry": sorted(latest["industry"].unique())})
    result["data_date"] = result["industry"].map(
        latest.groupby("industry")["date"].max().dt.date.astype(str)
    )

    for metric in WEIGHTS:
        metric_rows = latest[latest["metric"] == metric].set_index("industry")
        raw_values = pd.to_numeric(metric_rows.get("value"), errors="coerce")
        statuses = metric_rows.get("status", pd.Series(dtype=object))
        scoreable = statuses.isin(SCOREABLE_STATUSES)
        usable_values = raw_values.where(scoreable)

        result[metric] = result["industry"].map(usable_values)
        result[f"{metric}_score"] = result["industry"].map(
            usable_values.rank(method="average", pct=True) * 100
        )
        result[f"{metric}_status"] = (
            result["industry"].map(statuses).fillna("missing")
        )

    available_weights = []
    composite_scores = []
    missing_metrics = []
    data_statuses = []
    for _, row in result.iterrows():
        available = [
            metric
            for metric in WEIGHTS
            if pd.notna(row[f"{metric}_score"])
        ]
        available_weight = sum(WEIGHTS[metric] for metric in available)
        numerator = sum(
            row[f"{metric}_score"] * WEIGHTS[metric] for metric in available
        )
        available_weights.append(round(available_weight, 10))
        composite_scores.append(
            numerator / available_weight if available_weight else float("nan")
        )
        missing_metrics.append(
            ";".join(metric for metric in WEIGHTS if metric not in available)
        )
        data_statuses.append(
            "; ".join(
                f"{metric}:{row[f'{metric}_status']}" for metric in WEIGHTS
            )
        )

    result["available_weight"] = available_weights
    result["missing_metrics"] = missing_metrics
    result["data_status"] = data_statuses
    result["composite_score"] = pd.Series(composite_scores).round(2)
    result["rank"] = (
        result["composite_score"]
        .rank(method="min", ascending=False, na_option="bottom")
        .where(result["composite_score"].notna())
        .astype("Int64")
    )
    result = result.sort_values(
        ["composite_score", "industry"],
        ascending=[False, True],
        na_position="last",
    ).reset_index(drop=True)

    ordered = [
        "rank",
        "industry",
        "data_date",
        "composite_score",
        "news_heat",
        "news_heat_score",
        "market_return_3m",
        "market_return_3m_score",
        "policy_heat",
        "policy_heat_score",
        "available_weight",
        "missing_metrics",
        "data_status",
    ]
    result = result[ordered]
    if output_path is not None:
        write_csv(result, output_path)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Score industry momentum.")
    parser.add_argument(
        "--input",
        type=Path,
        default=PROCESSED_DIR / "industry_metrics_long.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPORTS_DIR / "industry_score.csv",
    )
    args = parser.parse_args()
    score_industries(pd.read_csv(args.input), output_path=args.output)


if __name__ == "__main__":
    main()
