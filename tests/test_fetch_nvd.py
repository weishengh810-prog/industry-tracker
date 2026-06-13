from datetime import date
import math

import pandas as pd
import pytest

import scripts.fetch_nvd as fetch_nvd
from scripts.common import LONG_COLUMNS, load_industries
from scripts.fetch_nvd import collect_nvd
from scripts.source_cache import daily_cache_path, read_json_cache, write_json_cache


TODAY = date(2026, 6, 12)
CYBERSECURITY = "网络安全"


class FakeResponse:
    def __init__(
        self,
        payload=None,
        error: Exception | None = None,
        json_error: Exception | None = None,
    ):
        self.payload = payload
        self.error = error
        self.json_error = json_error

    def raise_for_status(self):
        if self.error is not None:
            raise self.error

    def json(self):
        if self.json_error is not None:
            raise self.json_error
        return self.payload


def industry(name):
    return next(item for item in load_industries() if item["name"] == name)


def collect_one(tmp_path, response, **kwargs):
    return collect_nvd(
        industries=[industry(CYBERSECURITY)],
        requester=lambda *args, **request_kwargs: response,
        sleeper=lambda seconds: None,
        cache_dir=tmp_path / "cache",
        output_path=tmp_path / "nvd.csv",
        today=TODAY,
        **kwargs,
    )


def test_offline_nvd_reads_strict_sample_without_request_or_sleep(tmp_path):
    output = tmp_path / "nvd.csv"

    frame = collect_nvd(
        offline=True,
        output_path=output,
        requester=lambda *args, **kwargs: pytest.fail("unexpected request"),
        sleeper=lambda seconds: pytest.fail("unexpected sleep"),
    )

    assert output.exists()
    assert list(frame.columns) == LONG_COLUMNS
    assert len(frame) == 12
    assert set(frame["industry"]) == {item["name"] for item in load_industries()}
    assert set(frame["metric"]) == {"nvd_cve_count_4w"}
    assert set(frame["source"]) == {"NVD CVE API"}
    cybersecurity = frame.loc[frame["industry"] == CYBERSECURITY].iloc[0]
    assert cybersecurity["status"] == "sample"
    assert pd.notna(cybersecurity["value"])
    others = frame.loc[frame["industry"] != CYBERSECURITY]
    assert set(others["status"]) == {"missing_config"}
    assert others["value"].isna().all()
    pd.testing.assert_frame_equal(frame, pd.read_csv(output)[LONG_COLUMNS])


def test_online_nvd_requests_once_for_cybersecurity_only(tmp_path):
    calls = []

    def requester(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse({"totalResults": 0})

    frame = collect_nvd(
        requester=requester,
        sleeper=lambda seconds: None,
        cache_dir=tmp_path / "cache",
        output_path=tmp_path / "nvd.csv",
        today=TODAY,
    )

    assert len(calls) == 1
    assert len(frame) == 12
    assert list(frame.columns) == LONG_COLUMNS
    cybersecurity = frame.set_index("industry").loc[CYBERSECURITY]
    assert cybersecurity["value"] == 0
    assert cybersecurity["status"] == "no_match"
    others = frame.loc[frame["industry"] != CYBERSECURITY]
    assert set(others["status"]) == {"missing_config"}
    assert others["value"].isna().all()


def test_nvd_request_uses_exact_28_day_utc_window_and_minimal_page(tmp_path):
    calls = []

    def requester(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse({"totalResults": 2501})

    frame = collect_nvd(
        industries=[industry(CYBERSECURITY)],
        requester=requester,
        sleeper=lambda seconds: None,
        cache_dir=tmp_path / "cache",
        output_path=tmp_path / "nvd.csv",
        today=TODAY,
    )

    assert calls == [
        (
            "https://services.nvd.nist.gov/rest/json/cves/2.0",
            {
                "params": {
                    "pubStartDate": "2026-05-16T00:00:00.000Z",
                    "pubEndDate": "2026-06-12T23:59:59.999Z",
                    "resultsPerPage": 1,
                },
                "timeout": 30,
            },
        )
    ]
    assert frame.loc[0, "value"] == 2501
    assert frame.loc[0, "status"] == "ok"
    assert frame.loc[0, "date"] == TODAY.isoformat()
    assert frame.loc[0, "metric"] == "nvd_cve_count_4w"
    assert frame.loc[0, "source"] == "NVD CVE API"


@pytest.mark.parametrize(
    ("payload", "expected_value", "expected_status"),
    [
        ({"totalResults": 7}, 7, "ok"),
        ({"totalResults": 0}, 0, "no_match"),
    ],
)
def test_nvd_total_results_maps_to_value_and_status(
    tmp_path, payload, expected_value, expected_status
):
    frame = collect_one(tmp_path, FakeResponse(payload))

    assert frame.loc[0, "value"] == expected_value
    assert frame.loc[0, "status"] == expected_status


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"totalResults": -1},
        {"totalResults": True},
        {"totalResults": 1.0},
        {"totalResults": "1"},
        {"totalResults": None},
    ],
)
def test_nvd_malformed_total_results_is_source_error(tmp_path, payload):
    frame = collect_one(tmp_path, FakeResponse(payload))

    assert pd.isna(frame.loc[0, "value"])
    assert frame.loc[0, "status"] == "source_error"


def test_nvd_request_failure_only_marks_cybersecurity_and_logs_context(
    tmp_path, monkeypatch
):
    messages = []
    sleeps = []

    class RecordingLogger:
        def exception(self, message, *args):
            messages.append(message % args)

    monkeypatch.setattr(fetch_nvd, "setup_logging", lambda: RecordingLogger())

    def fail(*args, **kwargs):
        raise RuntimeError("NVD unavailable")

    frame = collect_nvd(
        requester=fail,
        sleeper=sleeps.append,
        cache_dir=tmp_path / "cache",
        output_path=tmp_path / "nvd.csv",
        today=TODAY,
    )

    statuses = frame.set_index("industry")["status"]
    assert statuses[CYBERSECURITY] == "source_error"
    assert set(statuses.drop(CYBERSECURITY)) == {"missing_config"}
    assert sleeps == [6]
    assert len(messages) == 1
    assert "https://services.nvd.nist.gov/rest/json/cves/2.0" in messages[0]
    assert CYBERSECURITY in messages[0]
    assert "NVD unavailable" in messages[0]


@pytest.mark.parametrize(
    ("response", "expected_status"),
    [
        (FakeResponse({"totalResults": 1}), "ok"),
        (FakeResponse(error=RuntimeError("bad status")), "source_error"),
        (FakeResponse(json_error=ValueError("invalid json")), "source_error"),
        (FakeResponse({"totalResults": -1}), "source_error"),
    ],
)
def test_nvd_sleeps_at_least_six_seconds_after_every_response_attempt(
    tmp_path, response, expected_status
):
    sleeps = []

    frame = collect_nvd(
        industries=[industry(CYBERSECURITY)],
        requester=lambda *args, **kwargs: response,
        sleeper=sleeps.append,
        cache_dir=tmp_path / "cache",
        output_path=tmp_path / "nvd.csv",
        today=TODAY,
    )

    assert len(sleeps) == 1
    assert sleeps[0] >= 6
    assert frame.loc[0, "status"] == expected_status


@pytest.mark.parametrize(
    ("payload", "expected_value", "expected_status"),
    [
        ({"value": 7, "status": "ok"}, 7, "ok"),
        ({"value": 0, "status": "no_match"}, 0, "no_match"),
        ({"value": None, "status": "source_error"}, None, "source_error"),
        (4, 4, "ok"),
        (0, 0, "no_match"),
        (6.0, 6, "ok"),
    ],
)
def test_nvd_semantically_valid_cache_skips_request_and_sleep(
    tmp_path, payload, expected_value, expected_status
):
    cache_dir = tmp_path / "cache"
    cache_path = daily_cache_path("nvd", cache_dir=cache_dir, today=TODAY)
    write_json_cache(cache_path, {CYBERSECURITY: payload})

    frame = collect_nvd(
        industries=[industry(CYBERSECURITY)],
        requester=lambda *args, **kwargs: pytest.fail("unexpected request"),
        sleeper=lambda seconds: pytest.fail("unexpected sleep"),
        cache_dir=cache_dir,
        output_path=tmp_path / "nvd.csv",
        today=TODAY,
    )

    value = frame.loc[0, "value"]
    if expected_value is None:
        assert pd.isna(value)
    else:
        assert value == expected_value
    assert frame.loc[0, "status"] == expected_status


@pytest.mark.parametrize(
    "payload",
    [
        {"value": 0, "status": "ok"},
        {"value": -1, "status": "ok"},
        {"value": 1.0, "status": "ok"},
        {"value": True, "status": "ok"},
        {"value": 1, "status": "no_match"},
        {"value": False, "status": "no_match"},
        {"value": 0, "status": "source_error"},
        {"value": None, "status": "ok"},
        {"value": None, "status": "no_match"},
        {"value": 1, "status": "unknown"},
        True,
        -1,
        1.5,
        math.nan,
        math.inf,
        -math.inf,
        None,
    ],
)
def test_nvd_semantically_invalid_cache_requests_online(tmp_path, payload):
    cache_dir = tmp_path / "cache"
    cache_path = daily_cache_path("nvd", cache_dir=cache_dir, today=TODAY)
    write_json_cache(cache_path, {CYBERSECURITY: payload})
    calls = []
    sleeps = []

    def requester(url, **kwargs):
        calls.append(url)
        return FakeResponse({"totalResults": 2})

    frame = collect_nvd(
        industries=[industry(CYBERSECURITY)],
        requester=requester,
        sleeper=sleeps.append,
        cache_dir=cache_dir,
        output_path=tmp_path / "nvd.csv",
        today=TODAY,
    )

    assert calls == ["https://services.nvd.nist.gov/rest/json/cves/2.0"]
    assert sleeps == [6]
    assert frame.loc[0, "value"] == 2
    assert frame.loc[0, "status"] == "ok"


def test_damaged_nvd_cache_requests_online(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_path = daily_cache_path("nvd", cache_dir=cache_dir, today=TODAY)
    cache_dir.mkdir()
    cache_path.write_text("{damaged", encoding="utf-8")
    calls = []

    def requester(url, **kwargs):
        calls.append(url)
        return FakeResponse({"totalResults": 2})

    frame = collect_nvd(
        industries=[industry(CYBERSECURITY)],
        requester=requester,
        sleeper=lambda seconds: None,
        cache_dir=cache_dir,
        output_path=tmp_path / "nvd.csv",
        today=TODAY,
    )

    assert calls == ["https://services.nvd.nist.gov/rest/json/cves/2.0"]
    assert frame.loc[0, "value"] == 2
    assert frame.loc[0, "status"] == "ok"


@pytest.mark.parametrize(
    ("response", "expected_cache"),
    [
        (
            FakeResponse({"totalResults": 5}),
            {CYBERSECURITY: {"value": 5, "status": "ok"}},
        ),
        (
            FakeResponse({"totalResults": 0}),
            {CYBERSECURITY: {"value": 0, "status": "no_match"}},
        ),
        (
            FakeResponse({"totalResults": -1}),
            {CYBERSECURITY: {"value": None, "status": "source_error"}},
        ),
    ],
)
def test_online_nvd_writes_status_aware_same_day_cache(
    tmp_path, response, expected_cache
):
    cache_dir = tmp_path / "cache"

    collect_nvd(
        industries=[industry(CYBERSECURITY)],
        requester=lambda *args, **kwargs: response,
        sleeper=lambda seconds: None,
        cache_dir=cache_dir,
        output_path=tmp_path / "nvd.csv",
        today=TODAY,
    )

    cache_path = daily_cache_path("nvd", cache_dir=cache_dir, today=TODAY)
    assert read_json_cache(cache_path) == expected_cache
