from __future__ import annotations

import argparse
import math
import sys
import time
import xml.etree.ElementTree as ET
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

ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"
ARXIV_SOURCE = "arXiv API"
COVERED_INDUSTRIES = {"人工智能", "半导体", "机器人", "医药健康"}
ATOM_ENTRY = "{http://www.w3.org/2005/Atom}entry"
OPENSEARCH_TOTAL_RESULTS = (
    "{http://a9.com/-/spec/opensearch/1.1/}totalResults"
)


def _build_query(industry: dict[str, Any], today: date) -> str:
    keywords = industry["keywords_en"][:2]
    terms = " OR ".join(f'all:"{keyword}"' for keyword in keywords)
    start = (today - timedelta(days=27)).strftime("%Y%m%d0000")
    end = today.strftime("%Y%m%d2359")
    return f"({terms}) AND submittedDate:[{start} TO {end}]"


def _count_entries(content: bytes) -> int:
    root = ET.fromstring(content)
    total_results = root.find(OPENSEARCH_TOTAL_RESULTS)
    if total_results is not None:
        count = int(total_results.text or "")
        if count < 0:
            raise ValueError("arXiv totalResults cannot be negative")
        return count
    return sum(1 for _ in root.iter(ATOM_ENTRY))


def _row(
    industry: str,
    today: date,
    value: int | None,
    status: str,
) -> dict[str, Any]:
    return {
        "industry": industry,
        "date": today.isoformat(),
        "metric": "arxiv_paper_count_4w",
        "value": value,
        "source": ARXIV_SOURCE,
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


def collect_arxiv(
    offline: bool = False,
    output_path: Path | None = None,
    sample_path: Path | None = None,
    industries: list[dict[str, Any]] | None = None,
    requester: Callable[..., Any] = requests.get,
    sleeper: Callable[[float], Any] = time.sleep,
    cache_dir: Path = CACHE_DIR,
    today: date | None = None,
) -> pd.DataFrame:
    output_path = output_path or RAW_DIR / "arxiv_daily.csv"
    sample_path = sample_path or SAMPLES_DIR / "arxiv_daily.csv"

    if offline:
        frame = pd.read_csv(sample_path)[LONG_COLUMNS]
        write_csv(frame, output_path)
        return frame

    current_date = today or date.today()
    configured_industries = industries if industries is not None else load_industries()
    cache_path = daily_cache_path("arxiv", cache_dir=cache_dir, today=current_date)
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
                ARXIV_ENDPOINT,
                params={
                    "search_query": _build_query(industry, current_date),
                    "start": 0,
                    "max_results": 1,
                },
                timeout=30,
            )
            response.raise_for_status()
            count = _count_entries(response.content)
            status = "ok" if count else "no_match"
            value = count
        except Exception as exc:
            setup_logging().exception(
                "arXiv request failed | endpoint=%s | industry=%s | error=%s",
                ARXIV_ENDPOINT,
                name,
                exc,
            )
            status = "source_error"
            value = None
        finally:
            sleeper(3)

        rows.append(_row(name, current_date, value, status))
        cache_data[name] = {"value": value, "status": status}

    write_json_cache(cache_path, cache_data)
    frame = pd.DataFrame(rows, columns=LONG_COLUMNS)
    write_csv(frame, output_path)
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect four-week arXiv activity.")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    collect_arxiv(offline=args.offline)


if __name__ == "__main__":
    main()
