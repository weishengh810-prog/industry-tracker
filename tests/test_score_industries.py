import pandas as pd

from scripts.score_industries import score_industries


COLUMNS = ["industry", "date", "metric", "value", "source", "status"]


def test_scoring_renormalizes_available_weights():
    frame = pd.DataFrame(
        [
            ["A", "2026-06-11", "news_heat", 10, "x", "ok"],
            ["A", "2026-06-11", "policy_heat", 5, "x", "ok"],
            [
                "A",
                "2026-06-11",
                "market_return_3m",
                None,
                "x",
                "missing_config",
            ],
            ["B", "2026-06-11", "news_heat", 1, "x", "ok"],
            ["B", "2026-06-11", "policy_heat", 1, "x", "ok"],
            ["B", "2026-06-11", "market_return_3m", 0.1, "x", "ok"],
        ],
        columns=COLUMNS,
    )

    result = score_industries(frame)
    row = result.set_index("industry").loc["A"]

    assert row["available_weight"] == 0.7
    assert row["missing_metrics"] == "market_return_3m"
    assert pd.notna(row["composite_score"])


def test_all_missing_industry_has_no_score():
    frame = pd.DataFrame(
        [
            [
                "A",
                "2026-06-11",
                "market_return_3m",
                None,
                "x",
                "missing_config",
            ]
        ],
        columns=COLUMNS,
    )

    result = score_industries(frame)

    assert pd.isna(result.loc[0, "composite_score"])
