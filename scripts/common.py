from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
SAMPLES_DIR = DATA_DIR / "samples"
REPORTS_DIR = PROJECT_ROOT / "reports"
CHARTS_DIR = PROJECT_ROOT / "charts"
LOGS_DIR = PROJECT_ROOT / "logs"

LONG_COLUMNS = ["industry", "date", "metric", "value", "source", "status"]
VALID_METRICS = {
    "news_heat",
    "policy_heat",
    "market_return_3m",
    "market_return_4w",
    "market_volume_change_4w",
    "arxiv_paper_count_4w",
    "github_repo_count_4w",
    "nvd_cve_count_4w",
}
VALID_STATUSES = {
    "ok",
    "sample",
    "missing_config",
    "source_error",
    "insufficient_data",
    "no_match",
}
ARCHIVE_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def ensure_directories(root: Path = PROJECT_ROOT) -> None:
    for relative in (
        "data/cache",
        "data/raw",
        "data/processed",
        "data/samples",
        "reports",
        "charts",
        "logs",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)


def valid_archive_dates(root: Path = PROJECT_ROOT) -> list[str]:
    archives_dir = Path(root) / "archives"
    if not archives_dir.exists():
        return []

    valid_dates = []
    for path in archives_dir.iterdir():
        if not path.is_dir() or not is_valid_archive_date(path.name):
            continue
        valid_dates.append(path.name)
    return sorted(valid_dates)


def is_valid_archive_date(value: str) -> bool:
    if not ARCHIVE_DATE_PATTERN.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def current_pipeline_date(root: Path = PROJECT_ROOT) -> str | None:
    current_path = (
        Path(root)
        / "data"
        / "processed"
        / "industry_metrics_long.csv"
    )
    if not current_path.exists():
        return None

    try:
        current = pd.read_csv(current_path, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        return None
    if "date" not in current:
        return None

    valid_dates = {
        str(value).strip()
        for value in current["date"].dropna()
        if is_valid_archive_date(str(value).strip())
    }
    return max(valid_dates, default=None)


def history_dates(root: Path = PROJECT_ROOT) -> list[str]:
    dates = set(valid_archive_dates(root))
    current_date = current_pipeline_date(root)
    if current_date is not None:
        dates.add(current_date)
    return sorted(dates)


def history_days(root: Path = PROJECT_ROOT) -> int:
    return len(history_dates(root))


def ranking_mode_from_statuses(statuses: Iterable[str]) -> str:
    values = [str(status) for status in statuses if status]
    if not values or all(
        status == "insufficient_history" for status in values
    ):
        return "历史数据不足"
    if "trial" in values:
        return "试运行评分模式"
    if "partial" in values or "insufficient_history" in values:
        return "部分 momentum 模式"
    return "完整 momentum 模式"


def setup_logging(root: Path | None = None) -> logging.Logger:
    logger = logging.getLogger("industry_tracker")
    if root is None and logger.handlers:
        return logger

    target_root = Path(root) if root is not None else PROJECT_ROOT
    target_main_log = (target_root / "logs" / "industry_tracker.log").resolve()
    current_main_log = getattr(logger, "_industry_tracker_main_log", None)
    if logger.handlers and current_main_log == target_main_log:
        return logger

    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()

    ensure_directories(target_root)

    logger.setLevel(logging.INFO)
    logger.propagate = False
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    file_handler = logging.FileHandler(
        target_main_log, encoding="utf-8"
    )
    error_handler = logging.FileHandler(
        target_root / "logs" / "error.log", encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    stream_handler = logging.StreamHandler()
    file_handler.setFormatter(formatter)
    error_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(error_handler)
    logger.addHandler(stream_handler)
    logger._industry_tracker_main_log = target_main_log
    return logger


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_industries(path: Path | None = None) -> list[dict[str, Any]]:
    config = load_json(path or CONFIG_DIR / "industries.json")
    return config["industries"]


def load_sources(path: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    return load_json(path or CONFIG_DIR / "sources.json")


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")
