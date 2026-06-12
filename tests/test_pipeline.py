"""Pipeline 测试."""

from osint_toolkit.pipeline.context import RunContext
from osint_toolkit.pipeline.runner import PipelineRunner


def test_pipeline_runner_records_steps(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.pipeline.context.get_data_dir", lambda: tmp_path)
    ctx = RunContext(command="test", query="hello", trace=True)
    runner = PipelineRunner(ctx)
    runner.run_step("demo", lambda: [1, 2, 3], input_summary="x")
    assert len(runner.steps) == 1
    assert (ctx.ensure_run_dir() / "trace.log").exists()
