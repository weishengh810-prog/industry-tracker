from __future__ import annotations

import argparse
import math
import sys
from datetime import date, timedelta
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

MARKET_METRICS = (
    "market_return_3m",
    "market_return_4w",
    "market_volume_change_4w",
)
MIN_AVERAGE_VOLUME = 1_000
DOWNLOAD_CALENDAR_DAYS = 121


def _extract_series(
    frame: pd.DataFrame, columns: tuple[str, ...]
) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float)
    if isinstance(frame.columns, pd.MultiIndex):
        for column in columns:
            if column in frame.columns.get_level_values(0):
                values = frame.xs(column, axis=1, level=0)
                cleaned = values.iloc[:, 0].dropna().sort_index()
                if not cleaned.empty:
                    return cleaned
    for column in columns:
        if column in frame:
            values = frame[column]
            if isinstance(values, pd.DataFrame):
                values = values.iloc[:, 0]
            cleaned = values.dropna().sort_index()
            if not cleaned.empty:
                return cleaned
    return pd.Series(dtype=float)


def _extract_prices(frame: pd.DataFrame) -> pd.Series:
    return _extract_series(frame, ("Adj Close", "Close"))


def _extract_volume(frame: pd.DataFrame) -> pd.Series:
    volume = _extract_series(frame, ("Volume",))
    return volume[volume.map(lambda value: math.isfinite(float(value)))]


def _finite_positive_mean(values: pd.Series) -> float | None:
    finite_positive = [
        float(value)
        for value in values
        if math.isfinite(float(value)) and value > 0
    ]
    if not finite_positive:
        return None
    try:
        mean = math.fsum(finite_positive) / len(finite_positive)
    except OverflowError:
        return None
    return mean if math.isfinite(mean) else None


def _row(
    industry: dict[str, Any],
    metric: str,
    status: str,
    source: str,
    observation_date: str,
    value: float | None = None,
) -> dict[str, Any]:
    return {
        "industry": industry["name"],
        "date": observation_date,
        "metric": metric,
        "value": value,
        "source": source,
        "status": status,
    }


def _status_rows(
    industry: dict[str, Any],
    status: str,
    source: str,
) -> list[dict[str, Any]]:
    today = date.today().isoformat()
    return [
        _row(industry, metric, status, source, today)
        for metric in MARKET_METRICS
    ]


def _price_return(
    industry: dict[str, Any],
    prices: pd.Series,
    days: int,
    metric: str,
    source: str,
) -> dict[str, Any]:
    if prices.empty:
        return _row(
            industry,
            metric,
            "insufficient_data",
            source,
            date.today().isoformat(),
        )

    latest = pd.Timestamp(prices.index[-1])
    window_start = latest - pd.Timedelta(days=days - 1)
    window = prices[prices.index >= window_start]
    observation_date = latest.date().isoformat()
    if len(window) < 2:
        return _row(
            industry,
            metric,
            "insufficient_data",
            source,
            observation_date,
        )
    start_price = float(window.iloc[0])
    end_price = float(window.iloc[-1])
    if (
        not math.isfinite(start_price)
        or start_price <= 0
        or not math.isfinite(end_price)
        or end_price <= 0
    ):
        return _row(
            industry,
            metric,
            "insufficient_data",
            source,
            observation_date,
        )
    value = end_price / start_price - 1
    if not math.isfinite(value):
        return _row(
            industry,
            metric,
            "insufficient_data",
            source,
            observation_date,
        )
    return _row(
        industry,
        metric,
        "ok",
        source,
        observation_date,
        value,
    )


def _volume_change(
    industry: dict[str, Any],
    frame: pd.DataFrame,
    source: str,
) -> dict[str, Any]:
    metric = "market_volume_change_4w"
    volume = _extract_volume(frame)
    if volume.empty:
        return _row(
            industry,
            metric,
            "insufficient_data",
            source,
            date.today().isoformat(),
        )

    latest = pd.Timestamp(volume.index[-1])
    current_cutoff = latest - pd.Timedelta(days=28)
    previous_cutoff = latest - pd.Timedelta(days=56)
    current = volume[(volume.index > current_cutoff) & (volume.index <= latest)]
    previous = volume[
        (volume.index > previous_cutoff) & (volume.index <= current_cutoff)
    ]
    current_mean = _finite_positive_mean(current)
    previous_mean = _finite_positive_mean(previous)
    observation_date = latest.date().isoformat()

    if (
        current_mean is None
        or previous_mean is None
        or previous_mean == 0
        or current_mean < MIN_AVERAGE_VOLUME
        or previous_mean < MIN_AVERAGE_VOLUME
    ):
        return _row(
            industry,
            metric,
            "insufficient_data",
            source,
            observation_date,
        )
    value = current_mean / previous_mean - 1
    if not math.isfinite(value):
        return _row(
            industry,
            metric,
            "insufficient_data",
            source,
            observation_date,
        )
    return _row(
        industry,
        metric,
        "ok",
        source,
        observation_date,
        value,
    )


def market_rows(
    industry: dict[str, Any],
    offline: bool = False,
    downloader: Callable[..., pd.DataFrame] | None = None,
) -> list[dict[str, Any]]:
    proxy = industry.get("market_proxy")
    if proxy is None:
        return _status_rows(industry, "missing_config", "")
    if offline:
        raise ValueError("market_rows offline mode requires the sample collector")

    downloader = downloader or yf.download
    source = f"{proxy['name']} ({proxy['ticker']})"
    end = date.today() + timedelta(days=1)
    start = end - timedelta(days=DOWNLOAD_CALENDAR_DAYS)
    try:
        frame = downloader(
            proxy["ticker"],
            start=start,
            end=end,
            interval="1d",
            progress=False,
            auto_adjust=False,
        )
    except Exception as exc:
        setup_logging().exception(
            "market source failed | industry=%s | ticker=%s | error=%s",
            industry["name"],
            proxy["ticker"],
            exc,
        )
        return _status_rows(industry, "source_error", source)
    if frame.empty:
        setup_logging().error(
            "market source returned empty data | industry=%s | ticker=%s",
            industry["name"],
            proxy["ticker"],
        )
        return _status_rows(industry, "source_error", source)

    prices = _extract_prices(frame)
    return [
        _price_return(
            industry,
            prices,
            days=90,
            metric="market_return_3m",
            source=source,
        ),
        _price_return(
            industry,
            prices,
            days=28,
            metric="market_return_4w",
            source=source,
        ),
        _volume_change(industry, frame, source),
    ]


def market_row(
    industry: dict[str, Any],
    offline: bool = False,
    downloader: Callable[..., pd.DataFrame] | None = None,
) -> dict[str, Any]:
    """Compatibility wrapper returning only the three-month price row."""
    return market_rows(
        industry,
        offline=offline,
        downloader=downloader,
    )[0]


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

    rows = [
        row
        for industry in industries
        for row in market_rows(industry, downloader=downloader)
    ]
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
    parser = argparse.ArgumentParser(description="Collect market proxy metrics.")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument(
        "--no-fallback-samples", action="store_false", dest="fallback_samples"
    )
    args = parser.parse_args()
    collect_market(offline=args.offline, fallback_samples=args.fallback_samples)


if __name__ == "__main__":
    main()
