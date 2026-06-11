from scripts.fetch_policy import collect_policy


def test_collect_policy_offline_marks_sample(tmp_path):
    output = tmp_path / "policy.csv"

    frame = collect_policy(offline=True, output_path=output)

    assert output.exists()
    assert set(frame["metric"]) == {"policy_heat"}
    assert set(frame["status"]) == {"sample"}
    assert len(frame) == 12


def test_policy_source_failure_falls_back_without_raising(tmp_path):
    output = tmp_path / "policy.csv"

    frame = collect_policy(
        offline=False,
        fallback_samples=True,
        output_path=output,
        sources=[
            {
                "name": "broken",
                "url": "http://127.0.0.1:1",
                "type": "rss",
            }
        ],
    )

    assert not frame.empty
    assert set(frame["status"]) == {"sample"}
