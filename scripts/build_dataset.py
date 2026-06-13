from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.common import (
    LONG_COLUMNS,
    PROCESSED_DIR,
    RAW_DIR,
    VALID_METRICS,
    VALID_STATUSES,
    write_csv,
)

RAW_FILES = (
    "news_daily.csv",
    "policy_daily.csv",
    "market_daily.csv",
    "arxiv_daily.csv",
    "github_daily.csv",
    "nvd_daily.csv",
)


def _normalize_frame(frame: pd.DataFrame, source_file: str) -> pd.DataFrame:
    missing_columns = [column for column in LONG_COLUMNS if column not in frame]
    if missing_columns:
        raise ValueError(f"{source_file} missing columns: {missing_columns}")

    frame = frame[LONG_COLUMNS].copy()
    unknown_metrics = set(frame["metric"].dropna()) - VALID_METRICS
    if unknown_metrics:
        raise ValueError(f"{source_file} has unknown metrics: {unknown_metrics}")
    unknown_statuses = set(frame["status"].dropna()) - VALID_STATUSES
    if unknown_statuses:
        raise ValueError(f"{source_file} has unknown statuses: {unknown_statuses}")

    dates = pd.to_datetime(frame["date"], errors="coerce")
    if dates.isna().any():
        raise ValueError(f"{source_file} has invalid dates")
    frame["date"] = dates.dt.date.astype(str)
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    return frame


def build_dataset(
    raw_dir: Path = RAW_DIR,
    output_path: Path = PROCESSED_DIR / "industry_metrics_long.csv",
) -> pd.DataFrame:
    frames = []
    for filename in RAW_FILES:
        path = raw_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Required raw file not found: {path}")
        frames.append(_normalize_frame(pd.read_csv(path), filename))

    result = pd.concat(frames, ignore_index=True)
    result = result.sort_values(
        ["date", "industry", "metric"], kind="stable"
    ).reset_index(drop=True)
    write_csv(result, output_path)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Build canonical industry long table.")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROCESSED_DIR / "industry_metrics_long.csv",
    )
    args = parser.parse_args()
    build_dataset(raw_dir=args.raw_dir, output_path=args.output)


if __name__ == "__main__":
    main()
