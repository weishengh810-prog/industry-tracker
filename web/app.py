from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response

from scripts.common import (
    is_valid_archive_date,
    ranking_mode_from_statuses,
    valid_archive_dates,
)
from scripts.store_to_db import SCHEMA

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "web" / "industry.db"


def _connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def _ensure_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.executescript(SCHEMA)


def _query(
    db_path: Path,
    sql: str,
    parameters: tuple[object, ...] = (),
) -> list[dict[str, object]]:
    with _connect(db_path) as connection:
        return [
            dict(row)
            for row in connection.execute(sql, parameters).fetchall()
        ]


def _scalar(
    db_path: Path,
    sql: str,
    parameters: tuple[object, ...] = (),
):
    with _connect(db_path) as connection:
        row = connection.execute(sql, parameters).fetchone()
    return row[0] if row else None


def _valid_archive_date(value: str) -> bool:
    return is_valid_archive_date(value)


def _archive_dates(project_root: Path) -> list[str]:
    return valid_archive_dates(project_root)


def _csv_response(
    frame: pd.DataFrame,
    filename: str,
    head_only: bool = False,
) -> Response:
    content = frame.to_csv(index=False).encode("utf-8-sig")
    encoded_filename = quote(filename)
    try:
        filename.encode("ascii")
        fallback_filename = filename
    except UnicodeEncodeError:
        fallback_filename = "industry_metrics_history.csv"
    headers = {
        "Content-Disposition": (
            f'attachment; filename="{fallback_filename}"; '
            f"filename*=UTF-8''{encoded_filename}"
        )
    }
    return Response(
        content=b"" if head_only else content,
        media_type="text/csv; charset=utf-8",
        headers=headers,
    )


def _read_download_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise HTTPException(status_code=404, detail="CSV file not found")
    return pd.read_csv(path, encoding="utf-8-sig")


def create_app(
    db_path: Path | str = DEFAULT_DB_PATH,
    project_root: Path | str = PROJECT_ROOT,
) -> FastAPI:
    target_db = Path(db_path).resolve()
    root = Path(project_root).resolve()
    _ensure_database(target_db)
    application = FastAPI(title="Industry Tracker Web")

    @application.get("/")
    def index() -> FileResponse:
        index_path = root / "web" / "static" / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=404, detail="Dashboard not found")
        return FileResponse(index_path, media_type="text/html")

    @application.get("/api/ranking")
    def ranking() -> list[dict[str, object]]:
        latest_date = _scalar(
            target_db,
            "SELECT MAX(date) FROM industry_scores",
        )
        if latest_date is None:
            return []
        previous_date = _scalar(
            target_db,
            "SELECT MAX(date) FROM industry_scores WHERE date < ?",
            (latest_date,),
        )
        current_rows = _query(
            target_db,
            """
            SELECT date, industry, composite_score, ranking, ranking_status,
                   capital_momentum_score, tech_activity_score,
                   external_signal_score
            FROM industry_scores
            WHERE date = ?
            ORDER BY CASE WHEN ranking IS NULL THEN 1 ELSE 0 END,
                     ranking, industry
            """,
            (latest_date,),
        )
        previous_rows = (
            _query(
                target_db,
                """
                SELECT industry, composite_score, ranking
                FROM industry_scores
                WHERE date = ?
                """,
                (previous_date,),
            )
            if previous_date
            else []
        )
        previous_by_industry = {
            str(row["industry"]): row for row in previous_rows
        }

        for row in current_rows:
            previous = previous_by_industry.get(str(row["industry"]))
            if row["ranking_status"] == "insufficient_history":
                row["composite_score"] = None
            current_score = row["composite_score"]
            previous_score = previous["composite_score"] if previous else None
            current_ranking = row["ranking"]
            previous_ranking = previous["ranking"] if previous else None
            row["score_change"] = (
                current_score - previous_score
                if current_score is not None and previous_score is not None
                else None
            )
            row["ranking_change"] = (
                previous_ranking - current_ranking
                if current_ranking is not None and previous_ranking is not None
                else None
            )
        return current_rows

    @application.get("/api/industry/{name}")
    def industry_detail(name: str) -> dict[str, object]:
        latest_metric_date = _scalar(
            target_db,
            "SELECT MAX(date) FROM daily_metrics WHERE industry = ?",
            (name,),
        )
        latest_momentum_date = _scalar(
            target_db,
            "SELECT MAX(date) FROM momentum_features WHERE industry = ?",
            (name,),
        )
        latest_metrics = []
        if latest_metric_date:
            latest_metrics = _query(
                target_db,
                """
                SELECT d.metric, d.value, d.source, d.status,
                       m.growth_rate_4w, m.z_score_12w,
                       m.freshness_days, m.momentum_status
                FROM daily_metrics AS d
                LEFT JOIN momentum_features AS m
                  ON m.industry = d.industry
                 AND m.metric = d.metric
                 AND m.date = ?
                WHERE d.industry = ? AND d.date = ?
                ORDER BY d.metric
                """,
                (latest_momentum_date, name, latest_metric_date),
            )

        latest_score_date = _scalar(
            target_db,
            "SELECT MAX(date) FROM industry_scores WHERE industry = ?",
            (name,),
        )
        score_history = []
        if latest_score_date:
            score_history = _query(
                target_db,
                """
                SELECT date, composite_score, ranking, ranking_status
                FROM industry_scores
                WHERE industry = ?
                  AND date >= date(?, '-29 days')
                ORDER BY date
                """,
                (name, latest_score_date),
            )

        metric_history = []
        if latest_metric_date:
            metric_history = _query(
                target_db,
                """
                SELECT date, metric, value, source, status
                FROM daily_metrics
                WHERE industry = ?
                  AND date >= date(?, '-29 days')
                ORDER BY date, metric
                """,
                (name, latest_metric_date),
            )

        if not latest_metrics and not score_history and not metric_history:
            raise HTTPException(status_code=404, detail="Industry not found")
        return {
            "industry": name,
            "latest_metrics": latest_metrics,
            "score_history_30d": score_history,
            "metric_history_30d": metric_history,
        }

    @application.get("/api/history")
    def history(
        days: int = Query(default=60, ge=1, le=3650),
    ) -> list[dict[str, object]]:
        latest_date = _scalar(
            target_db,
            "SELECT MAX(date) FROM industry_scores",
        )
        if latest_date is None:
            return []
        return _query(
            target_db,
            """
            SELECT date, industry, composite_score, ranking, ranking_status
            FROM industry_scores
            WHERE date >= date(?, ?)
            ORDER BY date, industry
            """,
            (latest_date, f"-{days - 1} days"),
        )

    @application.get("/api/meta")
    def meta() -> dict[str, object]:
        latest_dates = [
            _scalar(target_db, f"SELECT MAX(date) FROM {table}")
            for table in (
                "daily_metrics",
                "momentum_features",
                "industry_scores",
            )
        ]
        last_updated = max(
            (value for value in latest_dates if value is not None),
            default=None,
        )
        latest_score_date = latest_dates[-1]
        score_rows = (
            _query(
                target_db,
                """
                SELECT industry, ranking_status
                FROM industry_scores
                WHERE date = ?
                ORDER BY industry
                """,
                (latest_score_date,),
            )
            if latest_score_date
            else []
        )
        insufficient = [
            str(row["industry"])
            for row in score_rows
            if row["ranking_status"] == "insufficient_history"
        ]
        ranking_mode = ranking_mode_from_statuses(
            row["ranking_status"] for row in score_rows
        )

        archive_days = len(_archive_dates(root))
        return {
            "last_updated": last_updated,
            "ranking_mode": ranking_mode,
            "insufficient_industries": insufficient,
            "archive_days": archive_days,
            "days_until_full_mode": max(0, 28 - archive_days),
        }

    @application.api_route(
        "/api/download/latest",
        methods=["GET", "HEAD"],
    )
    def download_latest(request: Request) -> Response:
        frame = _read_download_csv(
            root / "data" / "processed" / "industry_metrics_long.csv"
        )
        data_date = (
            str(frame["date"].dropna().max())
            if "date" in frame and not frame["date"].dropna().empty
            else datetime.now().date().isoformat()
        )
        return _csv_response(
            frame,
            f"industry_metrics_{data_date}.csv",
            head_only=request.method == "HEAD",
        )

    @application.api_route(
        "/api/download/scores",
        methods=["GET", "HEAD"],
    )
    def download_scores(request: Request) -> Response:
        frame = _read_download_csv(root / "reports" / "industry_score.csv")
        data_date = (
            str(frame["data_date"].dropna().max())
            if "data_date" in frame and not frame["data_date"].dropna().empty
            else datetime.now().date().isoformat()
        )
        return _csv_response(
            frame,
            f"industry_scores_{data_date}.csv",
            head_only=request.method == "HEAD",
        )

    @application.api_route(
        "/api/download/archive/{archive_date}",
        methods=["GET", "HEAD"],
    )
    def download_archive(archive_date: str, request: Request) -> Response:
        if not _valid_archive_date(archive_date):
            raise HTTPException(status_code=422, detail="Invalid archive date")
        frame = _read_download_csv(
            root
            / "archives"
            / archive_date
            / "processed"
            / "industry_metrics_long.csv"
        )
        return _csv_response(
            frame,
            f"industry_metrics_{archive_date}.csv",
            head_only=request.method == "HEAD",
        )

    @application.api_route(
        "/api/download/history",
        methods=["GET", "HEAD"],
    )
    def download_history(
        request: Request,
        industry: str | None = None,
    ) -> Response:
        frames = []
        for archive_date in _archive_dates(root):
            path = (
                root
                / "archives"
                / archive_date
                / "processed"
                / "industry_metrics_long.csv"
            )
            if not path.exists():
                continue
            frame = pd.read_csv(path, encoding="utf-8-sig")
            frame["date"] = archive_date
            frames.append(frame)

        history_frame = (
            pd.concat(frames, ignore_index=True)
            if frames
            else pd.DataFrame(columns=["date", "industry"])
        )
        if industry is not None and "industry" in history_frame:
            history_frame = history_frame[
                history_frame["industry"].astype(str) == industry
            ]
        filename = (
            f"industry_metrics_history_{industry}.csv"
            if industry
            else "industry_metrics_history.csv"
        )
        return _csv_response(
            history_frame,
            filename,
            head_only=request.method == "HEAD",
        )

    return application


app = create_app()
