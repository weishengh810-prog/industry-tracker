import pandas as pd

from scripts.build_dataset import build_dataset
from scripts.common import LONG_COLUMNS


def test_build_dataset_enforces_order_and_valid_metrics(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    for name, metric in [
        ("news_daily.csv", "news_heat"),
        ("policy_daily.csv", "policy_heat"),
        ("market_daily.csv", "market_return_3m"),
    ]:
        pd.DataFrame(
            [
                {
                    "industry": "人工智能",
                    "date": "2026-06-11",
                    "metric": metric,
                    "value": 1,
                    "source": "sample",
                    "status": "sample",
                }
            ]
        ).to_csv(raw / name, index=False)
    output = tmp_path / "long.csv"

    frame = build_dataset(raw_dir=raw, output_path=output)

    assert list(frame.columns) == LONG_COLUMNS
    assert set(frame["metric"]) == {
        "news_heat",
        "policy_heat",
        "market_return_3m",
    }
    assert output.exists()
