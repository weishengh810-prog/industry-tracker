from scripts.fetch_news import collect_news


def test_collect_news_offline_marks_sample(tmp_path):
    output = tmp_path / "news.csv"

    frame = collect_news(offline=True, output_path=output)

    assert output.exists()
    assert set(frame["metric"]) == {"news_heat"}
    assert set(frame["status"]) == {"sample"}
    assert len(frame) == 12
