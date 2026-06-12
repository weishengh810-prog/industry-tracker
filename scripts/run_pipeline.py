from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Callable

import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_dataset import build_dataset
from scripts.common import (
    LONG_COLUMNS,
    PROJECT_ROOT,
    SAMPLES_DIR,
    ensure_directories,
    load_industries,
    setup_logging,
    write_csv,
)
from scripts.fetch_market import collect_market
from scripts.fetch_news import collect_news
from scripts.fetch_policy import collect_policy
from scripts.generate_report import generate_report
from scripts.score_industries import score_industries


def _source_error_frame(metric: str | list[str], source: str) -> pd.DataFrame:
    metrics = [metric] if isinstance(metric, str) else metric
    return pd.DataFrame(
        [
            {
                "industry": item["name"],
                "date": date.today().isoformat(),
                "metric": current_metric,
                "value": None,
                "source": source,
                "status": "source_error",
            }
            for item in load_industries()
            for current_metric in metrics
        ],
        columns=LONG_COLUMNS,
    )


def _run_collector(
    name: str,
    metric: str | list[str],
    output_path: Path,
    collector: Callable[[], pd.DataFrame],
    logger,
) -> pd.DataFrame:
    try:
        frame = collector()
        logger.info(
            "collector completed | collector=%s | rows=%s", name, len(frame)
        )
        return frame
    except Exception as exc:
        logger.exception(
            "collector crashed; continuing with source_error rows | collector=%s | error=%s",
            name,
            exc,
        )
        frame = _source_error_frame(metric, name)
        write_csv(frame, output_path)
        return frame


def run_pipeline(
    offline: bool = False,
    fallback_samples: bool = True,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Path]:
    project_root = Path(project_root)
    ensure_directories(project_root)
    logger = setup_logging(project_root)

    raw_dir = project_root / "data" / "raw"
    processed_dir = project_root / "data" / "processed"
    reports_dir = project_root / "reports"
    charts_dir = project_root / "charts"
    news_path = raw_dir / "news_daily.csv"
    policy_path = raw_dir / "policy_daily.csv"
    market_path = raw_dir / "market_daily.csv"

    _run_collector(
        "news",
        "news_heat",
        news_path,
        lambda: collect_news(
            offline=offline,
            fallback_samples=fallback_samples,
            output_path=news_path,
            sample_path=SAMPLES_DIR / "news_daily.csv",
        ),
        logger,
    )
    _run_collector(
        "policy",
        "policy_heat",
        policy_path,
        lambda: collect_policy(
            offline=offline,
            fallback_samples=fallback_samples,
            output_path=policy_path,
            sample_path=SAMPLES_DIR / "policy_daily.csv",
        ),
        logger,
    )
    _run_collector(
        "market",
        "market_return_3m",
        market_path,
        lambda: collect_market(
            offline=offline,
            fallback_samples=fallback_samples,
            output_path=market_path,
            sample_path=SAMPLES_DIR / "market_daily.csv",
        ),
        logger,
    )

    long_path = processed_dir / "industry_metrics_long.csv"
    score_path = reports_dir / "industry_score.csv"
    report_path = reports_dir / "industry_report.md"
    chart_path = charts_dir / "industry_score_bar.png"

    long_frame = build_dataset(raw_dir=raw_dir, output_path=long_path)
    scores = score_industries(long_frame, output_path=score_path)
    generate_report(scores, report_path=report_path, chart_path=chart_path)
    logger.info("pipeline completed | offline=%s", offline)

    return {
        "long_table": long_path,
        "score": score_path,
        "report": report_path,
        "chart": chart_path,
        "log": project_root / "logs" / "industry_tracker.log",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the industry tracker pipeline.")
    parser.add_argument("--offline", action="store_true")
    fallback_group = parser.add_mutually_exclusive_group()
    fallback_group.add_argument(
        "--fallback-samples",
        action="store_true",
        dest="fallback_samples",
        default=True,
    )
    fallback_group.add_argument(
        "--no-fallback-samples",
        action="store_false",
        dest="fallback_samples",
    )
    args = parser.parse_args()
    run_pipeline(
        offline=args.offline,
        fallback_samples=args.fallback_samples,
    )


if __name__ == "__main__":
    main()
