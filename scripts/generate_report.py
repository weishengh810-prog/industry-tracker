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
    if not rows:
        rows = [
            "| "
            + " | ".join("-" for _ in columns)
            + " |"
        ]
    return "\n".join([header, separator, *rows])


def _unique_text(scores: pd.DataFrame, column: str) -> str:
    if column not in scores:
        return ""
    values = [
        value
        for value in scores[column].dropna().astype(str).unique()
        if value
    ]
    return "；".join(values)


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
    data_dates = sorted(scores.get("data_date", pd.Series(dtype=object)).dropna().astype(str).unique())
    scoring_mode = _unique_text(scores, "scoring_mode") or "历史数据不足，暂不排名"
    excluded_metrics = _unique_text(scores, "excluded_metrics") or "无"
    ranked = scores.dropna(subset=["composite_score"]).copy()

    ranking_columns = [
        ("rank", "排名"),
        ("industry", "行业"),
        ("composite_score", "综合分"),
        ("capital_momentum_score", "资本动量"),
        ("tech_activity_score", "技术活跃度"),
        ("available_weight", "可用权重"),
        ("ranking_status", "排名状态"),
    ]
    volume_columns = [
        ("industry", "行业"),
        ("market_volume_change_4w", "当期值"),
        ("market_volume_change_4w_growth_rate_4w", "4周增长率"),
        ("market_volume_change_4w_momentum_status", "历史状态"),
    ]
    nvd_columns = [
        ("industry", "行业"),
        ("nvd_cve_count_4w", "近4周新增 CVE"),
        ("nvd_cve_count_4w_growth_rate_4w", "4周增长率"),
        ("nvd_cve_count_4w_momentum_status", "历史状态"),
    ]

    ranking_section = (
        _markdown_table(ranked, ranking_columns)
        if not ranked.empty
        else "当前暂无可排名行业。离线样例或新部署通常需要积累约 56 天历史后，"
        "才能计算第一批 `growth_rate_4w`。"
    )
    top_lines = [
        f"- **{row['industry']}**：综合分 {_display(row['composite_score'])}，"
        f"资本动量 {_display(row.get('capital_momentum_score'))}，"
        f"技术活跃度 {_display(row.get('tech_activity_score'))}。"
        for _, row in ranked.head(5).iterrows()
    ]
    if not top_lines:
        top_lines = ["- 当前暂无可排名行业。"]

    volume = scores[
        scores.get(
            "market_volume_change_4w",
            pd.Series(index=scores.index, dtype=float),
        ).notna()
        | scores.get(
            "market_volume_change_4w_growth_rate_4w",
            pd.Series(index=scores.index, dtype=float),
        ).notna()
    ]
    nvd = scores[
        scores.get(
            "nvd_cve_count_4w",
            pd.Series(index=scores.index, dtype=float),
        ).notna()
        | scores.get(
            "nvd_cve_count_4w_growth_rate_4w",
            pd.Series(index=scores.index, dtype=float),
        ).notna()
    ]

    content = "\n".join(
        [
            "# 行业发展动量报告",
            "",
            f"- 生成时间：{generated_at}",
            f"- 数据日期：{', '.join(data_dates) if data_dates else '见评分表'}",
            f"- 当前评分模式：{scoring_mode}",
            f"- 未进入主评分的指标：{excluded_metrics}",
            "",
            "## 行业排名",
            "",
            ranking_section,
            "",
            "## Top 5",
            "",
            *top_lines,
            "",
            "## 辅助观察：成交量",
            "",
            "`market_volume_change_4w` 仅作辅助观察，不进入主评分。",
            "",
            _markdown_table(volume, volume_columns),
            "",
            "物流供应链使用 SHPP 作为全球市场代理。该 ETF 可能流动性偏低，"
            "成交量变化需要结合 `insufficient_data` 状态谨慎解释。",
            "",
            "## 网络安全专项信号",
            "",
            "`nvd_cve_count_4w` 第一版只覆盖网络安全，不能单独进行行业横向评分，"
            "因此暂不进入 `external_signal` 主评分。",
            "",
            _markdown_table(nvd, nvd_columns),
            "",
            "## 方法说明",
            "",
            "- 主评分只使用 `growth_rate_4w`，不使用新闻、政策或当期绝对规模回退。",
            "- 任一底层指标至少 3 个行业的 `momentum_status=ok` 才能进入截面百分位。",
            "- `capital_momentum` 权重 35%，由 `market_return_3m` 和 `market_return_4w` 构成。",
            "- `tech_activity` 权重 65%，由 `arxiv_paper_count_4w` 和 `github_repo_count_4w` 构成。",
            "- 某个指标历史不足只排除该指标；可用维度按原始权重重新归一化。",
            "- `external_signal` 字段已预留，待多个行业拥有可比专项指标后再启用。",
            "",
            "本系统比较的是行业相对自身历史的加速程度，不是行业绝对规模。",
            "小行业若快速升温可能排名靠前；大行业若增速放缓排名会下降。",
            "ETF 为全球市场代理，不代表中国行业真实基本面。",
            f"当前评分模式：{scoring_mode}",
            "",
            "数据来源：公开 ETF 行情、arXiv 学术论文、GitHub 开源仓库、NVD 漏洞数据库。",
            "",
            "## 数据状态",
            "",
            "`sample` 表示离线样例；`missing_config` 表示该来源不覆盖该行业；"
            "`source_error` 表示请求或解析失败；`insufficient_data` 表示当期样本不足；"
            "`insufficient_history` 只用于历史特征，表示尚不能计算增长率。",
            "",
        ]
    )
    report_path.write_text(content, encoding="utf-8")

    chart_data = ranked.sort_values("composite_score")
    fig_height = max(4.5, len(chart_data) * 0.45)
    fig, axis = plt.subplots(figsize=(10, fig_height))
    if chart_data.empty:
        axis.text(0.5, 0.5, "历史数据不足，暂不排名", ha="center", va="center")
        axis.set_axis_off()
    else:
        axis.barh(
            chart_data["industry"],
            chart_data["composite_score"],
            color="#2F6B9A",
        )
        axis.set_xlim(0, 100)
        axis.set_xlabel("综合动量分")
        axis.set_title("行业相对历史加速度排名")
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
