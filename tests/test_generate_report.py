import pandas as pd

from scripts.generate_report import generate_report


def make_scores(ranked=True):
    return pd.DataFrame(
        [
            {
                "rank": 1 if ranked else pd.NA,
                "industry": "人工智能",
                "data_date": "2026-06-13",
                "composite_score": 88.0 if ranked else None,
                "capital_momentum_score": 80.0 if ranked else None,
                "tech_activity_score": 92.0 if ranked else None,
                "available_weight": 1.0 if ranked else 0.0,
                "ranking_status": "ranked" if ranked else "insufficient_history",
                "scoring_mode": (
                    "部分 momentum 模式"
                    if ranked
                    else "历史数据不足，暂不排名"
                ),
                "excluded_metrics": "github_repo_count_4w",
                "insufficient_metrics": "github_repo_count_4w",
                "data_status": "github_repo_count_4w:insufficient_history",
                "market_volume_change_4w": 0.15,
                "market_volume_change_4w_growth_rate_4w": 0.25,
                "market_volume_change_4w_momentum_status": "ok",
                "nvd_cve_count_4w": None,
                "nvd_cve_count_4w_growth_rate_4w": None,
                "nvd_cve_count_4w_momentum_status": "missing_config",
            },
            {
                "rank": 2 if ranked else pd.NA,
                "industry": "网络安全",
                "data_date": "2026-06-13",
                "composite_score": 72.0 if ranked else None,
                "capital_momentum_score": 70.0 if ranked else None,
                "tech_activity_score": 73.0 if ranked else None,
                "available_weight": 1.0 if ranked else 0.0,
                "ranking_status": "ranked" if ranked else "insufficient_history",
                "scoring_mode": (
                    "部分 momentum 模式"
                    if ranked
                    else "历史数据不足，暂不排名"
                ),
                "excluded_metrics": "github_repo_count_4w",
                "insufficient_metrics": "github_repo_count_4w",
                "data_status": "github_repo_count_4w:insufficient_history",
                "market_volume_change_4w": 0.05,
                "market_volume_change_4w_growth_rate_4w": None,
                "market_volume_change_4w_momentum_status": "insufficient_history",
                "nvd_cve_count_4w": 1864,
                "nvd_cve_count_4w_growth_rate_4w": 0.12,
                "nvd_cve_count_4w_momentum_status": "ok",
            },
        ]
    )


def test_report_discloses_momentum_mode_and_auxiliary_signals(tmp_path):
    report = tmp_path / "report.md"
    chart = tmp_path / "chart.png"

    generate_report(make_scores(), report_path=report, chart_path=chart)

    text = report.read_text(encoding="utf-8")
    assert "部分 momentum 模式" in text
    assert "market_volume_change_4w" in text
    assert "网络安全专项信号" in text
    assert "nvd_cve_count_4w" in text
    assert "至少 3 个行业" in text
    assert "不代表中国行业真实基本面" in text
    assert "相对自身历史的加速程度" in text
    assert chart.exists()


def test_report_handles_insufficient_history_without_ranking(tmp_path):
    report = tmp_path / "report.md"
    chart = tmp_path / "chart.png"

    generate_report(
        make_scores(ranked=False),
        report_path=report,
        chart_path=chart,
    )

    text = report.read_text(encoding="utf-8")
    assert "历史数据不足，暂不排名" in text
    assert "约 56 天" in text
    assert "当前暂无可排名行业" in text
    assert chart.exists()
