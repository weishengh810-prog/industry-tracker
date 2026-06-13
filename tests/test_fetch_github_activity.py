from datetime import date
import math

import pandas as pd
import pytest

import scripts.fetch_github_activity as fetch_github_activity
from scripts.common import LONG_COLUMNS, load_industries
from scripts.fetch_github_activity import collect_github_activity
from scripts.source_cache import daily_cache_path, read_json_cache, write_json_cache


COVERED = {"人工智能", "半导体", "机器人", "网络安全"}
TODAY = date(2026, 6, 12)


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
    return collect_github_activity(
        industries=[industry("人工智能")],
        requester=lambda *args, **request_kwargs: response,
        sleeper=lambda seconds: None,
        random_uniform=lambda start, end: 60,
        cache_dir=tmp_path / "cache",
        output_path=tmp_path / "github.csv",
        today=TODAY,
        **kwargs,
    )


def test_offline_github_reads_strict_sample_without_request_or_sleep(tmp_path):
    output = tmp_path / "github.csv"

    frame = collect_github_activity(
        offline=True,
        output_path=output,
        requester=lambda *args, **kwargs: pytest.fail("unexpected request"),
        sleeper=lambda seconds: pytest.fail("unexpected sleep"),
        random_uniform=lambda start, end: pytest.fail("unexpected random delay"),
    )

    assert output.exists()
    assert list(frame.columns) == LONG_COLUMNS
    assert len(frame) == 12
    assert set(frame["industry"]) == {item["name"] for item in load_industries()}
    assert set(frame["metric"]) == {"github_repo_count_4w"}
    assert set(frame["source"]) == {"GitHub Search API"}
    assert set(frame.loc[frame["industry"].isin(COVERED), "status"]) == {"sample"}
    assert frame.loc[frame["industry"].isin(COVERED), "value"].notna().all()
    assert set(frame.loc[~frame["industry"].isin(COVERED), "status"]) == {
        "missing_config"
    }
    assert frame.loc[~frame["industry"].isin(COVERED), "value"].isna().all()
    pd.testing.assert_frame_equal(frame, pd.read_csv(output)[LONG_COLUMNS])


def test_online_github_requests_exactly_four_covered_industries(tmp_path):
    calls = []

    def requester(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse({"total_count": 0, "incomplete_results": False})

    frame = collect_github_activity(
        requester=requester,
        sleeper=lambda seconds: None,
        random_uniform=lambda start, end: 60,
        cache_dir=tmp_path / "cache",
        output_path=tmp_path / "github.csv",
        today=TODAY,
    )

    assert len(calls) == 4
    assert set(frame.loc[frame["status"] != "missing_config", "industry"]) == COVERED
    assert len(frame) == 12
    assert list(frame.columns) == LONG_COLUMNS
    assert set(frame.loc[~frame["industry"].isin(COVERED), "status"]) == {
        "missing_config"
    }
    assert frame.loc[~frame["industry"].isin(COVERED), "value"].isna().all()


def test_github_request_uses_query_headers_cutoff_and_no_pagination(tmp_path):
    calls = []

    def requester(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse({"total_count": 2501, "incomplete_results": False})

    frame = collect_github_activity(
        industries=[industry("人工智能")],
        requester=requester,
        sleeper=lambda seconds: None,
        random_uniform=lambda start, end: 60,
        cache_dir=tmp_path / "cache",
        output_path=tmp_path / "github.csv",
        today=TODAY,
    )

    assert calls == [
        (
            "https://api.github.com/search/repositories",
            {
                "params": {
                    "q": '"artificial intelligence" OR "large language model" '
                    "created:>2026-05-15",
                    "per_page": 1,
                },
                "headers": {
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "industry-tracker/1.0",
                },
                "timeout": 30,
            },
        )
    ]
    assert frame.loc[0, "value"] == 2501
    assert frame.loc[0, "status"] == "ok"
    assert frame.loc[0, "date"] == TODAY.isoformat()
    assert frame.loc[0, "metric"] == "github_repo_count_4w"
    assert frame.loc[0, "source"] == "GitHub Search API"


def test_github_query_only_quotes_multiword_terms(tmp_path):
    calls = []

    def requester(url, **kwargs):
        calls.append(kwargs["params"]["q"])
        return FakeResponse({"total_count": 1, "incomplete_results": False})

    collect_github_activity(
        industries=[industry("半导体"), industry("机器人")],
        requester=requester,
        sleeper=lambda seconds: None,
        random_uniform=lambda start, end: 60,
        cache_dir=tmp_path / "cache",
        output_path=tmp_path / "github.csv",
        today=TODAY,
    )

    assert calls == [
        "semiconductor OR chip created:>2026-05-15",
        'robotics OR "industrial robot" created:>2026-05-15',
    ]


@pytest.mark.parametrize(
    ("payload", "expected_value", "expected_status"),
    [
        ({"total_count": 7, "incomplete_results": False}, 7, "ok"),
        ({"total_count": 0, "incomplete_results": False}, 0, "no_match"),
    ],
)
def test_github_total_count_maps_to_value_and_status(
    tmp_path, payload, expected_value, expected_status
):
    frame = collect_one(tmp_path, FakeResponse(payload))

    assert frame.loc[0, "value"] == expected_value
    assert frame.loc[0, "status"] == expected_status


@pytest.mark.parametrize(
    "payload",
    [
        {"incomplete_results": False},
        {"total_count": -1, "incomplete_results": False},
        {"total_count": True, "incomplete_results": False},
        {"total_count": 1.0, "incomplete_results": False},
        {"total_count": "1", "incomplete_results": False},
        {"total_count": None, "incomplete_results": False},
    ],
)
def test_github_malformed_total_count_is_source_error(tmp_path, payload):
    frame = collect_one(tmp_path, FakeResponse(payload))

    assert pd.isna(frame.loc[0, "value"])
    assert frame.loc[0, "status"] == "source_error"


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(
            {"total_count": 7, "incomplete_results": True},
            id="true",
        ),
        pytest.param({"total_count": 7}, id="missing"),
        pytest.param(
            {"total_count": 7, "incomplete_results": 0},
            id="integer-zero",
        ),
        pytest.param(
            {"total_count": 7, "incomplete_results": 1},
            id="integer-one",
        ),
        pytest.param(
            {"total_count": 7, "incomplete_results": "false"},
            id="string",
        ),
        pytest.param(
            {"total_count": 7, "incomplete_results": None},
            id="null",
        ),
    ],
)
def test_github_invalid_incomplete_results_is_cached_source_error(tmp_path, payload):
    cache_dir = tmp_path / "cache"

    frame = collect_one(tmp_path, FakeResponse(payload))

    assert pd.isna(frame.loc[0, "value"])
    assert frame.loc[0, "status"] == "source_error"
    cache_path = daily_cache_path("github", cache_dir=cache_dir, today=TODAY)
    assert read_json_cache(cache_path) == {
        "人工智能": {"value": None, "status": "source_error"}
    }


def test_github_invalid_json_is_source_error(tmp_path):
    frame = collect_one(
        tmp_path,
        FakeResponse(json_error=ValueError("invalid json")),
    )

    assert pd.isna(frame.loc[0, "value"])
    assert frame.loc[0, "status"] == "source_error"


def test_github_request_failure_logs_and_collection_continues(tmp_path, monkeypatch):
    messages = []
    calls = []

    class RecordingLogger:
        def exception(self, message, *args):
            messages.append(message % args)

    monkeypatch.setattr(
        fetch_github_activity,
        "setup_logging",
        lambda: RecordingLogger(),
    )

    def requester(url, **kwargs):
        calls.append(kwargs["params"]["q"])
        if len(calls) == 1:
            raise RuntimeError("network down")
        return FakeResponse({"total_count": 3, "incomplete_results": False})

    frame = collect_github_activity(
        industries=[industry("人工智能"), industry("半导体")],
        requester=requester,
        sleeper=lambda seconds: None,
        random_uniform=lambda start, end: 60,
        cache_dir=tmp_path / "cache",
        output_path=tmp_path / "github.csv",
        today=TODAY,
    ).set_index("industry")

    assert len(calls) == 2
    assert frame.loc["人工智能", "status"] == "source_error"
    assert pd.isna(frame.loc["人工智能", "value"])
    assert frame.loc["半导体", "status"] == "ok"
    assert frame.loc["半导体", "value"] == 3
    assert len(messages) == 1
    assert "https://api.github.com/search/repositories" in messages[0]
    assert "人工智能" in messages[0]
    assert "network down" in messages[0]


@pytest.mark.parametrize(
    ("response", "expected_status"),
    [
        (FakeResponse({"total_count": 1, "incomplete_results": False}), "ok"),
        (FakeResponse(error=RuntimeError("bad status")), "source_error"),
        (FakeResponse(json_error=ValueError("invalid json")), "source_error"),
    ],
)
def test_github_sleeps_once_after_each_attempt_with_injected_delay(
    tmp_path, response, expected_status
):
    random_calls = []
    sleeps = []

    def random_uniform(start, end):
        random_calls.append((start, end))
        return 67.5

    frame = collect_github_activity(
        industries=[industry("网络安全")],
        requester=lambda *args, **kwargs: response,
        sleeper=sleeps.append,
        random_uniform=random_uniform,
        cache_dir=tmp_path / "cache",
        output_path=tmp_path / "github.csv",
        today=TODAY,
    )

    assert random_calls == [(60, 75)]
    assert sleeps == [67.5]
    assert 60 <= sleeps[0] <= 75
    assert frame.loc[0, "status"] == expected_status


def test_github_cache_hit_recreates_rows_without_request_sleep_or_random(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_path = daily_cache_path("github", cache_dir=cache_dir, today=TODAY)
    write_json_cache(
        cache_path,
        {
            "人工智能": {"value": 4, "status": "ok"},
            "半导体": {"value": 0, "status": "no_match"},
            "机器人": {"value": None, "status": "source_error"},
            "网络安全": {"value": 8, "status": "ok"},
        },
    )

    frame = collect_github_activity(
        requester=lambda *args, **kwargs: pytest.fail("unexpected request"),
        sleeper=lambda seconds: pytest.fail("unexpected sleep"),
        random_uniform=lambda start, end: pytest.fail("unexpected random delay"),
        cache_dir=cache_dir,
        output_path=tmp_path / "github.csv",
        today=TODAY,
    ).set_index("industry")

    assert frame.loc["人工智能", "value"] == 4
    assert frame.loc["人工智能", "status"] == "ok"
    assert frame.loc["半导体", "value"] == 0
    assert frame.loc["半导体", "status"] == "no_match"
    assert pd.isna(frame.loc["机器人", "value"])
    assert frame.loc["机器人", "status"] == "source_error"


@pytest.mark.parametrize(
    ("payload", "expected_value", "expected_status"),
    [
        (4, 4, "ok"),
        (0, 0, "no_match"),
        (6.0, 6, "ok"),
    ],
)
def test_github_accepts_arxiv_compatible_numeric_cache_entries(
    tmp_path, payload, expected_value, expected_status
):
    cache_dir = tmp_path / "cache"
    cache_path = daily_cache_path("github", cache_dir=cache_dir, today=TODAY)
    write_json_cache(cache_path, {"人工智能": payload})

    frame = collect_github_activity(
        industries=[industry("人工智能")],
        requester=lambda *args, **kwargs: pytest.fail("unexpected request"),
        sleeper=lambda seconds: pytest.fail("unexpected sleep"),
        random_uniform=lambda start, end: pytest.fail("unexpected random delay"),
        cache_dir=cache_dir,
        output_path=tmp_path / "github.csv",
        today=TODAY,
    )

    assert frame.loc[0, "value"] == expected_value
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
def test_github_semantically_invalid_cache_requests_online(tmp_path, payload):
    cache_dir = tmp_path / "cache"
    cache_path = daily_cache_path("github", cache_dir=cache_dir, today=TODAY)
    write_json_cache(cache_path, {"人工智能": payload})
    calls = []

    def requester(url, **kwargs):
        calls.append(url)
        return FakeResponse({"total_count": 2, "incomplete_results": False})

    frame = collect_github_activity(
        industries=[industry("人工智能")],
        requester=requester,
        sleeper=lambda seconds: None,
        random_uniform=lambda start, end: 60,
        cache_dir=cache_dir,
        output_path=tmp_path / "github.csv",
        today=TODAY,
    )

    assert calls == ["https://api.github.com/search/repositories"]
    assert frame.loc[0, "value"] == 2
    assert frame.loc[0, "status"] == "ok"


def test_damaged_github_cache_requests_online(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_path = daily_cache_path("github", cache_dir=cache_dir, today=TODAY)
    cache_dir.mkdir()
    cache_path.write_text("{damaged", encoding="utf-8")
    calls = []

    def requester(url, **kwargs):
        calls.append(url)
        return FakeResponse({"total_count": 2, "incomplete_results": False})

    frame = collect_github_activity(
        industries=[industry("人工智能")],
        requester=requester,
        sleeper=lambda seconds: None,
        random_uniform=lambda start, end: 60,
        cache_dir=cache_dir,
        output_path=tmp_path / "github.csv",
        today=TODAY,
    )

    assert calls == ["https://api.github.com/search/repositories"]
    assert frame.loc[0, "value"] == 2
    assert frame.loc[0, "status"] == "ok"


def test_online_github_writes_all_covered_status_aware_cache_entries(tmp_path):
    cache_dir = tmp_path / "cache"
    responses = iter(
        [
            FakeResponse({"total_count": 5, "incomplete_results": False}),
            FakeResponse({"total_count": 0, "incomplete_results": False}),
            FakeResponse({"total_count": True, "incomplete_results": False}),
            FakeResponse(error=RuntimeError("bad status")),
        ]
    )

    collect_github_activity(
        requester=lambda *args, **kwargs: next(responses),
        sleeper=lambda seconds: None,
        random_uniform=lambda start, end: 60,
        cache_dir=cache_dir,
        output_path=tmp_path / "github.csv",
        today=TODAY,
    )

    cache_path = daily_cache_path("github", cache_dir=cache_dir, today=TODAY)
    assert read_json_cache(cache_path) == {
        "人工智能": {"value": 5, "status": "ok"},
        "半导体": {"value": 0, "status": "no_match"},
        "机器人": {"value": None, "status": "source_error"},
        "网络安全": {"value": None, "status": "source_error"},
    }
