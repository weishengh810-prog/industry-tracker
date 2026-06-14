from __future__ import annotations

import sqlite3

from scripts.run_pipeline import run_pipeline


def test_offline_pipeline_stores_outputs_in_sqlite(tmp_path):
    run_pipeline(offline=True, project_root=tmp_path)

    db_path = tmp_path / "web" / "industry.db"
    assert db_path.exists()
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM daily_metrics").fetchone()[0] > 0
        assert (
            connection.execute("SELECT COUNT(*) FROM momentum_features").fetchone()[0]
            > 0
        )
        assert connection.execute("SELECT COUNT(*) FROM industry_scores").fetchone()[0] > 0


def test_store_failure_does_not_fail_pipeline(tmp_path, monkeypatch):
    calls = []

    def fail_store(db_path):
        calls.append(db_path)
        raise RuntimeError("database unavailable")

    monkeypatch.setattr("scripts.store_to_db.store_to_db", fail_store)

    outputs = run_pipeline(offline=True, project_root=tmp_path)

    assert calls == [tmp_path / "web" / "industry.db"]
    assert outputs["long_table"].exists()
    assert outputs["score"].exists()
