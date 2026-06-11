from scripts.common import LONG_COLUMNS, load_industries


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
