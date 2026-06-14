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


def test_daily_update_prevents_overlap_and_logs_push_failures():
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "logs/daily_update.log" in script
    assert "command -v flock" in script
    assert "flock -n" in script
    assert "LOCK_DIR" in script
    assert "mkdir" in script
    assert "if ! git push; then" in script
    assert "git push failed" in script
    assert "exit 1" in script


def test_daily_update_stages_all_publish_outputs():
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    staging = script[script.index("git add") : script.index("git diff --cached")]
    for output_dir in ("docs/", "reports/", "charts/", "data/", "archives/"):
        assert output_dir in staging


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
