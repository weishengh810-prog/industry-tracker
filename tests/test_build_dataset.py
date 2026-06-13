import pandas as pd
import pytest

from scripts.build_dataset import RAW_FILES, build_dataset
from scripts.common import LONG_COLUMNS


RAW_METRICS = {
    "news_daily.csv": "news_heat",
    "policy_daily.csv": "policy_heat",
    "market_daily.csv": "market_return_3m",
    "arxiv_daily.csv": "arxiv_paper_count_4w",
    "github_daily.csv": "github_repo_count_4w",
    "nvd_daily.csv": "nvd_cve_count_4w",
}


def write_raw_files(raw, missing=None):
    raw.mkdir()
    for name, metric in RAW_METRICS.items():
        if name == missing:
            continue
        pd.DataFrame(
            [
                {
                    "industry": "A",
                    "date": "2026-06-11",
                    "metric": metric,
                    "value": 1,
                    "source": "sample",
                    "status": "sample",
                }
            ]
        ).to_csv(raw / name, index=False)


def test_build_dataset_requires_exactly_six_daily_sources(tmp_path):
    raw = tmp_path / "raw"
    write_raw_files(raw)
    output = tmp_path / "long.csv"

    frame = build_dataset(raw_dir=raw, output_path=output)

    assert RAW_FILES == tuple(RAW_METRICS)
    assert list(frame.columns) == LONG_COLUMNS
    assert set(frame["metric"]) == set(RAW_METRICS.values())
    assert output.exists()


@pytest.mark.parametrize("missing", RAW_METRICS)
def test_build_dataset_requires_each_daily_source(tmp_path, missing):
    raw = tmp_path / "raw"
    write_raw_files(raw, missing=missing)

    with pytest.raises(FileNotFoundError, match=missing):
        build_dataset(raw_dir=raw, output_path=tmp_path / "long.csv")


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("metric", "unknown_metric", "unknown metrics"),
        ("status", "unknown_status", "unknown statuses"),
    ],
)
def test_build_dataset_keeps_strict_metric_and_status_validation(
    tmp_path, column, value, message
):
    raw = tmp_path / "raw"
    write_raw_files(raw)
    path = raw / "news_daily.csv"
    frame = pd.read_csv(path)
    frame.loc[0, column] = value
    frame.to_csv(path, index=False)

    with pytest.raises(ValueError, match=message):
        build_dataset(raw_dir=raw, output_path=tmp_path / "long.csv")


def test_build_dataset_keeps_strict_long_columns_validation(tmp_path):
    raw = tmp_path / "raw"
    write_raw_files(raw)
    path = raw / "news_daily.csv"
    pd.read_csv(path).drop(columns="source").to_csv(path, index=False)

    with pytest.raises(ValueError, match="missing columns"):
        build_dataset(raw_dir=raw, output_path=tmp_path / "long.csv")
