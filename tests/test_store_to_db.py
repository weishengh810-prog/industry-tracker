from __future__ import annotations

import sqlite3
from datetime import date

import pandas as pd

from scripts.store_to_db import store_to_db


def _write_csv(root, relative_path, rows):
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


def test_store_to_db_upserts_all_supported_csv_files(tmp_path):
    _write_csv(
        tmp_path,
        "data/processed/industry_metrics_long.csv",
        [
            {
                "industry": "人工智能",
                "date": "2026-06-13",
                "metric": "news_heat",
                "value": 8.0,
                "source": "news",
                "status": "ok",
            }
        ],
    )
    _write_csv(
        tmp_path,
        "data/processed/momentum_features.csv",
        [
            {
                "industry": "人工智能",
                "metric": "news_heat",
                "growth_rate_4w": 0.25,
                "z_score_12w": 1.5,
                "freshness_days": 1,
                "momentum_status": "ok",
            }
        ],
    )
    _write_csv(
        tmp_path,
        "reports/industry_score.csv",
        [
            {
                "rank": 1,
                "industry": "人工智能",
                "data_date": "2026-06-13",
                "composite_score": 88.5,
                "ranking_status": "ranked",
                "capital_momentum_score": 90.0,
                "tech_activity_score": 85.0,
                "external_signal_score": 80.0,
                "ignored_column": "not stored",
            }
        ],
    )
    db_path = tmp_path / "web" / "industry.db"

    store_to_db(db_path)
    store_to_db(db_path)

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM daily_metrics").fetchone()[0] == 1
        assert (
            connection.execute("SELECT COUNT(*) FROM momentum_features").fetchone()[0]
            == 1
        )
        assert connection.execute("SELECT COUNT(*) FROM industry_scores").fetchone()[0] == 1
        momentum = connection.execute(
            """
            SELECT date, industry, metric, growth_rate_4w, z_score_12w,
                   freshness_days, momentum_status
            FROM momentum_features
            """
        ).fetchone()
        score = connection.execute(
            """
            SELECT date, industry, composite_score, ranking, ranking_status,
                   capital_momentum_score, tech_activity_score,
                   external_signal_score
            FROM industry_scores
            """
        ).fetchone()

    assert momentum == (
        date.today().isoformat(),
        "人工智能",
        "news_heat",
        0.25,
        1.5,
        1.0,
        "ok",
    )
    assert score == (
        "2026-06-13",
        "人工智能",
        88.5,
        1,
        "ranked",
        90.0,
        85.0,
        80.0,
    )


def test_store_to_db_skips_missing_csv_files(tmp_path):
    db_path = tmp_path / "web" / "industry.db"

    store_to_db(db_path)

    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("daily_metrics", "momentum_features", "industry_scores")
        }

    assert {"daily_metrics", "momentum_features", "industry_scores"} <= tables
    assert counts == {
        "daily_metrics": 0,
        "momentum_features": 0,
        "industry_scores": 0,
    }
