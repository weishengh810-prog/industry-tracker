import logging

from scripts.common import LONG_COLUMNS, load_industries, setup_logging


def test_industry_config_has_12_entries_and_allows_empty_proxy():
    industries = load_industries()

    assert len(industries) == 12
    assert {"name", "keywords", "market_proxy"} <= industries[0].keys()
    assert any(item["market_proxy"] is None for item in industries)
    assert LONG_COLUMNS == [
        "industry",
        "date",
        "metric",
        "value",
        "source",
        "status",
    ]


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
