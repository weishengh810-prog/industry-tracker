from __future__ import annotations

import logging
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger("industry_tracker")

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    industry TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL,
    source TEXT,
    status TEXT,
    UNIQUE(date, industry, metric)
);

CREATE TABLE IF NOT EXISTS momentum_features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    industry TEXT NOT NULL,
    metric TEXT NOT NULL,
    growth_rate_4w REAL,
    z_score_12w REAL,
    freshness_days REAL,
    momentum_status TEXT,
    UNIQUE(date, industry, metric)
);

CREATE TABLE IF NOT EXISTS industry_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    industry TEXT NOT NULL,
    composite_score REAL,
    ranking INTEGER,
    ranking_status TEXT,
    capital_momentum_score REAL,
    tech_activity_score REAL,
    external_signal_score REAL,
    UNIQUE(date, industry)
);
"""


def _db_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _read_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        logger.info("database import skipped; file missing | path=%s", path)
        return None
    return pd.read_csv(path, encoding="utf-8-sig")


def _has_columns(frame: pd.DataFrame, required: set[str], path: Path) -> bool:
    missing = sorted(required - set(frame.columns))
    if not missing:
        return True
    logger.warning(
        "database import skipped; required columns missing | path=%s | columns=%s",
        path,
        ",".join(missing),
    )
    return False


def _store_daily_metrics(connection: sqlite3.Connection, path: Path) -> None:
    frame = _read_csv(path)
    required = {"date", "industry", "metric"}
    if frame is None or not _has_columns(frame, required, path):
        return

    rows = [
        tuple(
            _db_value(row.get(column))
            for column in ("date", "industry", "metric", "value", "source", "status")
        )
        for row in frame.to_dict("records")
    ]
    connection.executemany(
        """
        INSERT INTO daily_metrics (
            date, industry, metric, value, source, status
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(date, industry, metric) DO UPDATE SET
            value = excluded.value,
            source = excluded.source,
            status = excluded.status
        """,
        rows,
    )


def _store_momentum_features(connection: sqlite3.Connection, path: Path) -> None:
    frame = _read_csv(path)
    required = {"industry", "metric"}
    if frame is None or not _has_columns(frame, required, path):
        return

    run_date = date.today().isoformat()
    rows = [
        (
            run_date,
            _db_value(row.get("industry")),
            _db_value(row.get("metric")),
            _db_value(row.get("growth_rate_4w")),
            _db_value(row.get("z_score_12w")),
            _db_value(row.get("freshness_days")),
            _db_value(row.get("momentum_status")),
        )
        for row in frame.to_dict("records")
    ]
    connection.executemany(
        """
        INSERT INTO momentum_features (
            date, industry, metric, growth_rate_4w, z_score_12w,
            freshness_days, momentum_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date, industry, metric) DO UPDATE SET
            growth_rate_4w = excluded.growth_rate_4w,
            z_score_12w = excluded.z_score_12w,
            freshness_days = excluded.freshness_days,
            momentum_status = excluded.momentum_status
        """,
        rows,
    )


def _store_industry_scores(connection: sqlite3.Connection, path: Path) -> None:
    frame = _read_csv(path)
    required = {"data_date", "industry"}
    if frame is None or not _has_columns(frame, required, path):
        return

    rows = [
        (
            _db_value(row.get("data_date")),
            _db_value(row.get("industry")),
            _db_value(row.get("composite_score")),
            _db_value(row.get("rank")),
            _db_value(row.get("ranking_status")),
            _db_value(row.get("capital_momentum_score")),
            _db_value(row.get("tech_activity_score")),
            _db_value(row.get("external_signal_score")),
        )
        for row in frame.to_dict("records")
    ]
    connection.executemany(
        """
        INSERT INTO industry_scores (
            date, industry, composite_score, ranking, ranking_status,
            capital_momentum_score, tech_activity_score,
            external_signal_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date, industry) DO UPDATE SET
            composite_score = excluded.composite_score,
            ranking = excluded.ranking,
            ranking_status = excluded.ranking_status,
            capital_momentum_score = excluded.capital_momentum_score,
            tech_activity_score = excluded.tech_activity_score,
            external_signal_score = excluded.external_signal_score
        """,
        rows,
    )


def store_to_db(db_path: Path | str = "web/industry.db") -> None:
    target = Path(db_path).resolve()
    project_root = target.parent.parent
    target.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(target) as connection:
        connection.executescript(SCHEMA)
        _store_daily_metrics(
            connection,
            project_root / "data" / "processed" / "industry_metrics_long.csv",
        )
        _store_momentum_features(
            connection,
            project_root / "data" / "processed" / "momentum_features.csv",
        )
        _store_industry_scores(
            connection,
            project_root / "reports" / "industry_score.csv",
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    store_to_db()
