from datetime import date

import pandas as pd
import pytest

import scripts.fetch_market as market
from scripts.common import LONG_COLUMNS, load_industries


INDUSTRY = {
    "name": "Test Industry",
    "market_proxy": {"ticker": "TEST", "name": "Test ETF"},
}
METRICS = {
    "market_return_3m",
    "market_return_4w",
    "market_volume_change_4w",
}


def _market_frame(
    *,
    include_volume: bool = True,
    volume: float = 2_000.0,
) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", "2026-05-31", freq="D")
    frame = pd.DataFrame(
        {"Adj Close": pd.Series(range(100, 251), index=index, dtype=float)}
    )
    if include_volume:
        frame["Volume"] = volume
    return frame


def _rows_by_metric(rows):
    return {row["metric"]: row for row in rows}


def _assert_prices_ok_volume_insufficient(rows):
    by_metric = _rows_by_metric(rows)
    assert by_metric["market_return_3m"]["status"] == "ok"
    assert by_metric["market_return_4w"]["status"] == "ok"
    assert by_metric["market_volume_change_4w"]["status"] == "insufficient_data"
    assert by_metric["market_volume_change_4w"]["value"] is None


def test_market_rows_marks_null_proxy_as_three_missing_config_rows():
    rows = market.market_rows({"name": "No Proxy", "market_proxy": None})

    assert len(rows) == 3
    assert {row["metric"] for row in rows} == METRICS
    assert {row["status"] for row in rows} == {"missing_config"}
    assert all(row["value"] is None for row in rows)
    assert all(list(row) == LONG_COLUMNS for row in rows)


def test_market_rows_calculates_price_and_volume_metrics_from_calendar_windows():
    frame = _market_frame()
    latest = frame.index[-1]
    frame.loc[frame.index > latest - pd.Timedelta(days=28), "Volume"] = 3_000

    rows = _rows_by_metric(
        market.market_rows(INDUSTRY, downloader=lambda *a, **k: frame)
    )

    expected_3m = frame.loc[latest - pd.Timedelta(days=89), "Adj Close"]
    expected_4w = frame.loc[latest - pd.Timedelta(days=27), "Adj Close"]
    assert rows["market_return_3m"]["value"] == pytest.approx(
        frame.loc[latest, "Adj Close"] / expected_3m - 1
    )
    assert rows["market_return_4w"]["value"] == pytest.approx(
        frame.loc[latest, "Adj Close"] / expected_4w - 1
    )
    assert rows["market_volume_change_4w"]["value"] == pytest.approx(0.5)
    assert {row["status"] for row in rows.values()} == {"ok"}
    assert {row["date"] for row in rows.values()} == {"2026-05-31"}


@pytest.mark.parametrize(
    ("metric", "days", "boundary_price", "inside_price"),
    [
        ("market_return_4w", 28, 100.0, 120.0),
        ("market_return_3m", 90, 80.0, 120.0),
    ],
)
def test_price_windows_exclude_days_ago_boundary_and_include_next_date(
    metric,
    days,
    boundary_price,
    inside_price,
):
    latest = pd.Timestamp("2026-05-31")
    frame = pd.DataFrame(
        {
            "Adj Close": [boundary_price, inside_price, 180.0],
            "Volume": [2_000.0, 2_000.0, 2_000.0],
        },
        index=[
            latest - pd.Timedelta(days=days),
            latest - pd.Timedelta(days=days - 1),
            latest,
        ],
    )

    rows = _rows_by_metric(
        market.market_rows(INDUSTRY, downloader=lambda *a, **k: frame)
    )

    assert rows[metric]["value"] == pytest.approx(180.0 / inside_price - 1)


def test_market_rows_uses_available_price_observations_after_window_cutoffs():
    frame = pd.DataFrame(
        {
            "Close": [100.0, 120.0, 150.0],
            "Volume": [2_000.0, 2_000.0, 2_000.0],
        },
        index=pd.to_datetime(["2026-03-03", "2026-05-04", "2026-05-31"]),
    )

    rows = _rows_by_metric(
        market.market_rows(INDUSTRY, downloader=lambda *a, **k: frame)
    )

    assert rows["market_return_3m"]["value"] == pytest.approx(0.5)
    assert rows["market_return_4w"]["value"] == pytest.approx(0.25)


def test_market_rows_keeps_price_metrics_ok_when_volume_is_missing():
    rows = market.market_rows(
        INDUSTRY,
        downloader=lambda *a, **k: _market_frame(include_volume=False),
    )

    _assert_prices_ok_volume_insufficient(rows)


def test_market_rows_marks_all_nan_volume_as_independently_insufficient():
    frame = _market_frame()
    frame["Volume"] = float("nan")

    rows = market.market_rows(INDUSTRY, downloader=lambda *a, **k: frame)

    _assert_prices_ok_volume_insufficient(rows)


@pytest.mark.parametrize(
    "invalid_window",
    ["current", "previous"],
)
def test_market_rows_rejects_infinite_volume_in_either_window(
    invalid_window,
):
    frame = _market_frame()
    latest = frame.index[-1]
    if invalid_window == "current":
        frame.loc[
            frame.index > latest - pd.Timedelta(days=28),
            "Volume",
        ] = 0.0
        frame.loc[latest - pd.Timedelta(days=1), "Volume"] = float("inf")
    else:
        frame.loc[
            (frame.index > latest - pd.Timedelta(days=56))
            & (frame.index <= latest - pd.Timedelta(days=28)),
            "Volume",
        ] = 0.0
        frame.loc[latest - pd.Timedelta(days=29), "Volume"] = float("inf")

    rows = market.market_rows(INDUSTRY, downloader=lambda *a, **k: frame)

    _assert_prices_ok_volume_insufficient(rows)


def test_market_rows_rejects_non_finite_volume_ratio(monkeypatch):
    frame = _market_frame()
    latest = frame.index[-1]
    frame.loc[
        frame.index > latest - pd.Timedelta(days=56),
        "Volume",
    ] = 0.0
    frame.loc[latest - pd.Timedelta(days=28), "Volume"] = 1e-308
    frame.loc[latest, "Volume"] = 1e308
    monkeypatch.setattr(market, "MIN_AVERAGE_VOLUME", 0)

    rows = market.market_rows(INDUSTRY, downloader=lambda *a, **k: frame)

    _assert_prices_ok_volume_insufficient(rows)


def test_market_volume_anchors_to_last_finite_observation_when_prices_continue():
    frame = _market_frame()
    price_latest = frame.index[-1]
    volume_latest = price_latest - pd.Timedelta(days=5)
    frame.loc[
        (frame.index > volume_latest - pd.Timedelta(days=56))
        & (frame.index <= volume_latest - pd.Timedelta(days=28)),
        "Volume",
    ] = 2_000
    frame.loc[
        frame.index > volume_latest - pd.Timedelta(days=28),
        "Volume",
    ] = 4_000
    frame.loc[frame.index > volume_latest, "Volume"] = float("nan")

    rows = _rows_by_metric(
        market.market_rows(INDUSTRY, downloader=lambda *a, **k: frame)
    )

    assert rows["market_return_3m"]["date"] == price_latest.date().isoformat()
    assert rows["market_return_4w"]["date"] == price_latest.date().isoformat()
    assert rows["market_volume_change_4w"]["status"] == "ok"
    assert rows["market_volume_change_4w"]["date"] == volume_latest.date().isoformat()
    assert rows["market_volume_change_4w"]["value"] == pytest.approx(1.0)


def test_market_volume_ignores_trailing_infinity_when_choosing_anchor():
    frame = _market_frame()
    price_latest = frame.index[-1]
    volume_latest = price_latest - pd.Timedelta(days=5)
    frame.loc[
        (frame.index > volume_latest - pd.Timedelta(days=56))
        & (frame.index <= volume_latest - pd.Timedelta(days=28)),
        "Volume",
    ] = 2_000
    frame.loc[
        frame.index > volume_latest - pd.Timedelta(days=28),
        "Volume",
    ] = 4_000
    frame.loc[frame.index > volume_latest, "Volume"] = float("inf")

    rows = _rows_by_metric(
        market.market_rows(INDUSTRY, downloader=lambda *a, **k: frame)
    )

    assert rows["market_return_3m"]["date"] == price_latest.date().isoformat()
    assert rows["market_return_4w"]["date"] == price_latest.date().isoformat()
    assert rows["market_volume_change_4w"]["status"] == "ok"
    assert rows["market_volume_change_4w"]["date"] == volume_latest.date().isoformat()
    assert rows["market_volume_change_4w"]["value"] == pytest.approx(1.0)


def test_market_volume_windows_use_exact_non_overlapping_boundary_dates():
    latest = pd.Timestamp("2026-05-31")
    excluded_volume = 9_000.0
    previous_start_volume = 1_200.0
    previous_end_volume = 1_800.0
    current_start_volume = 3_000.0
    current_end_volume = 5_000.0
    frame = pd.DataFrame(
        {
            "Adj Close": [100.0, 110.0, 120.0, 130.0, 150.0],
            "Volume": [
                excluded_volume,
                previous_start_volume,
                previous_end_volume,
                current_start_volume,
                current_end_volume,
            ],
        },
        index=[
            latest - pd.Timedelta(days=56),
            latest - pd.Timedelta(days=55),
            latest - pd.Timedelta(days=28),
            latest - pd.Timedelta(days=27),
            latest,
        ],
    )

    rows = _rows_by_metric(
        market.market_rows(INDUSTRY, downloader=lambda *a, **k: frame)
    )

    previous_mean = (previous_start_volume + previous_end_volume) / 2
    current_mean = (current_start_volume + current_end_volume) / 2
    assert rows["market_volume_change_4w"]["status"] == "ok"
    assert rows["market_volume_change_4w"]["value"] == pytest.approx(
        current_mean / previous_mean - 1
    )


@pytest.mark.parametrize(
    ("current_volume", "previous_volume"),
    [
        (0, 2_000),
        (2_000, 0),
        (999, 2_000),
        (2_000, 999),
    ],
    ids=[
        "current-no-positive",
        "previous-no-positive",
        "current-below-minimum",
        "previous-below-minimum",
    ],
)
def test_market_rows_marks_each_invalid_volume_window_independently_insufficient(
    current_volume,
    previous_volume,
):
    frame = _market_frame()
    latest = frame.index[-1]
    frame.loc[
        (frame.index > latest - pd.Timedelta(days=56))
        & (frame.index <= latest - pd.Timedelta(days=28)),
        "Volume",
    ] = previous_volume
    frame.loc[
        frame.index > latest - pd.Timedelta(days=28),
        "Volume",
    ] = current_volume

    rows = market.market_rows(
        INDUSTRY,
        downloader=lambda *a, **k: frame,
    )

    _assert_prices_ok_volume_insufficient(rows)


def test_market_rows_marks_each_price_metric_independently_insufficient():
    frame = pd.DataFrame(
        {"Adj Close": [100.0], "Volume": [2_000.0]},
        index=pd.to_datetime(["2026-05-31"]),
    )

    rows = _rows_by_metric(
        market.market_rows(INDUSTRY, downloader=lambda *a, **k: frame)
    )

    assert rows["market_return_3m"]["status"] == "insufficient_data"
    assert rows["market_return_4w"]["status"] == "insufficient_data"


def test_market_rows_marks_only_four_week_price_insufficient():
    frame = pd.DataFrame(
        {
            "Adj Close": [100.0, 150.0],
            "Volume": [2_000.0, 2_000.0],
        },
        index=pd.to_datetime(["2026-03-03", "2026-05-31"]),
    )

    rows = _rows_by_metric(
        market.market_rows(INDUSTRY, downloader=lambda *a, **k: frame)
    )

    assert rows["market_return_3m"]["status"] == "ok"
    assert rows["market_return_3m"]["value"] == pytest.approx(0.5)
    assert rows["market_return_4w"]["status"] == "insufficient_data"
    assert rows["market_return_4w"]["value"] is None


@pytest.mark.parametrize("invalid_start", [0.0, float("inf")])
def test_market_rows_rejects_invalid_four_week_start_price_independently(
    invalid_start,
):
    frame = _market_frame()
    latest = frame.index[-1]
    frame.loc[latest - pd.Timedelta(days=27), "Adj Close"] = invalid_start

    rows = _rows_by_metric(
        market.market_rows(INDUSTRY, downloader=lambda *a, **k: frame)
    )

    assert rows["market_return_3m"]["status"] == "ok"
    assert rows["market_return_4w"]["status"] == "insufficient_data"
    assert rows["market_return_4w"]["value"] is None
    assert rows["market_volume_change_4w"]["status"] == "ok"


def test_market_rows_rejects_infinite_end_price_without_affecting_volume():
    frame = _market_frame()
    frame.loc[frame.index[-1], "Adj Close"] = float("inf")

    rows = _rows_by_metric(
        market.market_rows(INDUSTRY, downloader=lambda *a, **k: frame)
    )

    assert rows["market_return_3m"]["status"] == "insufficient_data"
    assert rows["market_return_4w"]["status"] == "insufficient_data"
    assert rows["market_volume_change_4w"]["status"] == "ok"


def test_market_rows_rejects_non_finite_calculated_return():
    frame = _market_frame()
    latest = frame.index[-1]
    frame.loc[latest - pd.Timedelta(days=27), "Adj Close"] = 1e-308
    frame.loc[latest, "Adj Close"] = 1e308

    rows = _rows_by_metric(
        market.market_rows(INDUSTRY, downloader=lambda *a, **k: frame)
    )

    assert rows["market_return_4w"]["status"] == "insufficient_data"
    assert rows["market_return_4w"]["value"] is None
    assert rows["market_volume_change_4w"]["status"] == "ok"


def test_market_rows_drops_nan_start_price_and_uses_next_observation():
    frame = _market_frame()
    latest = frame.index[-1]
    frame.loc[latest - pd.Timedelta(days=27), "Adj Close"] = float("nan")
    expected_start = latest - pd.Timedelta(days=26)

    rows = _rows_by_metric(
        market.market_rows(INDUSTRY, downloader=lambda *a, **k: frame)
    )

    assert rows["market_return_4w"]["status"] == "ok"
    assert rows["market_return_4w"]["value"] == pytest.approx(
        frame.loc[latest, "Adj Close"]
        / frame.loc[expected_start, "Adj Close"]
        - 1
    )
    assert rows["market_volume_change_4w"]["status"] == "ok"


def test_market_rows_drops_nan_end_price_and_anchors_on_latest_usable_price():
    frame = _market_frame()
    original_latest = frame.index[-1]
    frame.loc[original_latest, "Adj Close"] = float("nan")
    usable_latest = original_latest - pd.Timedelta(days=1)
    expected_start = usable_latest - pd.Timedelta(days=27)

    rows = _rows_by_metric(
        market.market_rows(INDUSTRY, downloader=lambda *a, **k: frame)
    )

    assert rows["market_return_4w"]["status"] == "ok"
    assert rows["market_return_4w"]["date"] == usable_latest.date().isoformat()
    assert rows["market_return_4w"]["value"] == pytest.approx(
        frame.loc[usable_latest, "Adj Close"]
        / frame.loc[expected_start, "Adj Close"]
        - 1
    )
    assert rows["market_volume_change_4w"]["status"] == "ok"


def test_market_rows_return_exact_long_column_keys():
    rows = market.market_rows(
        INDUSTRY,
        downloader=lambda *a, **k: _market_frame(),
    )

    assert all(list(row) == LONG_COLUMNS for row in rows)


def test_market_rows_returns_three_source_errors_on_download_failure():
    def fail(*args, **kwargs):
        raise RuntimeError("download failed")

    rows = market.market_rows(INDUSTRY, downloader=fail)

    assert len(rows) == 3
    assert {row["metric"] for row in rows} == METRICS
    assert {row["status"] for row in rows} == {"source_error"}
    assert all(list(row) == LONG_COLUMNS for row in rows)


def test_market_rows_returns_three_source_errors_on_empty_download():
    rows = market.market_rows(
        INDUSTRY,
        downloader=lambda *a, **k: pd.DataFrame(),
    )

    assert len(rows) == 3
    assert {row["metric"] for row in rows} == METRICS
    assert {row["status"] for row in rows} == {"source_error"}
    assert all(row["value"] is None for row in rows)


def test_market_rows_downloads_once_with_explicit_120_day_range():
    calls = []

    def download(*args, **kwargs):
        calls.append((args, kwargs))
        return _market_frame()

    market.market_rows(INDUSTRY, downloader=download)

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ("TEST",)
    assert kwargs["interval"] == "1d"
    assert kwargs["progress"] is False
    assert kwargs["auto_adjust"] is False
    assert "period" not in kwargs
    assert isinstance(kwargs["start"], date)
    assert isinstance(kwargs["end"], date)
    assert (kwargs["end"] - kwargs["start"]).days >= 121


def test_market_rows_supports_multiindex_adjusted_close_and_volume():
    frame = _market_frame()
    frame.columns = pd.MultiIndex.from_tuples(
        [("Adj Close", "TEST"), ("Volume", "TEST")]
    )

    rows = _rows_by_metric(
        market.market_rows(INDUSTRY, downloader=lambda *a, **k: frame)
    )

    assert rows["market_return_3m"]["status"] == "ok"
    assert rows["market_return_4w"]["status"] == "ok"
    assert rows["market_volume_change_4w"]["status"] == "ok"


def test_market_rows_falls_back_to_flat_close_when_adjusted_close_is_all_nan():
    frame = _market_frame()
    frame["Close"] = frame["Adj Close"]
    frame["Adj Close"] = float("nan")

    rows = _rows_by_metric(
        market.market_rows(INDUSTRY, downloader=lambda *a, **k: frame)
    )

    assert rows["market_return_3m"]["status"] == "ok"
    assert rows["market_return_4w"]["status"] == "ok"


def test_market_rows_falls_back_to_multiindex_close_when_adjusted_is_all_nan():
    frame = _market_frame()
    frame["Close"] = frame["Adj Close"]
    frame["Adj Close"] = float("nan")
    frame.columns = pd.MultiIndex.from_tuples(
        [
            ("Adj Close", "TEST"),
            ("Volume", "TEST"),
            ("Close", "TEST"),
        ]
    )

    rows = _rows_by_metric(
        market.market_rows(INDUSTRY, downloader=lambda *a, **k: frame)
    )

    assert rows["market_return_3m"]["status"] == "ok"
    assert rows["market_return_4w"]["status"] == "ok"


def test_market_rows_prefers_adjusted_close_over_close():
    frame = _market_frame()
    frame["Close"] = frame["Adj Close"] * 10

    rows = _rows_by_metric(
        market.market_rows(INDUSTRY, downloader=lambda *a, **k: frame)
    )
    latest = frame.index[-1]
    start = latest - pd.Timedelta(days=89)

    assert rows["market_return_3m"]["value"] == pytest.approx(
        frame.loc[latest, "Adj Close"] / frame.loc[start, "Adj Close"] - 1
    )


def test_market_row_compatibility_wrapper_returns_three_month_row():
    row = market.market_row(
        INDUSTRY, downloader=lambda *a, **k: _market_frame()
    )

    assert row["metric"] == "market_return_3m"
    assert row["status"] == "ok"


def test_collect_market_offline_has_exactly_three_metrics_for_all_industries(
    tmp_path,
):
    output = tmp_path / "market.csv"

    frame = market.collect_market(offline=True, output_path=output)

    assert output.exists()
    assert list(frame.columns) == LONG_COLUMNS
    assert len(frame) == 36
    assert set(frame["metric"]) == METRICS
    assert frame.groupby(["industry", "metric"]).size().eq(1).all()
    assert set(frame["status"]) == {"sample"}
    expected_sources = {
        item["name"]: (
            f"{item['market_proxy']['name']} "
            f"({item['market_proxy']['ticker']})"
        )
        for item in load_industries()
    }
    assert frame.groupby("industry")["source"].nunique().eq(1).all()
    assert {
        industry: group["source"].iloc[0]
        for industry, group in frame.groupby("industry")
    } == expected_sources
    assert not frame["source"].str.contains(r"\.(?:SZ|SS)\)").any()


def test_collect_market_configures_project_yfinance_cache_for_default_downloader(
    tmp_path, monkeypatch
):
    configured = []
    monkeypatch.setattr(
        market.yf,
        "set_tz_cache_location",
        configured.append,
    )
    monkeypatch.setattr(
        market.yf,
        "download",
        lambda *args, **kwargs: _market_frame(),
    )

    market.collect_market(
        output_path=tmp_path / "market.csv",
        fallback_samples=False,
    )

    assert configured == [str(market.CACHE_DIR / "yfinance")]


def test_collect_market_flattens_rows_without_fallback_when_any_metric_is_ok(
    tmp_path,
):
    output = tmp_path / "market.csv"

    frame = market.collect_market(
        output_path=output,
        industries=[INDUSTRY],
        downloader=lambda *a, **k: _market_frame(include_volume=False),
    )

    assert len(frame) == 3
    assert set(frame["metric"]) == METRICS
    assert frame["status"].eq("ok").sum() == 2
    assert frame["status"].eq("insufficient_data").sum() == 1


def test_collect_market_falls_back_only_when_no_configured_metric_is_ok(tmp_path):
    output = tmp_path / "market.csv"
    sample = tmp_path / "sample.csv"
    pd.DataFrame(
        [
            ["Sample", "2026-05-31", metric, 0.1, "Sample ETF (TEST)", "sample"]
            for metric in sorted(METRICS)
        ],
        columns=LONG_COLUMNS,
    ).to_csv(sample, index=False)

    frame = market.collect_market(
        output_path=output,
        sample_path=sample,
        industries=[INDUSTRY],
        downloader=lambda *a, **k: pd.DataFrame(),
    )

    assert len(frame) == 3
    assert set(frame["status"]) == {"sample"}
