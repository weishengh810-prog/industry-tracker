from datetime import date, timedelta
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from scripts.build_momentum_features import (
    MOMENTUM_COLUMNS,
    build_momentum_features,
)
from scripts.common import LONG_COLUMNS, PROJECT_ROOT


LATEST = date(2026, 6, 12)


def make_rows(
    industry,
    metric,
    dates,
    values,
    statuses=None,
):
    date_values = [pd.Timestamp(value).date().isoformat() for value in dates]
    status_values = statuses or ["ok"] * len(date_values)
    return pd.DataFrame(
        {
            "industry": industry,
            "date": date_values,
            "metric": metric,
            "value": values,
            "source": "test",
            "status": status_values,
        },
        columns=LONG_COLUMNS,
    )


def make_daily_rows(
    industry="A",
    metric="market_return_4w",
    days=56,
    latest=LATEST,
    previous_value=2.0,
    current_value=4.0,
):
    dates = pd.date_range(latest - timedelta(days=days - 1), periods=days)
    split = max(days - 28, 0)
    values = [previous_value] * split + [current_value] * (days - split)
    return make_rows(industry, metric, dates, values)


def build(frame, tmp_path, **kwargs):
    kwargs.setdefault("output_path", tmp_path / "momentum.csv")
    return build_momentum_features(
        long_frame=frame,
        archives_dir=tmp_path / "archives",
        today=LATEST,
        **kwargs,
    )


def test_current_rows_override_archived_duplicate_dates(tmp_path):
    archives = tmp_path / "archives"
    archive_path = (
        archives
        / "2026"
        / "06"
        / "snapshot"
        / "processed"
        / "industry_metrics_long.csv"
    )
    archive_path.parent.mkdir(parents=True)
    archived = make_daily_rows()
    archived.loc[archived["date"] == LATEST.isoformat(), ["value", "status"]] = [
        999,
        "source_error",
    ]
    archived.to_csv(archive_path, index=False)
    current = make_rows(
        "A",
        "market_return_4w",
        [LATEST],
        [4.0],
        ["ok"],
    )

    row = build_momentum_features(
        long_frame=current,
        archives_dir=archives,
        output_path=tmp_path / "momentum.csv",
        today=LATEST,
    ).iloc[0]

    assert row["growth_rate_4w"] == pytest.approx(1.0)
    assert row["momentum_status"] == "ok"


def test_growth_zero_denominator_is_insufficient_history(tmp_path):
    frame = make_daily_rows(previous_value=0.0, current_value=2.0)

    row = build(frame, tmp_path).iloc[0]

    assert pd.isna(row["growth_rate_4w"])
    assert row["momentum_status"] == "insufficient_history"


def test_short_z_score_history_is_not_zero(tmp_path):
    frame = make_daily_rows(
        metric="github_repo_count_4w",
        days=26,
        previous_value=1.0,
        current_value=2.0,
    )

    row = build(frame, tmp_path).iloc[0]

    assert pd.isna(row["z_score_12w"])
    assert row["momentum_status"] == "insufficient_history"


def test_growth_can_be_ok_before_twelve_week_z_score_is_available(tmp_path):
    row = build(make_daily_rows(), tmp_path).iloc[0]

    assert row["growth_rate_4w"] == pytest.approx(1.0)
    assert pd.isna(row["z_score_12w"])
    assert row["momentum_status"] == "ok"


def test_history_eligibility_is_independent_per_industry_and_metric(tmp_path):
    enough = make_daily_rows("A", "market_return_4w")
    short_industry = make_daily_rows("B", "market_return_4w", days=20)
    short_metric = make_daily_rows("A", "github_repo_count_4w", days=20)

    result = build(
        pd.concat([enough, short_industry, short_metric], ignore_index=True),
        tmp_path,
    ).set_index(["industry", "metric"])

    assert result.loc[("A", "market_return_4w"), "momentum_status"] == "ok"
    assert (
        result.loc[("B", "market_return_4w"), "momentum_status"]
        == "insufficient_history"
    )
    assert (
        result.loc[("A", "github_repo_count_4w"), "momentum_status"]
        == "insufficient_history"
    )


@pytest.mark.parametrize(
    "latest_status",
    ["source_error", "missing_config", "insufficient_data"],
)
def test_latest_error_status_blocks_old_history(
    tmp_path, latest_status
):
    history = make_daily_rows(latest=LATEST - timedelta(days=1))
    latest = make_rows(
        "A",
        "market_return_4w",
        [LATEST],
        [None],
        [latest_status],
    )

    row = build(pd.concat([history, latest], ignore_index=True), tmp_path).iloc[0]

    assert pd.isna(row["growth_rate_4w"])
    assert pd.isna(row["z_score_12w"])
    assert row["freshness_days"] == 0
    assert row["momentum_status"] == latest_status


def test_growth_uses_exact_inclusive_calendar_boundaries(tmp_path):
    offsets_and_values = [
        (-56, 1000.0),
        (-55, 2.0),
        (-28, 2.0),
        (-27, 4.0),
        (0, 4.0),
    ]
    frame = make_rows(
        "A",
        "market_return_4w",
        [LATEST + timedelta(days=offset) for offset, _ in offsets_and_values],
        [value for _, value in offsets_and_values],
    )

    row = build(frame, tmp_path).iloc[0]

    assert row["growth_rate_4w"] == pytest.approx(1.0)
    assert row["momentum_status"] == "ok"


def test_non_finite_values_are_excluded_from_usable_history(tmp_path):
    frame = make_daily_rows()
    frame.loc[1, "value"] = np.inf
    frame.loc[30, "value"] = -np.inf
    frame.loc[40, "value"] = np.nan

    row = build(frame, tmp_path).iloc[0]

    assert row["growth_rate_4w"] == pytest.approx(1.0)
    assert pd.isna(row["z_score_12w"])
    assert row["momentum_status"] == "ok"


@pytest.mark.parametrize("latest_status", ["ok", "sample", "no_match"])
@pytest.mark.parametrize("latest_value", [np.nan, np.inf, -np.inf])
def test_latest_non_finite_value_blocks_old_finite_history(
    tmp_path, latest_status, latest_value
):
    history = make_daily_rows(
        days=84,
        latest=LATEST - timedelta(days=1),
    )
    latest = make_rows(
        "A",
        "market_return_4w",
        [LATEST],
        [latest_value],
        [latest_status],
    )

    row = build(pd.concat([history, latest], ignore_index=True), tmp_path).iloc[0]

    assert pd.isna(row["growth_rate_4w"])
    assert pd.isna(row["z_score_12w"])
    assert row["freshness_days"] == 0
    assert row["momentum_status"] == "insufficient_history"


def test_z_score_uses_84_day_window_and_sample_standard_deviation(tmp_path):
    dates = pd.date_range(LATEST - timedelta(days=83), periods=84)
    values = list(range(1, 85))
    row = build(
        make_rows("A", "github_repo_count_4w", dates, values),
        tmp_path,
    ).iloc[0]
    expected = (84 - np.mean(values)) / np.std(values, ddof=1)

    assert row["z_score_12w"] == pytest.approx(expected)
    assert row["momentum_status"] == "ok"


def test_output_columns_freshness_and_written_csv_are_exact(tmp_path):
    output = tmp_path / "momentum.csv"

    result = build(
        make_daily_rows(latest=LATEST - timedelta(days=3)),
        tmp_path,
        output_path=output,
    )

    assert list(result.columns) == MOMENTUM_COLUMNS
    assert MOMENTUM_COLUMNS == [
        "industry",
        "metric",
        "growth_rate_4w",
        "z_score_12w",
        "freshness_days",
        "momentum_status",
    ]
    assert result.loc[0, "freshness_days"] == 3
    assert list(pd.read_csv(output).columns) == MOMENTUM_COLUMNS


def test_momentum_cli_reads_input_archives_and_writes_output(tmp_path):
    input_path = tmp_path / "current.csv"
    output_path = tmp_path / "momentum.csv"
    archives_dir = tmp_path / "archives"
    make_daily_rows().to_csv(input_path, index=False)

    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "build_momentum_features.py"),
            "--input",
            str(input_path),
            "--archives-dir",
            str(archives_dir),
            "--output",
            str(output_path),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert list(pd.read_csv(output_path).columns) == MOMENTUM_COLUMNS
