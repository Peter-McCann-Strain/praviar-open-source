from __future__ import annotations

from types import SimpleNamespace

import pytest

from praviar_pipeline.pipeline.runtime.cli_runner import reanalyze_failed_impl, run_cli


def test_run_cli_prints_usage_and_returns_1() -> None:
    printed = []

    exit_code = run_cli(
        ["praviar_pipeline"],
        parse_run_args_fn=lambda _args: None,
        print_usage_fn=lambda: printed.append("usage"),
        configure_logging_fn=lambda: None,
        reanalyze_failed_fn=lambda *_args, **_kwargs: None,
        run_pipeline_fn=lambda *_args, **_kwargs: None,
        sync_to_database_fn=lambda *_args, **_kwargs: None,
        emit_json_report_fn=lambda *_args, **_kwargs: None,
    )

    assert exit_code == 1
    assert printed == ["usage"]


def test_run_cli_runs_standard_pipeline() -> None:
    configured = []
    synced = []
    emitted = []

    async def fake_pipeline(user_input: str, **kwargs) -> dict:
        assert user_input == "aspirin"
        assert kwargs["output_format"] == "json"
        return {"compound": {"name": "aspirin"}}

    exit_code = run_cli(
        ["praviar_pipeline", "aspirin"],
        parse_run_args_fn=lambda _args: SimpleNamespace(
            user_input="aspirin",
            output_format="json",
            resume_from=None,
            reanalyze_dir=None,
        ),
        print_usage_fn=lambda: None,
        configure_logging_fn=lambda: configured.append(True),
        reanalyze_failed_fn=lambda *_args, **_kwargs: None,
        run_pipeline_fn=fake_pipeline,
        sync_to_database_fn=lambda result, user_input, duration: synced.append(
            (result, user_input, duration >= 0.0)
        ),
        emit_json_report_fn=lambda result, banner: emitted.append((result, banner)),
    )

    assert exit_code == 0
    assert configured == [True]
    assert synced[0][1] == "aspirin"
    assert synced[0][2] is True
    assert emitted == [({"compound": {"name": "aspirin"}}, True)]


def test_run_cli_runs_reanalysis_path() -> None:
    configured = []
    synced = []
    emitted = []

    async def fake_reanalyze(_path):
        return {"compound": {"name": "retry"}}

    exit_code = run_cli(
        ["praviar_pipeline", "--reanalyze", "/tmp/run"],
        parse_run_args_fn=lambda _args: SimpleNamespace(
            user_input=None,
            output_format="json",
            resume_from=None,
            reanalyze_dir="/tmp/run",
        ),
        print_usage_fn=lambda: None,
        configure_logging_fn=lambda: configured.append(True),
        reanalyze_failed_fn=fake_reanalyze,
        run_pipeline_fn=lambda *_args, **_kwargs: None,
        sync_to_database_fn=lambda result, user_input, duration: synced.append(
            (result, user_input, duration)
        ),
        emit_json_report_fn=lambda result, banner: emitted.append((result, banner)),
    )

    assert exit_code == 0
    assert configured == [True]
    assert synced == [({"compound": {"name": "retry"}}, "retry", 0.0)]
    assert emitted == [({"compound": {"name": "retry"}}, False)]


@pytest.mark.asyncio
async def test_reanalyze_failed_impl_retries_failed_patents() -> None:
    context = SimpleNamespace(
        patent_hits=["hit-1", "hit-2"],
        analysis_failures=["failure-1"],
        compound="compound",
        triage_results=["triage"],
        analyses=["old-analysis"],
        checkpoint=SimpleNamespace(compound_input="aspirin"),
        checkpoint_integrity_keys="test-keys",
        state="state",
    )
    checkpoint_writes = []

    async def fake_analyze_patents(retry_patents, compound, triage_results):
        assert retry_patents == ["hit-1"]
        assert compound == "compound"
        assert triage_results == ["triage"]
        return ["new-analysis"], ["new-failure"], []

    async def fake_run_pipeline(*, user_input: str, resume_from: str) -> dict:
        return {"compound": {"name": user_input}, "resume_from": resume_from}

    result = await reanalyze_failed_impl(
        "/tmp/ckpt",
        load_reanalysis_context_fn=lambda _path, *, integrity_keys: context,
        select_failed_patents_fn=lambda patent_hits, analysis_failures: ({"hit-1"}, ["hit-1"]),
        analyze_patents_fn=fake_analyze_patents,
        merge_reanalysis_results_fn=lambda *_args: (["merged-analysis"], ["merged-failure"]),
        write_reanalysis_checkpoint_fn=lambda **kwargs: checkpoint_writes.append(kwargs),
        run_pipeline_fn=fake_run_pipeline,
        logger=SimpleNamespace(info=lambda *args, **kwargs: None),
        checkpoint_integrity_keys="test-keys",
    )

    assert checkpoint_writes[0]["checkpoint_dir_path"] == "/tmp/ckpt"
    assert checkpoint_writes[0]["merged_analyses"] == ["merged-analysis"]
    assert result == {
        "compound": {"name": "aspirin"},
        "resume_from": "/tmp/ckpt",
    }
