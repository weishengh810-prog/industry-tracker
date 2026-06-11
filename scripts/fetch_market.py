from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import yfinance as yf

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.common import (
    LONG_COLUMNS,
    RAW_DIR,
    SAMPLES_DIR,
    load_industries,
    setup_logging,
    write_csv,
)


def _extract_prices(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float)
    if isinstance(frame.columns, pd.MultiIndex):
        for column in ("Adj Close", "Close"):
            if column in frame.columns.get_level_values(0):
                values = frame.xs(column, axis=1, level=0)
                return values.iloc[:, 0].dropna()
    for column in ("Adj Close", "Close"):
        if column in frame:
            values = frame[column]
            if isinstance(values, pd.DataFrame):
                values = values.iloc[:, 0]
            return values.dropna()
    return pd.Series(dtype=float)


def market_row(
    industry: dict[str, Any],
    offline: bool = False,
    downloader: Callable[..., pd.DataFrame] | None = None,
) -> dict[str, Any]:
    proxy = industry.get("market_proxy")
    if proxy is None:
        return {
            "industry": industry["name"],
            "date": date.today().isoformat(),
            "metric": "market_return_3m",
            "value": None,
            "source": "",
            "status": "missing_config",
        }
    if offline:
        raise ValueError("market_row offline mode requires the sample collector")

    downloader = downloader or yf.download
    logger = setup_logging()
    try:
        frame = downloader(
            proxy["ticker"],
            period="3mo",
            interval="1d",
            progress=False,
            auto_adjust=False,
        )
        prices = _extract_prices(frame)
        if len(prices) < 2:
            return {
                "industry": industry["name"],
                "date": date.today().isoformat(),
                "metric": "market_return_3m",
                "value": None,
                "source": f"{proxy['name']} ({proxy['ticker']})",
                "status": "insufficient_data",
            }
        return {
            "industry": industry["name"],
            "date": pd.Timestamp(prices.index[-1]).date().isoformat(),
            "metric": "market_return_3m",
            "value": float(prices.iloc[-1] / prices.iloc[0] - 1),
            "source": f"{proxy['name']} ({proxy['ticker']})",
            "status": "ok",
        }
    except Exception as exc:
        logger.exception(
            "market source failed | industry=%s | ticker=%s | error=%s",
            industry["name"],
            proxy["ticker"],
            exc,
        )
        return {
            "industry": industry["name"],
            "date": date.today().isoformat(),
            "metric": "market_return_3m",
            "value": None,
            "source": f"{proxy['name']} ({proxy['ticker']})",
            "status": "source_error",
        }


def _sample_market(sample_path: Path) -> pd.DataFrame:
    return pd.read_csv(sample_path)[LONG_COLUMNS]


def collect_market(
    offline: bool = False,
    fallback_samples: bool = True,
    output_path: Path | None = None,
    sample_path: Path | None = None,
    industries: list[dict[str, Any]] | None = None,
    downloader: Callable[..., pd.DataFrame] | None = None,
) -> pd.DataFrame:
    output_path = output_path or RAW_DIR / "market_daily.csv"
    sample_path = sample_path or SAMPLES_DIR / "market_daily.csv"
    industries = industries or load_industries()

    if offline:
        frame = _sample_market(sample_path)
        write_csv(frame, output_path)
        return frame

    rows = [market_row(item, downloader=downloader) for item in industries]
    frame = pd.DataFrame(rows, columns=LONG_COLUMNS)
    configured = frame[frame["status"] != "missing_config"]
    if (
        fallback_samples
        and not configured.empty
        and not configured["status"].eq("ok").any()
    ):
        setup_logging().warning(
            "all configured market proxies failed; using offline samples"
        )
        frame = _sample_market(sample_path)

    write_csv(frame, output_path)
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect market proxy returns.")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument(
        "--no-fallback-samples", action="store_false", dest="fallback_samples"
    )
    args = parser.parse_args()
    collect_market(offline=args.offline, fallback_samples=args.fallback_samples)


if __name__ == "__main__":
    main()
