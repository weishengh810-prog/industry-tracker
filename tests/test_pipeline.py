from scripts.run_pipeline import run_pipeline


def test_offline_pipeline_generates_all_outputs(tmp_path):
    outputs = run_pipeline(offline=True, project_root=tmp_path)

    assert outputs["score"].exists()
    assert outputs["report"].exists()
    assert outputs["chart"].exists()
    assert outputs["long_table"].exists()
    assert outputs["log"].exists()
