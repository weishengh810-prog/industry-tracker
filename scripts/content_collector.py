from __future__ import annotations

from datetime import date, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin

import feedparser
import pandas as pd
import requests
from bs4 import BeautifulSoup

from scripts.common import LONG_COLUMNS


def match_industries(title: str, industries: list[dict[str, Any]]) -> list[str]:
    normalized = title.casefold()
    return [
        item["name"]
        for item in industries
        if any(keyword.casefold() in normalized for keyword in item["keywords"])
    ]


def normalize_date(value: Any) -> str:
    if not value:
        return date.today().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    try:
        return parsedate_to_datetime(text).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        parsed = pd.to_datetime(text, errors="coerce")
        return (
            date.today().isoformat()
            if pd.isna(parsed)
            else parsed.date().isoformat()
        )


def fetch_feed_entries(source: dict[str, Any], timeout: int = 15) -> list[dict]:
    response = requests.get(
        source["url"],
        timeout=timeout,
        headers={"User-Agent": "industry-tracker/1.0"},
    )
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    if feed.bozo and not feed.entries:
        raise ValueError(f"RSS parse failed: {feed.bozo_exception}")
    return [
        {
            "title": entry.get("title", "").strip(),
            "date": normalize_date(
                entry.get("published") or entry.get("updated") or entry.get("date")
            ),
            "link": entry.get("link", ""),
            "source": source["name"],
        }
        for entry in feed.entries
        if entry.get("title")
    ]


def fetch_html_entries(source: dict[str, Any], timeout: int = 15) -> list[dict]:
    response = requests.get(
        source["url"],
        timeout=timeout,
        headers={"User-Agent": "industry-tracker/1.0"},
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    entries: list[dict] = []
    for item in soup.select(source["item_selector"]):
        title_node = item.select_one(source.get("title_selector", "a"))
        if title_node is None:
            continue
        date_node = item.select_one(source.get("date_selector", "span"))
        href = title_node.get("href", "")
        entries.append(
            {
                "title": title_node.get_text(" ", strip=True),
                "date": normalize_date(
                    date_node.get_text(" ", strip=True) if date_node else None
                ),
                "link": urljoin(source["url"], href),
                "source": source["name"],
            }
        )
    return entries


def fetch_source_entries(source: dict[str, Any], timeout: int = 15) -> list[dict]:
    if source["type"] == "rss":
        return fetch_feed_entries(source, timeout)
    if source["type"] == "html":
        return fetch_html_entries(source, timeout)
    raise ValueError(f"Unsupported source type: {source['type']}")


def aggregate_entries(
    entries: list[dict],
    industries: list[dict[str, Any]],
    metric: str,
    status: str = "ok",
) -> pd.DataFrame:
    matched: dict[tuple[str, str], dict[str, set[str]]] = {}
    for entry in entries:
        for industry in match_industries(entry["title"], industries):
            key = (industry, entry["date"])
            bucket = matched.setdefault(key, {"titles": set(), "sources": set()})
            bucket["titles"].add(entry["title"])
            bucket["sources"].add(entry["source"])

    rows = [
        {
            "industry": industry,
            "date": entry_date,
            "metric": metric,
            "value": len(values["titles"]),
            "source": "; ".join(sorted(values["sources"])),
            "status": status,
        }
        for (industry, entry_date), values in matched.items()
    ]
    matched_industries = {row["industry"] for row in rows}
    source_names = "; ".join(sorted({entry["source"] for entry in entries}))
    for industry in industries:
        if industry["name"] not in matched_industries:
            rows.append(
                {
                    "industry": industry["name"],
                    "date": date.today().isoformat(),
                    "metric": metric,
                    "value": 0,
                    "source": source_names or "configured_sources",
                    "status": "no_match" if status == "ok" else status,
                }
            )
    return pd.DataFrame(rows, columns=LONG_COLUMNS)
