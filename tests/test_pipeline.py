import logging

from scripts.run_pipeline import _run_collector, _source_error_frame, run_pipeline


def test_source_error_frame_accepts_single_metric():
    frame = _source_error_frame("news_heat", "news")

    assert len(frame) == 12
    assert set(frame["metric"]) == {"news_heat"}
    assert set(frame["status"]) == {"source_error"}


def test_source_error_frame_expands_multiple_metrics():
    metrics = ["market_return_4w", "market_volume_change_4w"]

    frame = _source_error_frame(metrics, "market")

    assert len(frame) == 24
    assert set(frame["metric"]) == set(metrics)
    assert frame.groupby(["industry", "metric"]).size().eq(1).all()
    assert set(frame["status"]) == {"source_error"}


def test_run_collector_writes_source_errors_for_multiple_metrics(tmp_path):
    output = tmp_path / "collector.csv"

    def crash():
        raise RuntimeError("collector failed")

    frame = _run_collector(
        "market",
        ["market_return_4w", "market_volume_change_4w"],
        output,
        crash,
        logging.getLogger("test_pipeline"),
    )

    assert output.exists()
    assert len(frame) == 24
    assert set(frame["metric"]) == {
        "market_return_4w",
        "market_volume_change_4w",
    }
    assert set(frame["status"]) == {"source_error"}


def test_offline_pipeline_generates_all_outputs(tmp_path):
    outputs = run_pipeline(offline=True, project_root=tmp_path)

    assert outputs["score"].exists()
    assert outputs["report"].exists()
    assert outputs["chart"].exists()
    assert outputs["long_table"].exists()
    assert outputs["log"].exists()
