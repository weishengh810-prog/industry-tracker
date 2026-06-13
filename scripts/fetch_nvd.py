from __future__ import annotations

import argparse
import math
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import requests

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.common import (
    CACHE_DIR,
    LONG_COLUMNS,
    RAW_DIR,
    SAMPLES_DIR,
    load_industries,
    setup_logging,
    write_csv,
)
from scripts.source_cache import daily_cache_path, read_json_cache, write_json_cache

NVD_ENDPOINT = "https://services.nvd.nist.gov/rest/json/cves/2.0"
NVD_SOURCE = "NVD CVE API"
COVERED_INDUSTRY = "网络安全"


def _request_params(today: date) -> dict[str, str | int]:
    start = today - timedelta(days=27)
    return {
        "pubStartDate": f"{start.isoformat()}T00:00:00.000Z",
        "pubEndDate": f"{today.isoformat()}T23:59:59.999Z",
        "resultsPerPage": 1,
    }


def _total_results(payload: Any) -> int:
    if not isinstance(payload, dict):
        raise ValueError("NVD response must be an object")
    count = payload.get("totalResults")
    if type(count) is not int or count < 0:
        raise ValueError("NVD totalResults must be a nonnegative integer")
    return count


def _row(
    industry: str,
    today: date,
    value: int | None,
    status: str,
) -> dict[str, Any]:
    return {
        "industry": industry,
        "date": today.isoformat(),
        "metric": "nvd_cve_count_4w",
        "value": value,
        "source": NVD_SOURCE,
        "status": status,
    }


def _cache_entry(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        status = payload.get("status")
        value = payload.get("value")
        if status == "ok" and type(value) is int and value > 0:
            return {"value": value, "status": status}
        if status == "no_match" and type(value) is int and value == 0:
            return {"value": value, "status": status}
        if status == "source_error" and value is None:
            return {"value": value, "status": status}
        return None
    if (
        isinstance(payload, (int, float))
        and not isinstance(payload, bool)
        and math.isfinite(payload)
        and payload >= 0
        and float(payload).is_integer()
    ):
        value = int(payload)
        return {
            "value": value,
            "status": "ok" if value else "no_match",
        }
    return None


def _cached_rows(
    cached: dict[str, Any],
    industries: list[dict[str, Any]],
    today: date,
) -> list[dict[str, Any]] | None:
    rows = []
    for industry in industries:
        name = industry["name"]
        if name != COVERED_INDUSTRY:
            rows.append(_row(name, today, None, "missing_config"))
            continue
        entry = _cache_entry(cached.get(name))
        if entry is None:
            return None
        rows.append(_row(name, today, entry["value"], entry["status"]))
    return rows


def collect_nvd(
    offline: bool = False,
    output_path: Path | None = None,
    sample_path: Path | None = None,
    industries: list[dict[str, Any]] | None = None,
    requester: Callable[..., Any] = requests.get,
    sleeper: Callable[[float], Any] = time.sleep,
    cache_dir: Path = CACHE_DIR,
    today: date | None = None,
) -> pd.DataFrame:
    output_path = output_path or RAW_DIR / "nvd_daily.csv"
    sample_path = sample_path or SAMPLES_DIR / "nvd_daily.csv"

    if offline:
        frame = pd.read_csv(sample_path)[LONG_COLUMNS]
        write_csv(frame, output_path)
        return frame

    current_date = today or date.today()
    configured_industries = industries if industries is not None else load_industries()
    cache_path = daily_cache_path("nvd", cache_dir=cache_dir, today=current_date)
    cached = read_json_cache(cache_path)
    if cached is not None:
        rows = _cached_rows(cached, configured_industries, current_date)
        if rows is not None:
            frame = pd.DataFrame(rows, columns=LONG_COLUMNS)
            write_csv(frame, output_path)
            return frame

    value = None
    status = "missing_config"
    has_covered_industry = any(
        industry["name"] == COVERED_INDUSTRY
        for industry in configured_industries
    )
    if has_covered_industry:
        try:
            response = requester(
                NVD_ENDPOINT,
                params=_request_params(current_date),
                timeout=30,
            )
            response.raise_for_status()
            value = _total_results(response.json())
            status = "ok" if value else "no_match"
        except Exception as exc:
            setup_logging().exception(
                "NVD request failed | endpoint=%s | industry=%s | error=%s",
                NVD_ENDPOINT,
                COVERED_INDUSTRY,
                exc,
            )
            value = None
            status = "source_error"
        finally:
            sleeper(6)

    rows = [
        _row(
            industry["name"],
            current_date,
            value if industry["name"] == COVERED_INDUSTRY else None,
            status if industry["name"] == COVERED_INDUSTRY else "missing_config",
        )
        for industry in configured_industries
    ]
    cache_data = (
        {COVERED_INDUSTRY: {"value": value, "status": status}}
        if has_covered_industry
        else {}
    )
    write_json_cache(cache_path, cache_data)
    frame = pd.DataFrame(rows, columns=LONG_COLUMNS)
    write_csv(frame, output_path)
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect four-week NVD CVE activity.")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    collect_nvd(offline=args.offline)


if __name__ == "__main__":
    main()
