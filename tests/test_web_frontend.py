from pathlib import Path


INDEX_PATH = Path(__file__).resolve().parents[1] / "web" / "static" / "index.html"


def test_dashboard_contains_required_views_and_dependencies():
    html = INDEX_PATH.read_text(encoding="utf-8")

    assert "cdnjs.cloudflare.com/ajax/libs/alpinejs/" in html
    assert "cdnjs.cloudflare.com/ajax/libs/Chart.js/" in html
    assert "主看板" in html
    assert "行业详情" in html
    assert "历史对比" in html
    assert "/api/download/latest" in html
    assert "/api/download/scores" in html
    assert "/api/download/history" in html
    assert "数据积累中" in html
    assert "historyChart" in html
    assert "detailChart" in html
    assert "@media (max-width:" in html
