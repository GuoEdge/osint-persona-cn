"""Pipeline 测试."""

import json

from osint_toolkit.pipeline.context import RunContext
from osint_toolkit.pipeline.runner import PipelineRunner


def test_pipeline_runner_records_steps(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.pipeline.context.get_data_dir", lambda: tmp_path)
    ctx = RunContext(command="test", query="hello", trace=True)
    runner = PipelineRunner(ctx)
    runner.run_step("demo", lambda: [1, 2, 3], input_summary="x")
    assert len(runner.steps) == 1
    assert (ctx.ensure_run_dir() / "trace.log").exists()


def test_pipeline_runner_keeps_step_and_artifact_separate(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.pipeline.context.get_data_dir", lambda: tmp_path)
    ctx = RunContext(command="test", query="hello", trace=True)
    runner = PipelineRunner(ctx)

    runner.run_step("demo", lambda: [{"title": "a"}], artifact_name="items_demo.json")

    run_dir = ctx.ensure_run_dir()
    step_payload = json.loads((run_dir / "01_demo.json").read_text(encoding="utf-8"))
    artifact_payload = json.loads((run_dir / "items_demo.json").read_text(encoding="utf-8"))
    assert step_payload["step"] == "demo"
    assert step_payload["artifacts"] == ["items_demo.json"]
    assert artifact_payload == [{"title": "a"}]
