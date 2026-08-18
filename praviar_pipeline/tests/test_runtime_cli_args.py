from __future__ import annotations

import pytest

from praviar_pipeline.pipeline.runtime.cli_args import (
    emit_json_report,
    parse_run_args,
    print_usage,
)


def test_parse_run_args_extracts_standard_flags():
    parsed = parse_run_args(
        [
            "aspirin",
            "--format",
            "Markdown",
            "--resume",
            "/tmp/checkpoints",
        ]
    )

    assert parsed.user_input == "aspirin"
    assert parsed.output_format == "markdown"
    assert parsed.resume_from == "/tmp/checkpoints"
    assert parsed.reanalyze_dir is None


def test_parse_run_args_rejects_depth_flag():
    with pytest.raises(ValueError, match="--depth was removed"):
        parse_run_args(["aspirin", "--depth", "Deep"])


def test_parse_run_args_rejects_depth_equals_flag():
    with pytest.raises(ValueError, match="--depth was removed"):
        parse_run_args(["aspirin", "--depth=deep"])


def test_parse_run_args_rejects_legacy_mode_flag():
    with pytest.raises(ValueError, match="--mode was removed"):
        parse_run_args(["aspirin", "--mode", "lite"])


def test_parse_run_args_rejects_legacy_mode_equals_flag():
    with pytest.raises(ValueError, match="--mode was removed"):
        parse_run_args(["aspirin", "--mode=lite"])


def test_parse_run_args_extracts_reanalysis_flag():
    parsed = parse_run_args(
        [
            "--reanalyze",
            "/tmp/retry",
            "--format",
            "json",
        ]
    )

    assert parsed.user_input == ""
    assert parsed.reanalyze_dir == "/tmp/retry"
    assert parsed.output_format == "json"


def test_emit_json_report_supports_optional_banner(capsys):
    emit_json_report({"compound": {"name": "aspirin"}}, banner=True)
    output = capsys.readouterr().out

    assert "FTO ANALYSIS REPORT" in output
    assert '"name": "aspirin"' in output


def test_print_usage_emits_canonical_praviar_pipeline_command(capsys):
    print_usage()
    output = capsys.readouterr().out

    assert "praviar-pipeline run <compound>" in output
    assert "python -m praviar_pipeline.run" not in output
