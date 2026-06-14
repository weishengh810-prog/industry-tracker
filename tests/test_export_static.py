from __future__ import annotations

import json
import sqlite3

import pandas as pd

from scripts.export_static import export_static
from scripts.store_to_db import SCHEMA


def _create_database(path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(SCHEMA)
        connection.executemany(
            """
            INSERT INTO industry_scores (
                date, industry, composite_score, ranking, ranking_status,
                capital_momentum_score, tech_activity_score,
                external_signal_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("2026-06-13", "人工智能", 80.0, 2, "ranked", 70.0, 85.0, None),
                ("2026-06-13", "半导体", 82.0, 1, "ranked", 75.0, 88.0, None),
                ("2026-06-14", "人工智能", 88.0, 1, "ranked", 90.0, 87.0, 60.0),
                ("2026-06-14", "半导体", 70.0, 2, "partial", 72.0, 68.0, None),
            ],
        )
        connection.executemany(
            """
            INSERT INTO daily_metrics (
                date, industry, metric, value, source, status
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("2026-06-13", "人工智能", "news_heat", 3.0, "news", "ok"),
                ("2026-06-14", "人工智能", "news_heat", 5.0, "news", "ok"),
                (
                    "2026-06-14",
                    "人工智能",
                    "market_return_4w",
                    0.12,
                    "market",
                    "ok",
                ),
                ("2026-06-14", "半导体", "news_heat", 2.0, "news", "ok"),
            ],
        )
        connection.executemany(
            """
            INSERT INTO momentum_features (
                date, industry, metric, growth_rate_4w, z_score_12w,
                freshness_days, momentum_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "2026-06-15",
                    "人工智能",
                    "news_heat",
                    0.25,
                    1.5,
                    1.0,
                    "ok",
                ),
                (
                    "2026-06-15",
                    "人工智能",
                    "market_return_4w",
                    0.10,
                    0.8,
                    1.0,
                    "ok",
                ),
                (
                    "2026-06-15",
                    "半导体",
                    "news_heat",
                    None,
                    None,
                    1.0,
                    "insufficient_history",
                ),
            ],
        )


def test_export_static_writes_complete_deterministic_public_data(tmp_path):
    db_path = tmp_path / "web" / "industry.db"
    output_dir = tmp_path / "docs" / "data"
    _create_database(db_path)
    (tmp_path / "archives" / "2026-06-13").mkdir(parents=True)
    (tmp_path / "archives" / "2026-06-14").mkdir()
    (tmp_path / "archives" / "not-a-date").mkdir()

    outputs = export_static(
        db_path,
        output_dir=output_dir,
        project_root=tmp_path,
    )
    first_contents = {
        name: path.read_bytes() for name, path in outputs.items()
    }
    export_static(
        db_path,
        output_dir=output_dir,
        project_root=tmp_path,
    )

    assert set(outputs) == {"meta", "ranking", "history"}
    assert all(path.exists() for path in outputs.values())
    assert {
        name: path.read_bytes() for name, path in outputs.items()
    } == first_contents

    meta = json.loads(outputs["meta"].read_text(encoding="utf-8"))
    assert meta == {
        "last_updated": "2026-06-15",
        "ranking_mode": "完整 momentum 模式",
        "insufficient_industries": [],
        "archive_days": 2,
        "days_until_full_mode": 26,
    }

    ranking_text = outputs["ranking"].read_text(encoding="utf-8")
    ranking = json.loads(ranking_text)
    assert "人工智能" in ranking_text
    assert "\\u4eba\\u5de5\\u667a\\u80fd" not in ranking_text
    assert [row["industry"] for row in ranking] == ["人工智能", "半导体"]
    assert ranking[0]["score_change"] == 8.0
    assert ranking[0]["ranking_change"] == 1
    assert ranking[1]["score_change"] == -12.0
    assert ranking[1]["ranking_change"] == -1
    assert ranking[0]["latest_metrics"] == {
        "daily_metrics": [
            {
                "date": "2026-06-14",
                "metric": "market_return_4w",
                "value": 0.12,
                "source": "market",
                "status": "ok",
            },
            {
                "date": "2026-06-14",
                "metric": "news_heat",
                "value": 5.0,
                "source": "news",
                "status": "ok",
            },
        ],
        "momentum_features": [
            {
                "date": "2026-06-15",
                "metric": "market_return_4w",
                "growth_rate_4w": 0.1,
                "z_score_12w": 0.8,
                "freshness_days": 1.0,
                "momentum_status": "ok",
            },
            {
                "date": "2026-06-15",
                "metric": "news_heat",
                "growth_rate_4w": 0.25,
                "z_score_12w": 1.5,
                "freshness_days": 1.0,
                "momentum_status": "ok",
            },
        ],
    }

    history = pd.read_csv(outputs["history"], encoding="utf-8-sig")
    assert history.columns.tolist() == [
        "date",
        "industry",
        "composite_score",
        "ranking",
        "ranking_status",
        "capital_momentum_score",
        "tech_activity_score",
        "external_signal_score",
        "score_change",
        "ranking_change",
    ]
    assert len(history) == 4
    latest_ai = history[
        (history["date"] == "2026-06-14")
        & (history["industry"] == "人工智能")
    ].iloc[0]
    assert latest_ai["capital_momentum_score"] == 90.0
    assert latest_ai["tech_activity_score"] == 87.0
    assert latest_ai["external_signal_score"] == 60.0
    assert latest_ai["score_change"] == 8.0
    assert latest_ai["ranking_change"] == 1.0


def test_export_static_writes_valid_empty_outputs(tmp_path):
    db_path = tmp_path / "web" / "industry.db"
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as connection:
        connection.executescript(SCHEMA)

    outputs = export_static(
        db_path,
        output_dir=tmp_path / "docs" / "data",
        project_root=tmp_path,
    )

    assert json.loads(outputs["meta"].read_text(encoding="utf-8")) == {
        "last_updated": None,
        "ranking_mode": "历史数据不足",
        "insufficient_industries": [],
        "archive_days": 0,
        "days_until_full_mode": 28,
    }
    assert json.loads(outputs["ranking"].read_text(encoding="utf-8")) == []
    history = pd.read_csv(outputs["history"], encoding="utf-8-sig")
    assert history.empty
    assert history.columns.tolist() == [
        "date",
        "industry",
        "composite_score",
        "ranking",
        "ranking_status",
        "capital_momentum_score",
        "tech_activity_score",
        "external_signal_score",
        "score_change",
        "ranking_change",
    ]
