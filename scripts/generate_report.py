from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.common import CHARTS_DIR, REPORTS_DIR

plt.rcParams["font.sans-serif"] = [
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK SC",
    "Arial Unicode MS",
    "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False


def _display(value: Any, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _markdown_table(frame: pd.DataFrame, columns: list[tuple[str, str]]) -> str:
    header = "| " + " | ".join(label for _, label in columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    rows = [
        "| "
        + " | ".join(_display(row.get(column)) for column, _ in columns)
        + " |"
        for _, row in frame.iterrows()
    ]
    return "\n".join([header, separator, *rows])


def generate_report(
    scores: pd.DataFrame,
    report_path: Path = REPORTS_DIR / "industry_report.md",
    chart_path: Path = CHARTS_DIR / "industry_score_bar.png",
) -> tuple[Path, Path]:
    if scores.empty:
        raise ValueError("Cannot generate a report from empty scores")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    data_dates = (
        sorted(scores["data_date"].dropna().astype(str).unique())
        if "data_date" in scores
        else []
    )

    ranking_columns = [
        ("rank", "排名"),
        ("industry", "行业"),
        ("composite_score", "综合分"),
        ("news_heat_score", "新闻热度分"),
        ("market_return_3m_score", "市场代理分"),
        ("policy_heat_score", "政策热度分"),
        ("available_weight", "可用权重"),
    ]
    top_lines = []
    for _, row in scores.dropna(subset=["composite_score"]).head(5).iterrows():
        top_lines.append(
            f"- **{row['industry']}**：综合分 {_display(row['composite_score'])}；"
            f"新闻热度 {_display(row.get('news_heat'), 0)}，"
            f"市场代理近 3 个月收益 {_display(row.get('market_return_3m'), 4)}，"
            f"政策热度 {_display(row.get('policy_heat'), 0)}。"
        )
    if not top_lines:
        top_lines.append("- 当前没有可计算综合分的行业。")

    status_columns = [
        ("industry", "行业"),
        ("available_weight", "可用权重"),
        ("missing_metrics", "缺失指标"),
        ("data_status", "数据状态"),
    ]
    content = "\n".join(
        [
            "# 行业发展势头排名报告",
            "",
            f"- 生成时间：{generated_at}",
            f"- 数据日期：{', '.join(data_dates) if data_dates else '见评分表'}",
            "",
            "## 行业排名",
            "",
            _markdown_table(scores, ranking_columns),
            "",
            "## Top 5 行业及判断依据",
            "",
            *top_lines,
            "",
            "## 数据完整性与降级状态",
            "",
            _markdown_table(scores, status_columns),
            "",
            "状态 `sample` 表示使用离线样例；`missing_config` 表示没有配置合理的市场代理；"
            "`source_error` 表示来源请求或解析失败；`insufficient_data` 表示行情样本不足。",
            "",
            "## 方法说明",
            "",
            "综合分采用新闻热度 40%、市场表现代理 30%、政策热度 30%。"
            "每个维度按当期行业截面百分位映射到 0-100 分。缺失维度不会按 0 分处理，"
            "而是在可用维度上按原权重比例重新归一化。",
            "",
            "## 市场代理指标声明",
            "",
            "ETF/指数仅作为资本市场预期的代理指标，不代表行业真实市场规模、收入或利润。"
            "部分中国新兴行业没有合理代理标的，因此对应市场维度可能缺失。",
            "",
            "## 风险提示",
            "",
            "- 关键词统计会受来源覆盖、标题措辞和重复转载影响。",
            "- 政策与新闻热度反映关注度，不等同于产业基本面改善。",
            "- 样例数据仅用于离线演示，不能作为投资或经营决策依据。",
            "- 排名是相对评分，应结合原始指标、缺失状态和更长时间序列解读。",
            "",
        ]
    )
    report_path.write_text(content, encoding="utf-8")

    chart_data = scores.dropna(subset=["composite_score"]).sort_values(
        "composite_score"
    )
    fig_height = max(4.5, len(chart_data) * 0.45)
    fig, axis = plt.subplots(figsize=(10, fig_height))
    if chart_data.empty:
        axis.text(0.5, 0.5, "无可用评分", ha="center", va="center")
        axis.set_axis_off()
    else:
        axis.barh(
            chart_data["industry"],
            chart_data["composite_score"],
            color="#2F6B9A",
        )
        axis.set_xlim(0, 100)
        axis.set_xlabel("综合分")
        axis.set_title("行业发展势头评分（含资本市场代理指标）")
        axis.grid(axis="x", alpha=0.2)
        for index, value in enumerate(chart_data["composite_score"]):
            axis.text(value + 1, index, f"{value:.1f}", va="center", fontsize=9)
    fig.tight_layout()
    fig.savefig(chart_path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return report_path, chart_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate industry score report.")
    parser.add_argument(
        "--input",
        type=Path,
        default=REPORTS_DIR / "industry_score.csv",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=REPORTS_DIR / "industry_report.md",
    )
    parser.add_argument(
        "--chart",
        type=Path,
        default=CHARTS_DIR / "industry_score_bar.png",
    )
    args = parser.parse_args()
    generate_report(
        pd.read_csv(args.input),
        report_path=args.report,
        chart_path=args.chart,
    )


if __name__ == "__main__":
    main()
