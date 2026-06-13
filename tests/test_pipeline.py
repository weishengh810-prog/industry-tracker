import logging

import pandas as pd

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

    for name in ("long_table", "momentum", "score", "report", "chart", "log"):
        assert outputs[name].exists()

    raw_dir = tmp_path / "data" / "raw"
    assert {path.name for path in raw_dir.glob("*_daily.csv")} == {
        "news_daily.csv",
        "policy_daily.csv",
        "market_daily.csv",
        "arxiv_daily.csv",
        "github_daily.csv",
        "nvd_daily.csv",
    }
    long_frame = pd.read_csv(outputs["long_table"])
    assert {
        "market_return_4w",
        "market_volume_change_4w",
        "arxiv_paper_count_4w",
        "github_repo_count_4w",
        "nvd_cve_count_4w",
    }.issubset(set(long_frame["metric"]))
    scores = pd.read_csv(outputs["score"])
    assert scores["composite_score"].isna().all()
    assert set(scores["scoring_mode"]) == {"历史数据不足，暂不排名"}


def test_new_collector_crash_does_not_stop_offline_pipeline(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "scripts.run_pipeline.collect_arxiv",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    outputs = run_pipeline(offline=True, project_root=tmp_path)

    arxiv = pd.read_csv(tmp_path / "data" / "raw" / "arxiv_daily.csv")
    assert set(arxiv["status"]) == {"source_error"}
    assert outputs["momentum"].exists()
    assert outputs["score"].exists()
    assert outputs["report"].exists()
