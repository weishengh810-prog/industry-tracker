import subprocess
import sys

import pytest

from scripts.common import PROJECT_ROOT


@pytest.mark.parametrize(
    "script_name",
    [
        "fetch_news.py",
        "fetch_policy.py",
        "fetch_market.py",
        "fetch_arxiv.py",
        "fetch_github_activity.py",
        "fetch_nvd.py",
        "build_dataset.py",
        "build_momentum_features.py",
        "score_industries.py",
        "generate_report.py",
        "run_pipeline.py",
        "export_static.py",
    ],
)
def test_script_can_run_directly(script_name):
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / script_name), "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
