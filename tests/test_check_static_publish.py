import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHECK_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "check_static_publish.py"


def _write_valid_static_site(docs_dir: Path) -> None:
    data_dir = docs_dir / "data"
    data_dir.mkdir(parents=True)
    (docs_dir / "index.html").write_text(
        '<a href="./data/history.csv">下载</a>',
        encoding="utf-8",
    )
    (data_dir / "meta.json").write_text(
        json.dumps({"last_updated": "2026-06-15"}),
        encoding="utf-8",
    )
    (data_dir / "ranking.json").write_text(
        json.dumps([{"industry": "人工智能"}]),
        encoding="utf-8",
    )
    (data_dir / "history.csv").write_text(
        "date,industry,composite_score\n"
        "2026-06-15,人工智能,88.0\n",
        encoding="utf-8",
    )


def _run_static_check(docs_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(CHECK_SCRIPT_PATH),
            "--docs-dir",
            str(docs_dir),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_static_publish_check_accepts_complete_isolated_site(tmp_path):
    docs_dir = tmp_path / "docs"
    _write_valid_static_site(docs_dir)

    result = _run_static_check(docs_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout
    assert "FAIL" not in result.stdout


def test_static_publish_check_rejects_dynamic_api_reference(tmp_path):
    docs_dir = tmp_path / "docs"
    _write_valid_static_site(docs_dir)
    (docs_dir / "index.html").write_text(
        '<script>fetch("/api/ranking")</script>',
        encoding="utf-8",
    )

    result = _run_static_check(docs_dir)

    assert result.returncode != 0
    assert "FAIL" in result.stdout
    assert "/api/" in result.stdout


def test_static_publish_check_rejects_sensitive_credentials(tmp_path):
    docs_dir = tmp_path / "docs"
    _write_valid_static_site(docs_dir)
    (docs_dir / "leaked.txt").write_text(
        "token = unsafe-example",
        encoding="utf-8",
    )

    result = _run_static_check(docs_dir)

    assert result.returncode != 0
    assert "FAIL" in result.stdout
    assert "sensitive credential pattern" in result.stdout


def test_static_publish_check_rejects_invalid_json(tmp_path):
    docs_dir = tmp_path / "docs"
    _write_valid_static_site(docs_dir)
    (docs_dir / "data" / "ranking.json").write_text(
        "{not-valid-json",
        encoding="utf-8",
    )

    result = _run_static_check(docs_dir)

    assert result.returncode != 0
    assert "ranking.json is not valid JSON" in result.stdout
