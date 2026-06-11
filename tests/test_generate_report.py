import pandas as pd

from scripts.generate_report import generate_report


def test_report_discloses_proxy_and_degraded_data(tmp_path):
    scores = pd.DataFrame(
        [
            {
                "rank": 1,
                "industry": "人工智能",
                "composite_score": 90.0,
                "news_heat": 8,
                "market_return_3m": 0.12,
                "policy_heat": 5,
                "news_heat_score": 100,
                "market_return_3m_score": 100,
                "policy_heat_score": 100,
                "available_weight": 1.0,
                "missing_metrics": "",
                "data_status": "sample",
            }
        ]
    )
    report = tmp_path / "report.md"
    chart = tmp_path / "chart.png"

    generate_report(scores, report_path=report, chart_path=chart)

    text = report.read_text(encoding="utf-8")
    assert "代理指标" in text
    assert "不代表行业真实市场规模" in text
    assert "sample" in text
    assert chart.exists()
