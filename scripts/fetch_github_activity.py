from __future__ import annotations

import argparse
import math
import random
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

GITHUB_ENDPOINT = "https://api.github.com/search/repositories"
GITHUB_SOURCE = "GitHub Search API"
COVERED_INDUSTRIES = {"人工智能", "半导体", "机器人", "网络安全"}
GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "industry-tracker/1.0",
}


def _quote_term(term: str) -> str:
    return f'"{term}"' if any(character.isspace() for character in term) else term


def _build_query(industry: dict[str, Any], today: date) -> str:
    terms = " OR ".join(_quote_term(term) for term in industry["keywords_en"][:2])
    cutoff = (today - timedelta(days=28)).isoformat()
    return f"{terms} created:>{cutoff}"


def _total_count(payload: Any) -> int:
    if not isinstance(payload, dict):
        raise ValueError("GitHub response must be an object")
    if payload.get("incomplete_results") is not False:
        raise ValueError("GitHub incomplete_results must be false")
    count = payload.get("total_count")
    if type(count) is not int or count < 0:
        raise ValueError("GitHub total_count must be a nonnegative integer")
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
        "metric": "github_repo_count_4w",
        "value": value,
        "source": GITHUB_SOURCE,
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
        if name not in COVERED_INDUSTRIES:
            rows.append(_row(name, today, None, "missing_config"))
            continue
        entry = _cache_entry(cached.get(name))
        if entry is None:
            return None
        rows.append(_row(name, today, entry["value"], entry["status"]))
    return rows


def collect_github_activity(
    offline: bool = False,
    output_path: Path | None = None,
    sample_path: Path | None = None,
    industries: list[dict[str, Any]] | None = None,
    requester: Callable[..., Any] = requests.get,
    sleeper: Callable[[float], Any] = time.sleep,
    random_uniform: Callable[[float, float], float] = random.uniform,
    cache_dir: Path = CACHE_DIR,
    today: date | None = None,
) -> pd.DataFrame:
    output_path = output_path or RAW_DIR / "github_daily.csv"
    sample_path = sample_path or SAMPLES_DIR / "github_daily.csv"

    if offline:
        frame = pd.read_csv(sample_path)[LONG_COLUMNS]
        write_csv(frame, output_path)
        return frame

    current_date = today or date.today()
    configured_industries = industries if industries is not None else load_industries()
    cache_path = daily_cache_path("github", cache_dir=cache_dir, today=current_date)
    cached = read_json_cache(cache_path)
    if cached is not None:
        rows = _cached_rows(cached, configured_industries, current_date)
        if rows is not None:
            frame = pd.DataFrame(rows, columns=LONG_COLUMNS)
            write_csv(frame, output_path)
            return frame

    rows = []
    cache_data = {}
    for industry in configured_industries:
        name = industry["name"]
        if name not in COVERED_INDUSTRIES:
            rows.append(_row(name, current_date, None, "missing_config"))
            continue

        try:
            response = requester(
                GITHUB_ENDPOINT,
                params={
                    "q": _build_query(industry, current_date),
                    "per_page": 1,
                },
                headers=GITHUB_HEADERS,
                timeout=30,
            )
            response.raise_for_status()
            count = _total_count(response.json())
            status = "ok" if count else "no_match"
            value = count
        except Exception as exc:
            setup_logging().exception(
                "GitHub request failed | endpoint=%s | industry=%s | error=%s",
                GITHUB_ENDPOINT,
                name,
                exc,
            )
            status = "source_error"
            value = None
        finally:
            sleeper(random_uniform(60, 75))

        rows.append(_row(name, current_date, value, status))
        cache_data[name] = {"value": value, "status": status}

    write_json_cache(cache_path, cache_data)
    frame = pd.DataFrame(rows, columns=LONG_COLUMNS)
    write_csv(frame, output_path)
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect four-week GitHub activity.")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    collect_github_activity(offline=args.offline)


if __name__ == "__main__":
    main()
