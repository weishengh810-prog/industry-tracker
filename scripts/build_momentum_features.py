from __future__ import annotations

import argparse
import math
import sys
from datetime import date
from pathlib import Path

import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.common import (
    LONG_COLUMNS,
    PROCESSED_DIR,
    PROJECT_ROOT,
    write_csv,
)

MOMENTUM_COLUMNS = [
    "industry",
    "metric",
    "growth_rate_4w",
    "z_score_12w",
    "freshness_days",
    "momentum_status",
]
USABLE_STATUSES = {"ok", "sample", "no_match"}


def _prepare_frame(frame: pd.DataFrame, priority: int) -> pd.DataFrame:
    missing_columns = [column for column in LONG_COLUMNS if column not in frame]
    if missing_columns:
        raise ValueError(f"Momentum input missing columns: {missing_columns}")

    prepared = frame[LONG_COLUMNS].copy()
    prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce")
    if prepared["date"].isna().any():
        raise ValueError("Momentum input has invalid dates")
    prepared["date"] = prepared["date"].dt.normalize()
    prepared["value"] = pd.to_numeric(prepared["value"], errors="coerce")
    prepared["_priority"] = priority
    return prepared


def _archive_paths(archives_dir: Path) -> list[Path]:
    if not archives_dir.exists():
        return []
    return sorted(
        path
        for path in archives_dir.rglob("industry_metrics_long.csv")
        if path.is_file() and path.parent.name == "processed"
    )


def _load_combined_history(
    current: pd.DataFrame,
    archives_dir: Path,
) -> pd.DataFrame:
    frames = [
        _prepare_frame(pd.read_csv(path), priority=0)
        for path in _archive_paths(archives_dir)
    ]
    frames.append(_prepare_frame(current, priority=1))
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(
        ["_priority", "date"], kind="stable"
    ).drop_duplicates(
        ["industry", "metric", "date"],
        keep="last",
    )
    return combined.sort_values(
        ["industry", "metric", "date"], kind="stable"
    ).reset_index(drop=True)


def _finite_history(group: pd.DataFrame) -> pd.DataFrame:
    finite = group["value"].map(
        lambda value: pd.notna(value) and math.isfinite(value)
    )
    return group[group["status"].isin(USABLE_STATUSES) & finite]


def _growth_rate(
    usable: pd.DataFrame,
    latest: pd.Timestamp,
) -> float | None:
    previous_start = latest - pd.Timedelta(days=55)
    previous_end = latest - pd.Timedelta(days=28)
    current_start = latest - pd.Timedelta(days=27)

    if usable.empty or usable["date"].min() > previous_start:
        return None

    previous = usable.loc[
        usable["date"].between(previous_start, previous_end),
        "value",
    ]
    current = usable.loc[
        usable["date"].between(current_start, latest),
        "value",
    ]
    if previous.empty or current.empty:
        return None

    previous_mean = previous.mean()
    current_mean = current.mean()
    if (
        not math.isfinite(previous_mean)
        or not math.isfinite(current_mean)
        or previous_mean == 0
    ):
        return None

    growth = (current_mean / previous_mean) - 1
    return float(growth) if math.isfinite(growth) else None


def _z_score(
    usable: pd.DataFrame,
    latest: pd.Timestamp,
) -> float | None:
    window_start = latest - pd.Timedelta(days=83)
    if usable.empty or usable["date"].min() > window_start:
        return None

    window = usable.loc[
        usable["date"].between(window_start, latest),
        "value",
    ]
    if len(window) < 2:
        return None

    mean = window.mean()
    standard_deviation = window.std()
    if (
        not math.isfinite(mean)
        or not math.isfinite(standard_deviation)
        or standard_deviation == 0
    ):
        return None

    score = (window.iloc[-1] - mean) / standard_deviation
    return float(score) if math.isfinite(score) else None


def _build_group_row(
    industry: object,
    metric: object,
    group: pd.DataFrame,
    build_date: date,
) -> dict[str, object]:
    latest_row = group.iloc[-1]
    latest = latest_row["date"]
    freshness_days = (build_date - latest.date()).days
    status = latest_row["status"]

    if status not in USABLE_STATUSES:
        return {
            "industry": industry,
            "metric": metric,
            "growth_rate_4w": None,
            "z_score_12w": None,
            "freshness_days": freshness_days,
            "momentum_status": status,
        }

    latest_value = latest_row["value"]
    if pd.isna(latest_value) or not math.isfinite(latest_value):
        return {
            "industry": industry,
            "metric": metric,
            "growth_rate_4w": None,
            "z_score_12w": None,
            "freshness_days": freshness_days,
            "momentum_status": "insufficient_history",
        }

    usable = _finite_history(group)
    growth = _growth_rate(usable, latest)
    z_score = _z_score(usable, latest)
    return {
        "industry": industry,
        "metric": metric,
        "growth_rate_4w": growth,
        "z_score_12w": z_score,
        "freshness_days": freshness_days,
        "momentum_status": "ok" if growth is not None else "insufficient_history",
    }


def build_momentum_features(
    long_frame: pd.DataFrame | None = None,
    input_path: Path = PROCESSED_DIR / "industry_metrics_long.csv",
    archives_dir: Path = PROJECT_ROOT / "archives",
    output_path: Path = PROCESSED_DIR / "momentum_features.csv",
    today: date | None = None,
) -> pd.DataFrame:
    current = pd.read_csv(input_path) if long_frame is None else long_frame.copy()
    combined = _load_combined_history(current, archives_dir)
    build_date = today or date.today()
    rows = [
        _build_group_row(industry, metric, group, build_date)
        for (industry, metric), group in combined.groupby(
            ["industry", "metric"],
            sort=True,
        )
    ]
    result = pd.DataFrame(rows, columns=MOMENTUM_COLUMNS)
    write_csv(result, output_path)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build per-metric historical momentum features."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=PROCESSED_DIR / "industry_metrics_long.csv",
    )
    parser.add_argument(
        "--archives-dir",
        type=Path,
        default=PROJECT_ROOT / "archives",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROCESSED_DIR / "momentum_features.csv",
    )
    args = parser.parse_args()
    build_momentum_features(
        input_path=args.input,
        archives_dir=args.archives_dir,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
