from __future__ import annotations

from unittest.mock import MagicMock

import praviar_pipeline.cli as cli
from praviar_pipeline.cli_patcid import main as patcid_main
from praviar_pipeline.cli_validate import PASS, check_prompts


def test_cli_dispatches_run(monkeypatch):
    run_main = MagicMock()
    monkeypatch.setattr(cli, "run_main", run_main)

    exit_code = cli.main(["run", "aspirin"])

    assert exit_code == 0
    run_main.assert_called_once()


def test_cli_dispatches_validate(monkeypatch):
    validate_main = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "validate_main", validate_main)

    exit_code = cli.main(["validate"])

    assert exit_code == 0
    validate_main.assert_called_once_with([])


def test_cli_dispatches_bigquery_check(monkeypatch):
    bigquery_main = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "check_bigquery_main", bigquery_main)

    exit_code = cli.main(["check-bigquery"])

    assert exit_code == 0
    bigquery_main.assert_called_once_with([])


def test_cli_dispatches_patcid_index(monkeypatch):
    patcid_main = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "index_patcid_main", patcid_main)

    exit_code = cli.main(["index-patcid", "data/patcid_dump.jsonl"])

    assert exit_code == 0
    patcid_main.assert_called_once_with(["data/patcid_dump.jsonl"])


def test_cli_dispatches_models(monkeypatch):
    models_main = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "models_main", models_main)

    exit_code = cli.main(["models", "list", "--json"])

    assert exit_code == 0
    models_main.assert_called_once_with(["list", "--json"])


def test_cli_validate_prompt_check_uses_packaged_prompt_dir():
    statuses = {name: status for status, name, _detail in check_prompts()}

    assert statuses["triage_system.txt"] == PASS
    assert statuses["claim_analysis_system.txt"] == PASS
    assert statuses["report_summary_system.txt"] == PASS


def test_patcid_cli_returns_error_code_for_missing_args(capsys):
    exit_code = patcid_main([])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "praviar-pipeline index-patcid" in captured.out
