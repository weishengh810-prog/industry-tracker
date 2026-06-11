from scripts.fetch_market import collect_market, market_row


def test_market_row_marks_empty_proxy_as_missing_config():
    row = market_row({"name": "低空经济", "market_proxy": None}, offline=False)

    assert row["status"] == "missing_config"
    assert row["value"] is None


def test_collect_market_offline_preserves_missing_proxy(tmp_path):
    output = tmp_path / "market.csv"

    frame = collect_market(offline=True, output_path=output)

    assert output.exists()
    assert "sample" in set(frame["status"])
    assert "missing_config" in set(frame["status"])
    assert len(frame) == 12
