from __future__ import annotations

import sqlite3

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from scripts.store_to_db import SCHEMA
from web.app import create_app


@pytest.fixture
def web_client(tmp_path):
    static_dir = tmp_path / "web" / "static"
    static_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text(
        "<html><body>Industry dashboard</body></html>",
        encoding="utf-8",
    )
    db_path = tmp_path / "web" / "industry.db"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(SCHEMA)
    app = create_app(db_path=db_path, project_root=tmp_path)
    return TestClient(app), db_path, tmp_path


def _execute(db_path, sql, rows):
    with sqlite3.connect(db_path) as connection:
        connection.executemany(sql, rows)


def test_root_returns_dashboard_html(web_client):
    client, _, _ = web_client

    response = client.get("/")

    assert response.status_code == 200
    assert "Industry dashboard" in response.text


def test_ranking_returns_latest_scores_and_previous_period_changes(web_client):
    client, db_path, _ = web_client
    _execute(
        db_path,
        """
        INSERT INTO industry_scores (
            date, industry, composite_score, ranking, ranking_status,
            capital_momentum_score, tech_activity_score, external_signal_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("2026-06-12", "人工智能", 80.0, 2, "ranked", 82.0, 78.0, 75.0),
            ("2026-06-12", "半导体", 90.0, 1, "ranked", 91.0, 89.0, 86.0),
            ("2026-06-13", "人工智能", 85.0, 1, "ranked", 88.0, 82.0, 79.0),
            (
                "2026-06-13",
                "半导体",
                None,
                None,
                "insufficient_history",
                None,
                None,
                None,
            ),
        ],
    )

    response = client.get("/api/ranking")

    assert response.status_code == 200
    ranking = {row["industry"]: row for row in response.json()}
    assert ranking["人工智能"]["score_change"] == 5.0
    assert ranking["人工智能"]["ranking_change"] == 1
    assert ranking["半导体"]["composite_score"] is None
    assert ranking["半导体"]["score_change"] is None


def test_industry_detail_combines_latest_metrics_and_30_day_history(web_client):
    client, db_path, _ = web_client
    _execute(
        db_path,
        """
        INSERT INTO daily_metrics (
            date, industry, metric, value, source, status
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            ("2026-06-12", "人工智能", "news_heat", 7.0, "news", "ok"),
            ("2026-06-13", "人工智能", "news_heat", 8.0, "news", "ok"),
        ],
    )
    _execute(
        db_path,
        """
        INSERT INTO momentum_features (
            date, industry, metric, growth_rate_4w, z_score_12w,
            freshness_days, momentum_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [("2026-06-14", "人工智能", "news_heat", 0.2, 1.4, 1.0, "ok")],
    )
    _execute(
        db_path,
        """
        INSERT INTO industry_scores (
            date, industry, composite_score, ranking, ranking_status
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("2026-06-12", "人工智能", 80.0, 2, "ranked"),
            ("2026-06-13", "人工智能", 85.0, 1, "ranked"),
        ],
    )

    response = client.get("/api/industry/人工智能")

    assert response.status_code == 200
    payload = response.json()
    assert payload["industry"] == "人工智能"
    assert payload["latest_metrics"] == [
        {
            "metric": "news_heat",
            "value": 8.0,
            "source": "news",
            "status": "ok",
            "growth_rate_4w": 0.2,
            "z_score_12w": 1.4,
            "freshness_days": 1.0,
            "momentum_status": "ok",
        }
    ]
    assert [row["composite_score"] for row in payload["score_history_30d"]] == [
        80.0,
        85.0,
    ]
    assert len(payload["metric_history_30d"]) == 2


def test_history_uses_latest_database_date_as_window_end(web_client):
    client, db_path, _ = web_client
    _execute(
        db_path,
        """
        INSERT INTO industry_scores (
            date, industry, composite_score, ranking, ranking_status
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("2026-06-10", "人工智能", 70.0, 3, "ranked"),
            ("2026-06-12", "人工智能", 80.0, 2, "ranked"),
            ("2026-06-13", "人工智能", 85.0, 1, "ranked"),
        ],
    )

    response = client.get("/api/history", params={"days": 2})

    assert response.status_code == 200
    assert [row["date"] for row in response.json()] == [
        "2026-06-12",
        "2026-06-13",
    ]


def test_meta_reports_partial_mode_and_archive_progress(web_client):
    client, db_path, root = web_client
    _execute(
        db_path,
        """
        INSERT INTO industry_scores (
            date, industry, composite_score, ranking, ranking_status
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("2026-06-13", "人工智能", 85.0, 1, "ranked"),
            ("2026-06-13", "半导体", None, None, "insufficient_history"),
        ],
    )
    _execute(
        db_path,
        """
        INSERT INTO momentum_features (
            date, industry, metric, momentum_status
        ) VALUES (?, ?, ?, ?)
        """,
        [("2026-06-14", "人工智能", "news_heat", "ok")],
    )
    (root / "archives" / "2026-06-12").mkdir(parents=True)
    (root / "archives" / "2026-06-13").mkdir()
    (root / "archives" / "not-a-date").mkdir()

    response = client.get("/api/meta")

    assert response.status_code == 200
    assert response.json() == {
        "last_updated": "2026-06-14",
        "ranking_mode": "部分 momentum 模式",
        "insufficient_industries": ["半导体"],
        "archive_days": 2,
        "days_until_full_mode": 26,
    }


def test_meta_reports_trial_mode(web_client):
    client, db_path, root = web_client
    _execute(
        db_path,
        """
        INSERT INTO industry_scores (
            date, industry, composite_score, ranking, ranking_status
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("2026-06-13", "人工智能", 85.0, 1, "trial"),
            ("2026-06-13", "半导体", 80.0, 2, "trial"),
        ],
    )
    (root / "archives" / "2026-06-12").mkdir(parents=True)

    response = client.get("/api/meta")

    assert response.status_code == 200
    assert response.json()["ranking_mode"] == "试运行评分模式"
    assert response.json()["archive_days"] == 1


def test_download_latest_uses_bom_and_data_date_filename(web_client):
    client, _, root = web_client
    path = root / "data" / "processed" / "industry_metrics_long.csv"
    path.parent.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "industry": "人工智能",
                "date": "2026-06-13",
                "metric": "news_heat",
                "value": 8,
                "source": "news",
                "status": "ok",
            }
        ]
    ).to_csv(path, index=False)

    response = client.get("/api/download/latest")
    head_response = client.head("/api/download/latest")

    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert "industry_metrics_2026-06-13.csv" in response.headers[
        "content-disposition"
    ]
    assert head_response.status_code == 200


def test_download_scores_returns_404_when_report_is_missing(web_client):
    client, _, _ = web_client

    response = client.get("/api/download/scores")

    assert response.status_code == 404


def test_archive_download_validates_date_and_blocks_invalid_paths(web_client):
    client, _, root = web_client
    archive_path = (
        root
        / "archives"
        / "2026-06-12"
        / "processed"
        / "industry_metrics_long.csv"
    )
    archive_path.parent.mkdir(parents=True)
    pd.DataFrame(
        [{"industry": "人工智能", "metric": "news_heat", "value": 7}]
    ).to_csv(archive_path, index=False)

    invalid = client.get("/api/download/archive/2026-6-12")
    valid = client.get("/api/download/archive/2026-06-12")

    assert invalid.status_code == 422
    assert valid.status_code == 200
    assert valid.content.startswith(b"\xef\xbb\xbf")


def test_history_download_merges_archives_and_filters_industry(web_client):
    client, _, root = web_client
    for archive_date, industry in (
        ("2026-06-12", "人工智能"),
        ("2026-06-13", "半导体"),
    ):
        path = (
            root
            / "archives"
            / archive_date
            / "processed"
            / "industry_metrics_long.csv"
        )
        path.parent.mkdir(parents=True)
        pd.DataFrame(
            [{"industry": industry, "metric": "news_heat", "value": 1}]
        ).to_csv(path, index=False)

    response = client.get(
        "/api/download/history",
        params={"industry": "人工智能"},
    )

    assert response.status_code == 200
    decoded = response.content.decode("utf-8-sig")
    assert "人工智能" in decoded
    assert "半导体" not in decoded
    assert "2026-06-12" in decoded
