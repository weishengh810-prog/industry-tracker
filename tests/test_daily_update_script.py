from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "daily_update.sh"
)


def test_daily_update_exports_and_conditionally_pushes_static_site():
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    pipeline = "python scripts/run_pipeline.py"
    store = "python scripts/store_to_db.py"
    export = "python scripts/export_static.py"
    assert pipeline in script
    assert store in script
    assert export in script
    assert script.index(pipeline) < script.index(store) < script.index(export)
    assert "docs/" in script
    assert "git diff --cached --quiet" in script
    assert script.index("git commit") < script.index("git push")
    assert 'echo "No changes to commit"' in script


def test_daily_update_keeps_existing_archive_workflow():
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'TODAY=$(date +%F)' in script
    assert 'ARCHIVE_DIR="archives/${TODAY}"' in script
    assert 'mkdir -p "${ARCHIVE_DIR}/processed"' in script
    assert (
        'cp data/processed/industry_metrics_long.csv '
        '"${ARCHIVE_DIR}/processed/industry_metrics_long.csv"'
    ) in script
    assert (
        'cp reports/industry_score.csv '
        '"${ARCHIVE_DIR}/reports/industry_score.csv"'
    ) in script
