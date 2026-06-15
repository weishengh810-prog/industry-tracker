import logging

import pandas as pd
import pytest

import scripts.common as common
from scripts.common import (
    LONG_COLUMNS,
    VALID_METRICS,
    VALID_STATUSES,
    ensure_directories,
    load_industries,
    load_sources,
    setup_logging,
)


def test_industry_config_has_required_keywords_and_us_market_proxies():
    industries = load_industries()
    expected = {
        "人工智能": (
            ["artificial intelligence", "large language model", "generative AI"],
            "AIQ",
            "Global X Artificial Intelligence & Technology ETF",
        ),
        "半导体": (
            ["semiconductor", "chip", "integrated circuit"],
            "SMH",
            "VanEck Semiconductor ETF",
        ),
        "新能源汽车": (
            ["electric vehicle", "EV battery", "autonomous driving"],
            "DRIV",
            "Global X Autonomous & Electric Vehicles ETF",
        ),
        "储能": (
            ["energy storage", "battery storage", "grid storage"],
            "BATT",
            "Amplify Lithium & Battery Technology ETF",
        ),
        "机器人": (
            ["robotics", "industrial robot", "humanoid robot"],
            "ROBO",
            "ROBO Global Robotics and Automation Index ETF",
        ),
        "低空经济": (
            ["drone", "eVTOL", "urban air mobility"],
            "ARKX",
            "ARK Space Exploration & Innovation ETF",
        ),
        "跨境电商": (
            ["cross-border e-commerce", "global marketplace", "overseas warehouse"],
            "EMQQ",
            "EMQQ The Emerging Markets Internet & Ecommerce ETF",
        ),
        "医药健康": (
            ["pharmaceutical", "biotech", "medical device"],
            "IXJ",
            "iShares Global Healthcare ETF",
        ),
        "消费零售": (
            ["consumer retail", "e-commerce", "consumer goods"],
            "CHIQ",
            "Global X MSCI China Consumer Discretionary ETF",
        ),
        "物流供应链": (
            ["logistics", "supply chain", "freight"],
            "SHPP",
            "Pacer Industrials and Logistics ETF",
        ),
        "旅游": (
            ["tourism", "travel", "hospitality"],
            "AWAY",
            "Amplify Travel Tech ETF",
        ),
        "网络安全": (
            ["cybersecurity", "information security", "network security"],
            "CIBR",
            "First Trust NASDAQ Cybersecurity ETF",
        ),
    }

    assert len(industries) == 12
    assert {item["name"] for item in industries} == set(expected)
    for item in industries:
        keywords_en, ticker, proxy_name = expected[item["name"]]
        assert item["keywords"]
        assert item["keywords_en"] == keywords_en
        assert item["market_proxy"] == {"ticker": ticker, "name": proxy_name}
        assert not ticker.endswith((".SZ", ".SS"))


def test_source_config_removes_policy_sources_but_keeps_news():
    sources = load_sources()

    assert sources["policy"] == []
    assert sources["news"] == [
        {
            "name": "Google News 中文科技",
            "url": (
                "https://news.google.com/rss/search?"
                "q=%E7%A7%91%E6%8A%80%20OR%20%E4%BA%A7%E4%B8%9A"
                "&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
            ),
            "type": "rss",
        }
    ]


def test_metric_extension_preserves_long_columns_and_statuses():
    assert LONG_COLUMNS == [
        "industry",
        "date",
        "metric",
        "value",
        "source",
        "status",
    ]
    assert VALID_METRICS == {
        "news_heat",
        "policy_heat",
        "market_return_3m",
        "market_return_4w",
        "market_volume_change_4w",
        "arxiv_paper_count_4w",
        "github_repo_count_4w",
        "nvd_cve_count_4w",
    }
    assert VALID_STATUSES == {
        "ok",
        "sample",
        "missing_config",
        "source_error",
        "insufficient_data",
        "no_match",
    }


def test_setup_logging_writes_separate_error_log(tmp_path):
    logger = setup_logging(tmp_path)

    logger.error("test source failure")
    for handler in logger.handlers:
        handler.flush()

    error_log = tmp_path / "logs" / "error.log"
    assert error_log.exists()
    assert "test source failure" in error_log.read_text(encoding="utf-8")
    assert any(
        isinstance(handler, logging.FileHandler) for handler in logger.handlers
    )


def test_ensure_directories_creates_cache_directory(tmp_path):
    ensure_directories(tmp_path)

    assert (tmp_path / "data" / "cache").is_dir()


def _create_archive_dates(root, dates):
    for archive_date in dates:
        (root / "archives" / archive_date).mkdir(parents=True)


def _write_current_data(root, frame):
    path = root / "data" / "processed" / "industry_metrics_long.csv"
    path.parent.mkdir(parents=True)
    frame.to_csv(path, index=False)


def test_history_days_unions_27_archives_with_current_pipeline_date(tmp_path):
    archive_dates = pd.date_range(
        "2026-05-01",
        periods=27,
        freq="D",
    ).strftime("%Y-%m-%d")
    _create_archive_dates(tmp_path, archive_dates)
    _write_current_data(
        tmp_path,
        pd.DataFrame({"date": ["2026-05-28", "2026-05-28"]}),
    )

    assert common.current_pipeline_date(tmp_path) == "2026-05-28"
    assert common.history_days(tmp_path) == 28


def test_history_days_does_not_duplicate_already_archived_current_date(
    tmp_path,
):
    _create_archive_dates(
        tmp_path,
        ["2026-05-27", "2026-05-28"],
    )
    _write_current_data(
        tmp_path,
        pd.DataFrame({"date": ["2026-05-28"]}),
    )

    assert common.history_days(tmp_path) == 2


def test_history_days_ignores_non_iso_archive_directories(tmp_path):
    _create_archive_dates(
        tmp_path,
        ["2026-05-27", "2026-5-28", "notes", "2026-02-30"],
    )

    assert common.history_days(tmp_path) == 1


@pytest.mark.parametrize(
    "frame",
    [
        pd.DataFrame(),
        pd.DataFrame({"industry": ["人工智能"]}),
    ],
)
def test_history_days_uses_only_archives_when_current_data_has_no_date(
    tmp_path,
    frame,
):
    _create_archive_dates(
        tmp_path,
        ["2026-05-27", "2026-05-28"],
    )
    _write_current_data(tmp_path, frame)

    assert common.current_pipeline_date(tmp_path) is None
    assert common.history_days(tmp_path) == 2
