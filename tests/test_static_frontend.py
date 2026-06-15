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
    assert "latest_metrics?.daily_metrics" in html
    assert "latest_metrics?.momentum_features" in html
    assert "capital_momentum_score" in html
    assert "tech_activity_score" in html
    assert "external_signal_score" in html
    assert "historyChart" in html
    assert "detailChart" in html
    assert "@media (max-width:" in html


def test_static_dashboard_has_bi_loading_filter_and_empty_states():
    html = INDEX_PATH.read_text(encoding="utf-8")

    assert "skeleton-card" in html
    assert "chart-skeleton" in html
    assert "filteredRanking" in html
    assert 'topN: "all"' in html
    assert "Top 3" in html
    assert "Top 5" in html
    assert "Top 10" in html
    assert 'value="3"' in html
    assert 'value="5"' in html
    assert 'value="10"' in html
    assert 'value="all"' in html
    assert 'placeholder="搜索行业名称"' in html
    assert "没有符合当前筛选条件的行业" in html
    assert (
        "历史数据仍在积累中。当前有效数据点不足，"
        "折线图将在更多每日归档生成后自动显示。"
    ) in html
    assert "hasEnoughHistoryData" in html


def test_static_dashboard_discloses_trial_mode_and_keeps_progress():
    html = INDEX_PATH.read_text(encoding="utf-8")

    assert "试运行评分 / 历史不足，仅供观察" in html
    assert "meta.ranking_mode === '试运行评分模式'" in html
    assert "`${meta.archive_days || 0} / 28 天`" in html


def test_static_dashboard_explains_metrics_and_chart_tooltips():
    html = INDEX_PATH.read_text(encoding="utf-8")

    assert "综合分：当前行业相对动量综合评分。" in html
    assert "资本动量：市场代理指标形成的相对动量。" in html
    assert "技术活跃度：arXiv / GitHub 等技术信号形成的相对动量。" in html
    assert "外部信号：目前仅辅助观察，不一定参与主评分。" in html
    assert "较上期：和上一评分日期相比的排名或得分变化。" in html
    assert "tooltipRows" in html
    assert "日期" in html
    assert "综合分" in html
    assert "资本动量" in html
    assert "技术活跃度" in html
    assert "排名" in html
    assert "暂无数据" in html


def test_static_dashboard_marks_selected_card_and_animates_detail():
    html = INDEX_PATH.read_text(encoding="utf-8")

    assert "rank-card selected" in html or "selectedIndustry === item.industry" in html
    assert "detail-transition" in html
    assert "chart-fade" in html


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
    assert (
        "0 6 * * * /home/admin/industry-tracker/scripts/daily_update.sh "
        ">> /home/admin/industry-tracker/logs/daily_update.log 2>&1"
    ) in readme
    assert "bash scripts/daily_update.sh" in readme
    assert "tail -n 100 logs/daily_update.log" in readme
    assert "git status" in readme
    assert "试运行评分模式" in readme
    assert "history_days < 28" in readme
    assert "最新截面值" in readme
    assert "每个指标独立计算行业截面百分位" in readme
    assert "不再回退到最新截面值" in readme
    assert "完整 momentum 模式" in readme
    assert "部分 momentum 模式" in readme
