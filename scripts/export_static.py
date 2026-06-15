from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.common import history_days, ranking_mode_from_statuses

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "web" / "industry.db"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "docs" / "data"
HISTORY_COLUMNS = [
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


def _connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


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


def _history_rows(db_path: Path) -> list[dict[str, object]]:
    rows = _query(
        db_path,
        """
        SELECT date, industry, composite_score, ranking, ranking_status,
               capital_momentum_score, tech_activity_score,
               external_signal_score
        FROM industry_scores
        ORDER BY date, industry
        """,
    )
    previous_by_industry: dict[str, dict[str, object]] = {}
    for row in rows:
        industry = str(row["industry"])
        previous = previous_by_industry.get(industry)
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
        previous_by_industry[industry] = row
    return rows


def _latest_daily_metrics(
    db_path: Path,
    industry: str,
) -> list[dict[str, object]]:
    latest_date = _scalar(
        db_path,
        "SELECT MAX(date) FROM daily_metrics WHERE industry = ?",
        (industry,),
    )
    if latest_date is None:
        return []
    return _query(
        db_path,
        """
        SELECT date, metric, value, source, status
        FROM daily_metrics
        WHERE industry = ? AND date = ?
        ORDER BY metric
        """,
        (industry, latest_date),
    )


def _latest_momentum_features(
    db_path: Path,
    industry: str,
) -> list[dict[str, object]]:
    latest_date = _scalar(
        db_path,
        "SELECT MAX(date) FROM momentum_features WHERE industry = ?",
        (industry,),
    )
    if latest_date is None:
        return []
    return _query(
        db_path,
        """
        SELECT date, metric, growth_rate_4w, z_score_12w,
               freshness_days, momentum_status
        FROM momentum_features
        WHERE industry = ? AND date = ?
        ORDER BY metric
        """,
        (industry, latest_date),
    )


def _latest_ranking(
    db_path: Path,
    history: list[dict[str, object]],
) -> list[dict[str, object]]:
    if not history:
        return []
    latest_date = max(str(row["date"]) for row in history)
    latest_rows = [
        dict(row) for row in history if str(row["date"]) == latest_date
    ]
    latest_rows.sort(
        key=lambda row: (
            row["ranking"] is None,
            row["ranking"] if row["ranking"] is not None else 0,
            str(row["industry"]),
        )
    )
    for row in latest_rows:
        if row["ranking_status"] == "insufficient_history":
            row["composite_score"] = None
        industry = str(row["industry"])
        row["latest_metrics"] = {
            "daily_metrics": _latest_daily_metrics(db_path, industry),
            "momentum_features": _latest_momentum_features(db_path, industry),
        }
    return latest_rows


def _meta(db_path: Path, project_root: Path) -> dict[str, object]:
    latest_dates = [
        _scalar(db_path, f"SELECT MAX(date) FROM {table}")
        for table in ("daily_metrics", "momentum_features", "industry_scores")
    ]
    last_updated = max(
        (value for value in latest_dates if value is not None),
        default=None,
    )
    latest_score_date = latest_dates[-1]
    score_rows = (
        _query(
            db_path,
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

    data_days = history_days(project_root)
    return {
        "last_updated": last_updated,
        "ranking_mode": ranking_mode,
        "insufficient_industries": insufficient,
        "archive_days": data_days,
        "days_until_full_mode": max(0, 28 - data_days),
    }


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_history(
    path: Path,
    history: list[dict[str, object]],
) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=HISTORY_COLUMNS,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(history)


def export_static(
    db_path: Path | str = DEFAULT_DB_PATH,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    project_root: Path | str = PROJECT_ROOT,
) -> dict[str, Path]:
    target_db = Path(db_path).resolve()
    target_dir = Path(output_dir).resolve()
    root = Path(project_root).resolve()
    if not target_db.exists():
        raise FileNotFoundError(f"SQLite database not found: {target_db}")
    target_dir.mkdir(parents=True, exist_ok=True)

    history = _history_rows(target_db)
    ranking = _latest_ranking(target_db, history)
    meta = _meta(target_db, root)

    outputs = {
        "meta": target_dir / "meta.json",
        "ranking": target_dir / "ranking.json",
        "history": target_dir / "history.csv",
    }
    _write_json(outputs["meta"], meta)
    _write_json(outputs["ranking"], ranking)
    _write_history(outputs["history"], history)
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export SQLite dashboard data for GitHub Pages."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    export_static(
        db_path=args.db,
        output_dir=args.output_dir,
        project_root=args.project_root,
    )


if __name__ == "__main__":
    main()
