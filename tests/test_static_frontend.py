from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = PROJECT_ROOT / "docs" / "index.html"
README_PATH = PROJECT_ROOT / "README.md"


def test_static_dashboard_uses_only_relative_public_data_files():
    html = INDEX_PATH.read_text(encoding="utf-8")

    assert 'fetch("./data/meta.json")' in html
    assert 'fetch("./data/ranking.json")' in html
    assert 'fetch("./data/history.csv")' in html
    assert 'href="./data/history.csv"' in html
    assert "/api/" not in html


def test_static_dashboard_retains_core_views_and_nested_metric_contract():
    html = INDEX_PATH.read_text(encoding="utf-8")

    assert "cdnjs.cloudflare.com/ajax/libs/alpinejs/" in html
    assert "cdnjs.cloudflare.com/ajax/libs/Chart.js/" in html
    assert "主看板" in html
    assert "行业详情" in html
    assert "历史对比" in html
    assert "最后更新" in html
    assert "当前评分模式" in html
    assert "历史积累进度" in html
    assert "行业排名" in html
    assert "latest_metrics.daily_metrics" in html
    assert "latest_metrics.momentum_features" in html
    assert "capital_momentum_score" in html
    assert "tech_activity_score" in html
    assert "external_signal_score" in html
    assert "historyChart" in html
    assert "detailChart" in html
    assert "@media (max-width:" in html


def test_readme_documents_dynamic_and_static_deployment():
    readme = README_PATH.read_text(encoding="utf-8")

    assert "FastAPI" in readme
    assert "ECS" in readme
    assert "GitHub Pages" in readme
    assert "Settings" in readme
    assert "Pages" in readme
    assert "/docs" in readme
    assert "python scripts/store_to_db.py" in readme
    assert "python scripts/export_static.py" in readme
    assert "scripts/daily_update.sh" in readme
    assert "SSH deploy key" in readme
    assert "token" in readme.lower()
    assert "私钥" in readme
