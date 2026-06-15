from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.common import PROJECT_ROOT
from scripts.score_industries import score_industries


LONG_COLUMNS = ["industry", "date", "metric", "value", "source", "status"]
MOMENTUM_COLUMNS = [
    "industry",
    "metric",
    "growth_rate_4w",
    "z_score_12w",
    "freshness_days",
    "momentum_status",
]
PRIMARY_METRICS = [
    "market_return_3m",
    "market_return_4w",
    "arxiv_paper_count_4w",
    "github_repo_count_4w",
]


def make_daily(
    values: dict[str, dict[str, float | None]],
    dates: dict[str, str] | None = None,
    statuses: dict[tuple[str, str], str] | None = None,
) -> pd.DataFrame:
    rows = []
    for metric, industry_values in values.items():
        for industry, value in industry_values.items():
            rows.append(
                [
                    industry,
                    (dates or {}).get(industry, "2026-06-12"),
                    metric,
                    value,
                    "test",
                    (statuses or {}).get((industry, metric), "ok"),
                ]
            )
    return pd.DataFrame(rows, columns=LONG_COLUMNS)


def make_momentum(
    values: dict[str, dict[str, float | None]],
    statuses: dict[tuple[str, str], str] | None = None,
) -> pd.DataFrame:
    rows = []
    for metric, industry_values in values.items():
        for industry, growth in industry_values.items():
            rows.append(
                [
                    industry,
                    metric,
                    growth,
                    None,
                    0,
                    (statuses or {}).get((industry, metric), "ok"),
                ]
            )
    return pd.DataFrame(rows, columns=MOMENTUM_COLUMNS)


def all_primary_momentum() -> pd.DataFrame:
    return make_momentum(
        {
            "market_return_3m": {"A": 0.3, "B": 0.2, "C": 0.1},
            "market_return_4w": {"A": 0.1, "B": 0.3, "C": 0.2},
            "arxiv_paper_count_4w": {"A": 0.2, "B": 0.1, "C": 0.3},
            "github_repo_count_4w": {"A": 0.3, "B": 0.1, "C": 0.2},
        }
    )


def daily_for_all_primary() -> pd.DataFrame:
    return make_daily(
        {
            metric: {"A": 10.0, "B": 20.0, "C": 30.0}
            for metric in PRIMARY_METRICS
        }
    )


def test_score_uses_growth_rate_instead_of_daily_absolute_value():
    daily = make_daily(
        {"market_return_4w": {"A": 1.0, "B": 2.0, "C": 3.0}}
    )
    momentum = make_momentum(
        {"market_return_4w": {"A": 0.3, "B": 0.2, "C": 0.1}}
    )

    result = score_industries(daily, momentum).set_index("industry")

    assert result.loc["A", "market_return_4w"] == 1.0
    assert result.loc["A", "market_return_4w_score"] == pytest.approx(100.0)
    assert result.loc["C", "market_return_4w_score"] == pytest.approx(
        100.0 / 3.0
    )
    assert result.loc["A", "composite_score"] > result.loc[
        "C", "composite_score"
    ]


def test_trial_prefers_growth_and_falls_back_to_latest_value_per_industry():
    daily = make_daily(
        {
            "market_return_4w": {
                "A": 1000.0,
                "B": 20.0,
                "C": 30.0,
                "D": 40.0,
            }
        }
    )
    momentum = make_momentum(
        {
            "market_return_4w": {
                "A": 0.4,
                "B": None,
                "C": None,
                "D": None,
            }
        },
        statuses={
            ("B", "market_return_4w"): "insufficient_history",
            ("C", "market_return_4w"): "insufficient_history",
            ("D", "market_return_4w"): "insufficient_history",
        },
    )

    result = score_industries(
        daily,
        momentum,
        history_days=27,
    ).set_index("industry")

    assert result.loc["A", "market_return_4w_score_source"] == "growth_rate_4w"
    assert result.loc["B", "market_return_4w_score_source"] == "latest_value"
    assert result.loc["A", "market_return_4w_score"] == 25.0
    assert result.loc["D", "market_return_4w_score"] == 100.0
    assert set(result["scoring_mode"]) == {"试运行评分模式"}
    assert set(result["ranking_status"]) == {"trial"}


def test_trial_fallback_excludes_invalid_daily_statuses_and_values():
    daily = make_daily(
        {
            "github_repo_count_4w": {
                "A": 10.0,
                "B": 20.0,
                "C": 30.0,
                "D": 40.0,
                "E": np.inf,
            }
        },
        statuses={
            ("D", "github_repo_count_4w"): "source_error",
        },
    )

    result = score_industries(
        daily,
        momentum_frame=None,
        history_days=4,
    ).set_index("industry")

    assert result.loc[["A", "B", "C"], "github_repo_count_4w_score"].notna().all()
    assert result.loc[["D", "E"], "github_repo_count_4w_score"].isna().all()
    assert result.loc["D", "github_repo_count_4w_score_source"] == "unavailable"
    assert result.loc["E", "github_repo_count_4w_score_source"] == "unavailable"


def test_trial_percentiles_are_independent_across_different_metric_units():
    daily = make_daily(
        {
            "market_return_3m": {"A": 0.01, "B": 0.02, "C": 0.03},
            "arxiv_paper_count_4w": {
                "A": 1000.0,
                "B": 100.0,
                "C": 10.0,
            },
        }
    )

    result = score_industries(
        daily,
        momentum_frame=None,
        history_days=4,
    ).set_index("industry")

    assert result.loc["A", "market_return_3m_score"] == pytest.approx(
        100.0 / 3.0
    )
    assert result.loc["A", "arxiv_paper_count_4w_score"] == 100.0
    assert result.loc["A", "composite_score"] == pytest.approx(
        (100.0 / 3.0) * 0.35 + 100.0 * 0.65
    )
    assert result.loc["B", "composite_score"] == pytest.approx(
        200.0 / 3.0
    )


def test_formal_stage_does_not_fall_back_to_latest_values():
    daily = make_daily(
        {"market_return_3m": {"A": 10.0, "B": 20.0, "C": 30.0}}
    )

    trial = score_industries(
        daily,
        momentum_frame=None,
        history_days=27,
    )
    formal = score_industries(
        daily,
        momentum_frame=None,
        history_days=28,
    )

    assert trial["market_return_3m_score"].notna().all()
    assert set(trial["market_return_3m_score_source"]) == {"latest_value"}
    assert formal["market_return_3m_score"].isna().all()
    assert set(formal["market_return_3m_score_source"]) == {"unavailable"}
    assert set(formal["scoring_mode"]) == {"历史数据不足，暂不排名"}


def test_metric_with_fewer_than_three_eligible_industries_is_excluded():
    daily = make_daily(
        {"arxiv_paper_count_4w": {"A": 10.0, "B": 20.0, "C": 30.0}}
    )
    momentum = make_momentum(
        {"arxiv_paper_count_4w": {"A": 0.2, "B": 0.1, "C": None}}
    )

    result = score_industries(daily, momentum)

    assert result["arxiv_paper_count_4w_score"].isna().all()
    assert result["composite_score"].isna().all()
    assert all(
        "arxiv_paper_count_4w" in excluded.split(";")
        for excluded in result["excluded_metrics"]
    )


def test_metric_with_exactly_three_eligible_industries_is_scored():
    daily = make_daily(
        {
            "github_repo_count_4w": {
                "A": 10.0,
                "B": 20.0,
                "C": 30.0,
                "D": 40.0,
            }
        }
    )
    momentum = make_momentum(
        {
            "github_repo_count_4w": {
                "A": 0.2,
                "B": 0.1,
                "C": 0.3,
                "D": None,
            }
        }
    )

    result = score_industries(daily, momentum).set_index("industry")

    assert result.loc[["A", "B", "C"], "github_repo_count_4w_score"].notna().all()
    assert pd.isna(result.loc["D", "github_repo_count_4w_score"])
    assert result.loc["C", "github_repo_count_4w_score"] == 100.0


def test_non_ok_status_and_non_finite_growth_are_not_eligible():
    industries = ["A", "B", "C", "D", "E", "F"]
    daily = make_daily(
        {"market_return_3m": dict.fromkeys(industries, 1.0)}
    )
    momentum = make_momentum(
        {
            "market_return_3m": {
                "A": 0.1,
                "B": 0.2,
                "C": 0.3,
                "D": 99.0,
                "E": np.nan,
                "F": np.inf,
            }
        },
        statuses={("D", "market_return_3m"): "insufficient_history"},
    )

    result = score_industries(daily, momentum).set_index("industry")

    assert result.loc[["A", "B", "C"], "market_return_3m_score"].notna().all()
    assert result.loc[["D", "E", "F"], "market_return_3m_score"].isna().all()
    assert "market_return_3m" in result.loc["D", "insufficient_metrics"]


def test_volume_and_nvd_extremes_do_not_affect_primary_score():
    daily = pd.concat(
        [
            daily_for_all_primary(),
            make_daily(
                {
                    "market_volume_change_4w": {
                        "A": 1.0,
                        "B": 2.0,
                        "C": 3.0,
                    },
                    "nvd_cve_count_4w": {"A": 4.0, "B": 5.0, "C": 6.0},
                }
            ),
        ],
        ignore_index=True,
    )
    primary = all_primary_momentum()
    augmented = pd.concat(
        [
            primary,
            make_momentum(
                {
                    "market_volume_change_4w": {
                        "A": -1e12,
                        "B": 0.0,
                        "C": 1e12,
                    },
                    "nvd_cve_count_4w": {
                        "A": 1e12,
                        "B": 0.0,
                        "C": -1e12,
                    },
                }
            ),
        ],
        ignore_index=True,
    )

    base = score_industries(daily, primary).set_index("industry")
    with_auxiliary = score_industries(daily, augmented).set_index("industry")

    pd.testing.assert_series_equal(
        base["composite_score"],
        with_auxiliary["composite_score"],
    )
    assert with_auxiliary.loc["A", "market_volume_change_4w"] == 1.0
    assert (
        with_auxiliary.loc["A", "market_volume_change_4w_growth_rate_4w"]
        == -1e12
    )
    assert (
        with_auxiliary.loc["A", "market_volume_change_4w_momentum_status"]
        == "ok"
    )
    assert pd.isna(with_auxiliary.loc["A", "external_signal_score"])


def test_missing_momentum_keeps_all_industries_but_produces_no_ranking():
    daily = make_daily(
        {"market_return_4w": {"A": 1.0, "B": 2.0, "C": 3.0}},
        dates={
            "A": "2026-06-10",
            "B": "2026-06-12",
            "C": "2026-06-11",
        },
    )

    result = score_industries(daily, momentum_frame=None)

    assert set(result["industry"]) == {"A", "B", "C"}
    assert set(result["data_date"]) == {"2026-06-12"}
    assert result["composite_score"].isna().all()
    assert result["rank"].isna().all()
    assert set(result["ranking_status"]) == {"insufficient_history"}
    assert set(result["scoring_mode"]) == {"历史数据不足，暂不排名"}


def test_dimension_scores_average_available_bottom_level_metrics():
    momentum = all_primary_momentum()

    result = score_industries(
        daily_for_all_primary(),
        momentum,
    ).set_index("industry")

    assert result.loc["A", "capital_momentum_score"] == pytest.approx(
        (
            result.loc["A", "market_return_3m_score"]
            + result.loc["A", "market_return_4w_score"]
        )
        / 2
    )
    assert result.loc["A", "tech_activity_score"] == pytest.approx(
        (
            result.loc["A", "arxiv_paper_count_4w_score"]
            + result.loc["A", "github_repo_count_4w_score"]
        )
        / 2
    )
    assert result.loc["A", "composite_score"] == pytest.approx(
        result.loc["A", "capital_momentum_score"] * 0.35
        + result.loc["A", "tech_activity_score"] * 0.65
    )


def test_available_dimensions_are_renormalized_by_original_weight():
    industries = ["A", "B", "C", "D", "E", "F"]
    daily = make_daily(
        {
            "market_return_3m": dict.fromkeys(industries, 1.0),
            "arxiv_paper_count_4w": dict.fromkeys(industries, 1.0),
        }
    )
    momentum = make_momentum(
        {
            "market_return_3m": {
                "A": None,
                "B": None,
                "C": None,
                "D": 0.1,
                "E": 0.2,
                "F": 0.3,
            },
            "arxiv_paper_count_4w": {
                "A": 0.3,
                "B": 0.2,
                "C": 0.1,
                "D": None,
                "E": None,
                "F": None,
            },
        }
    )

    result = score_industries(daily, momentum).set_index("industry")

    assert result.loc["A", "available_weight"] == 0.65
    assert result.loc["A", "composite_score"] == result.loc[
        "A", "tech_activity_score"
    ]
    assert result.loc["F", "available_weight"] == 0.35
    assert result.loc["F", "composite_score"] == result.loc[
        "F", "capital_momentum_score"
    ]


def test_complete_partial_and_insufficient_modes_are_explicit():
    complete = score_industries(
        daily_for_all_primary(),
        all_primary_momentum(),
    )
    partial = score_industries(
        make_daily(
            {"market_return_3m": {"A": 1.0, "B": 2.0, "C": 3.0}}
        ),
        make_momentum(
            {"market_return_3m": {"A": 0.1, "B": 0.2, "C": 0.3}}
        ),
    )
    insufficient = score_industries(
        make_daily(
            {"market_return_3m": {"A": 1.0, "B": 2.0, "C": 3.0}}
        ),
        None,
    )

    assert set(complete["scoring_mode"]) == {"完整 momentum 模式"}
    assert set(complete["ranking_status"]) == {"ranked"}
    assert set(complete["available_weight"]) == {1.0}
    assert set(partial["scoring_mode"]) == {"部分 momentum 模式"}
    assert set(partial["ranking_status"]) == {"partial"}
    assert set(insufficient["scoring_mode"]) == {"历史数据不足，暂不排名"}


def test_output_path_writes_the_returned_scores(tmp_path):
    output = tmp_path / "nested" / "industry_score.csv"
    daily = make_daily(
        {"market_return_3m": {"A": 1.0, "B": 2.0, "C": 3.0}}
    )
    momentum = make_momentum(
        {"market_return_3m": {"A": 0.1, "B": 0.2, "C": 0.3}}
    )

    result = score_industries(daily, momentum, output_path=output)

    assert output.exists()
    written = pd.read_csv(output)
    pd.testing.assert_frame_equal(
        written,
        result,
        check_dtype=False,
    )


def test_cli_missing_momentum_file_writes_no_ranking_and_exits_zero(tmp_path):
    input_path = tmp_path / "industry_metrics_long.csv"
    output_path = tmp_path / "industry_score.csv"
    missing_momentum = tmp_path / "missing_momentum_features.csv"
    make_daily(
        {"market_return_3m": {"A": 1.0, "B": 2.0, "C": 3.0}}
    ).to_csv(input_path, index=False)

    completed = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "score_industries.py"),
            "--input",
            str(input_path),
            "--momentum",
            str(missing_momentum),
            "--output",
            str(output_path),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    written = pd.read_csv(output_path)
    assert written["composite_score"].isna().all()
    assert set(written["scoring_mode"]) == {"历史数据不足，暂不排名"}
