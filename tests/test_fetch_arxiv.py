from datetime import date
import math

import pandas as pd
import pytest

import scripts.fetch_arxiv as fetch_arxiv
from scripts.common import LONG_COLUMNS, load_industries
from scripts.fetch_arxiv import collect_arxiv
from scripts.source_cache import daily_cache_path, read_json_cache, write_json_cache


COVERED = {"人工智能", "半导体", "机器人", "医药健康"}
TODAY = date(2026, 6, 12)
ATOM_EMPTY = b"<?xml version='1.0'?><feed xmlns='http://www.w3.org/2005/Atom'/>"
ATOM_TWO_ENTRIES = b"""<?xml version='1.0'?>
<atom:feed xmlns:atom='http://www.w3.org/2005/Atom'>
  <atom:entry><atom:id>one</atom:id></atom:entry>
  <atom:entry><atom:id>two</atom:id></atom:entry>
</atom:feed>
"""
ATOM_TOTAL_2501 = b"""<?xml version='1.0'?>
<feed xmlns='http://www.w3.org/2005/Atom'
      xmlns:opensearch='http://a9.com/-/spec/opensearch/1.1/'>
  <opensearch:totalResults>2501</opensearch:totalResults>
  <entry><id>one</id></entry>
</feed>
"""


class FakeResponse:
    def __init__(self, content: bytes, error: Exception | None = None):
        self.content = content
        self.error = error

    def raise_for_status(self):
        if self.error is not None:
            raise self.error


def industry(name):
    return next(item for item in load_industries() if item["name"] == name)


def test_offline_arxiv_reads_strict_sample_without_request_or_sleep(tmp_path):
    output = tmp_path / "arxiv.csv"

    frame = collect_arxiv(
        offline=True,
        output_path=output,
        requester=lambda *args, **kwargs: pytest.fail("unexpected request"),
        sleeper=lambda seconds: pytest.fail("unexpected sleep"),
    )

    assert output.exists()
    assert list(frame.columns) == LONG_COLUMNS
    assert len(frame) == 12
    assert set(frame["industry"]) == {item["name"] for item in load_industries()}
    assert set(frame["metric"]) == {"arxiv_paper_count_4w"}
    assert set(frame["source"]) == {"arXiv API"}
    assert set(frame.loc[frame["industry"].isin(COVERED), "status"]) == {"sample"}
    assert frame.loc[frame["industry"].isin(COVERED), "value"].notna().all()
    assert set(frame.loc[~frame["industry"].isin(COVERED), "status"]) == {
        "missing_config"
    }
    assert frame.loc[~frame["industry"].isin(COVERED), "value"].isna().all()
    pd.testing.assert_frame_equal(frame, pd.read_csv(output)[LONG_COLUMNS])


def test_online_arxiv_requests_exactly_the_four_covered_industries(tmp_path):
    calls = []

    def requester(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(ATOM_EMPTY)

    frame = collect_arxiv(
        requester=requester,
        sleeper=lambda seconds: None,
        cache_dir=tmp_path / "cache",
        output_path=tmp_path / "arxiv.csv",
        today=TODAY,
    )

    assert len(calls) == 4
    assert set(frame.loc[frame["status"] != "missing_config", "industry"]) == COVERED
    assert set(frame.loc[~frame["industry"].isin(COVERED), "status"]) == {
        "missing_config"
    }
    assert frame.loc[~frame["industry"].isin(COVERED), "value"].isna().all()


def test_arxiv_query_uses_first_two_english_keywords_and_28_day_range(tmp_path):
    calls = []
    ai = industry("人工智能")

    def requester(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(ATOM_EMPTY)

    collect_arxiv(
        industries=[ai],
        requester=requester,
        sleeper=lambda seconds: None,
        cache_dir=tmp_path / "cache",
        output_path=tmp_path / "arxiv.csv",
        today=TODAY,
    )

    url, kwargs = calls[0]
    query = kwargs["params"]["search_query"]
    assert url == "https://export.arxiv.org/api/query"
    assert 'all:"artificial intelligence"' in query
    assert 'all:"large language model"' in query
    assert "generative AI" not in query
    assert "人工智能" not in query
    assert "submittedDate:[202605160000 TO 202606122359]" in query
    assert "202605150000" not in query
    assert kwargs["params"]["max_results"] == 1


def test_arxiv_positive_atom_result_counts_namespaced_entries(tmp_path):
    frame = collect_arxiv(
        industries=[industry("半导体")],
        requester=lambda *args, **kwargs: FakeResponse(ATOM_TWO_ENTRIES),
        sleeper=lambda seconds: None,
        cache_dir=tmp_path / "cache",
        output_path=tmp_path / "arxiv.csv",
        today=TODAY,
    )

    assert frame.loc[0, "value"] == 2
    assert frame.loc[0, "status"] == "ok"
    assert frame.loc[0, "date"] == TODAY.isoformat()
    assert list(frame.columns) == LONG_COLUMNS


def test_arxiv_uses_authoritative_total_results_instead_of_returned_entries(
    tmp_path,
):
    frame = collect_arxiv(
        industries=[industry("人工智能")],
        requester=lambda *args, **kwargs: FakeResponse(ATOM_TOTAL_2501),
        sleeper=lambda seconds: None,
        cache_dir=tmp_path / "cache",
        output_path=tmp_path / "arxiv.csv",
        today=TODAY,
    )

    assert frame.loc[0, "value"] == 2501
    assert frame.loc[0, "status"] == "ok"


@pytest.mark.parametrize("total_results", [b"-1", b"not-an-integer"])
def test_arxiv_invalid_total_results_is_source_error(tmp_path, total_results):
    content = (
        b"<?xml version='1.0'?><feed xmlns='http://www.w3.org/2005/Atom' "
        b"xmlns:opensearch='http://a9.com/-/spec/opensearch/1.1/'>"
        b"<opensearch:totalResults>"
        + total_results
        + b"</opensearch:totalResults><entry/></feed>"
    )

    frame = collect_arxiv(
        industries=[industry("人工智能")],
        requester=lambda *args, **kwargs: FakeResponse(content),
        sleeper=lambda seconds: None,
        cache_dir=tmp_path / "cache",
        output_path=tmp_path / "arxiv.csv",
        today=TODAY,
    )

    assert pd.isna(frame.loc[0, "value"])
    assert frame.loc[0, "status"] == "source_error"


def test_arxiv_empty_result_is_zero_and_no_match(tmp_path):
    frame = collect_arxiv(
        industries=[industry("机器人")],
        requester=lambda *args, **kwargs: FakeResponse(ATOM_EMPTY),
        sleeper=lambda seconds: None,
        cache_dir=tmp_path / "cache",
        output_path=tmp_path / "arxiv.csv",
        today=TODAY,
    )

    assert frame.loc[0, "value"] == 0
    assert frame.loc[0, "status"] == "no_match"


def test_arxiv_cache_hit_recreates_value_and_status_without_request_or_sleep(
    tmp_path,
):
    cache_dir = tmp_path / "cache"
    cache_path = daily_cache_path("arxiv", cache_dir=cache_dir, today=TODAY)
    write_json_cache(
        cache_path,
        {"人工智能": {"value": 0, "status": "no_match"}},
    )

    frame = collect_arxiv(
        industries=[industry("人工智能")],
        requester=lambda *args, **kwargs: pytest.fail("unexpected request"),
        sleeper=lambda seconds: pytest.fail("unexpected sleep"),
        cache_dir=cache_dir,
        output_path=tmp_path / "arxiv.csv",
        today=TODAY,
    )

    assert frame.loc[0, "value"] == 0
    assert frame.loc[0, "status"] == "no_match"


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
def test_arxiv_accepts_semantically_valid_cache_entries(
    tmp_path, payload, expected_value, expected_status
):
    cache_dir = tmp_path / "cache"
    cache_path = daily_cache_path("arxiv", cache_dir=cache_dir, today=TODAY)
    write_json_cache(cache_path, {"人工智能": payload})

    frame = collect_arxiv(
        industries=[industry("人工智能")],
        requester=lambda *args, **kwargs: pytest.fail("unexpected request"),
        sleeper=lambda seconds: pytest.fail("unexpected sleep"),
        cache_dir=cache_dir,
        output_path=tmp_path / "arxiv.csv",
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
def test_arxiv_rejects_malformed_cache_and_requests_online(tmp_path, payload):
    cache_dir = tmp_path / "cache"
    cache_path = daily_cache_path("arxiv", cache_dir=cache_dir, today=TODAY)
    write_json_cache(cache_path, {"人工智能": payload})
    calls = []

    def requester(url, **kwargs):
        calls.append(url)
        return FakeResponse(ATOM_TWO_ENTRIES)

    frame = collect_arxiv(
        industries=[industry("人工智能")],
        requester=requester,
        sleeper=lambda seconds: None,
        cache_dir=cache_dir,
        output_path=tmp_path / "arxiv.csv",
        today=TODAY,
    )

    assert calls == ["https://export.arxiv.org/api/query"]
    assert frame.loc[0, "value"] == 2
    assert frame.loc[0, "status"] == "ok"


def test_damaged_arxiv_cache_proceeds_with_online_request(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_path = daily_cache_path("arxiv", cache_dir=cache_dir, today=TODAY)
    cache_dir.mkdir()
    cache_path.write_text("{damaged", encoding="utf-8")
    calls = []

    def requester(url, **kwargs):
        calls.append(url)
        return FakeResponse(ATOM_TWO_ENTRIES)

    frame = collect_arxiv(
        industries=[industry("人工智能")],
        requester=requester,
        sleeper=lambda seconds: None,
        cache_dir=cache_dir,
        output_path=tmp_path / "arxiv.csv",
        today=TODAY,
    )

    assert calls == ["https://export.arxiv.org/api/query"]
    assert frame.loc[0, "value"] == 2
    assert frame.loc[0, "status"] == "ok"


def test_arxiv_request_failure_is_per_industry_and_collection_continues(tmp_path):
    calls = []
    sleeps = []

    def requester(url, **kwargs):
        calls.append(kwargs["params"]["search_query"])
        if len(calls) == 1:
            raise RuntimeError("network down")
        return FakeResponse(ATOM_TWO_ENTRIES)

    frame = collect_arxiv(
        industries=[industry("人工智能"), industry("半导体")],
        requester=requester,
        sleeper=sleeps.append,
        cache_dir=tmp_path / "cache",
        output_path=tmp_path / "arxiv.csv",
        today=TODAY,
    )

    assert len(calls) == 2
    assert sleeps == [3, 3]
    assert frame.set_index("industry").loc["人工智能", "status"] == "source_error"
    assert pd.isna(frame.set_index("industry").loc["人工智能", "value"])
    assert frame.set_index("industry").loc["半导体", "status"] == "ok"
    assert frame.set_index("industry").loc["半导体", "value"] == 2


def test_arxiv_request_failure_logs_endpoint_industry_and_error(tmp_path, monkeypatch):
    messages = []

    class RecordingLogger:
        def exception(self, message, *args):
            messages.append(message % args)

    monkeypatch.setattr(fetch_arxiv, "setup_logging", lambda: RecordingLogger())

    collect_arxiv(
        industries=[industry("人工智能")],
        requester=lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("network down")
        ),
        sleeper=lambda seconds: None,
        cache_dir=tmp_path / "cache",
        output_path=tmp_path / "arxiv.csv",
        today=TODAY,
    )

    assert len(messages) == 1
    assert "https://export.arxiv.org/api/query" in messages[0]
    assert "人工智能" in messages[0]
    assert "network down" in messages[0]


@pytest.mark.parametrize(
    ("response", "expected_status"),
    [
        (FakeResponse(ATOM_EMPTY), "no_match"),
        (FakeResponse(b"<not-xml"), "source_error"),
        (FakeResponse(ATOM_EMPTY, RuntimeError("bad status")), "source_error"),
    ],
)
def test_arxiv_sleeps_at_least_three_seconds_after_every_attempt(
    tmp_path, response, expected_status
):
    sleeps = []

    frame = collect_arxiv(
        industries=[industry("医药健康")],
        requester=lambda *args, **kwargs: response,
        sleeper=sleeps.append,
        cache_dir=tmp_path / "cache",
        output_path=tmp_path / "arxiv.csv",
        today=TODAY,
    )

    assert len(sleeps) == 1
    assert sleeps[0] >= 3
    assert frame.loc[0, "status"] == expected_status


def test_online_arxiv_writes_status_aware_same_day_cache(tmp_path):
    cache_dir = tmp_path / "cache"

    collect_arxiv(
        industries=[industry("机器人")],
        requester=lambda *args, **kwargs: FakeResponse(ATOM_EMPTY),
        sleeper=lambda seconds: None,
        cache_dir=cache_dir,
        output_path=tmp_path / "arxiv.csv",
        today=TODAY,
    )

    cache_path = daily_cache_path("arxiv", cache_dir=cache_dir, today=TODAY)
    assert read_json_cache(cache_path) == {
        "机器人": {"value": 0, "status": "no_match"}
    }
