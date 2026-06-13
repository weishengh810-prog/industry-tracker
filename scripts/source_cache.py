from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from scripts.common import CACHE_DIR


def daily_cache_path(
    source: str,
    cache_dir: Path = CACHE_DIR,
    today: date | None = None,
) -> Path:
    cache_date = today or date.today()
    return cache_dir / f"{source}_{cache_date.isoformat()}.json"


def read_json_cache(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    return data if isinstance(data, dict) else None


def write_json_cache(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
