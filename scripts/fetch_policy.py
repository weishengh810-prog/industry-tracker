from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.common import (
    LONG_COLUMNS,
    RAW_DIR,
    SAMPLES_DIR,
    load_industries,
    load_sources,
    setup_logging,
    write_csv,
)
from scripts.content_collector import aggregate_entries, fetch_source_entries


def _sample_policy(sample_path: Path) -> pd.DataFrame:
    frame = pd.read_csv(sample_path)
    frame["status"] = "sample"
    return frame[LONG_COLUMNS]


def _error_rows(industries: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "industry": item["name"],
                "date": date.today().isoformat(),
                "metric": "policy_heat",
                "value": None,
                "source": "configured_sources",
                "status": "source_error",
            }
            for item in industries
        ],
        columns=LONG_COLUMNS,
    )


def collect_policy(
    offline: bool = False,
    fallback_samples: bool = True,
    output_path: Path | None = None,
    sources: list[dict[str, Any]] | None = None,
    sample_path: Path | None = None,
) -> pd.DataFrame:
    output_path = output_path or RAW_DIR / "policy_daily.csv"
    sample_path = sample_path or SAMPLES_DIR / "policy_daily.csv"
    industries = load_industries()
    logger = setup_logging()

    if offline:
        frame = _sample_policy(sample_path)
        write_csv(frame, output_path)
        return frame

    configured_sources = sources if sources is not None else load_sources()["policy"]
    entries: list[dict] = []
    successful_sources = 0
    for source in configured_sources:
        try:
            entries.extend(fetch_source_entries(source))
            successful_sources += 1
        except Exception as exc:
            logger.exception(
                "policy source failed | source=%s | error=%s",
                source.get("name", source.get("url", "unknown")),
                exc,
            )

    if successful_sources:
        frame = aggregate_entries(entries, industries, "policy_heat")
    elif fallback_samples:
        logger.warning("all policy sources failed; using offline samples")
        frame = _sample_policy(sample_path)
    else:
        frame = _error_rows(industries)

    write_csv(frame, output_path)
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect industry policy heat.")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument(
        "--no-fallback-samples", action="store_false", dest="fallback_samples"
    )
    args = parser.parse_args()
    collect_policy(offline=args.offline, fallback_samples=args.fallback_samples)


if __name__ == "__main__":
    main()
