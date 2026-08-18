"""Sentinel tests for secret-safe pipeline and isolated-worker diagnostics."""

from __future__ import annotations

import ast
import json
import stat
from pathlib import Path

import pytest

from praviar_pipeline.dryrun import DryRunAssertionError, assert_report_valid
from praviar_pipeline.errors import ConfigurationError
from praviar_pipeline.model_supply_chain import require_resolved_drawing_model_supply_chain
from praviar_pipeline.ocsr.workers import (
    chemsam_seg_worker,
    doc2sar_worker,
    markushgrapher_worker,
    molclassifier_worker,
    molparser_worker,
)
from praviar_pipeline.ocsr.workers.model_integrity import (
    ModelChecksumError,
    expected_model_sha256,
)
from praviar_pipeline.ocsr.workers.worker_diagnostics import safe_worker_error
from praviar_pipeline.replay import load_manifest
from praviar_pipeline.response_cache import CacheMode, ResponseCache

SENTINEL = "SECRET-token-customer-query-7e4bd0"


def _assert_secret_safe(error: BaseException, *secret_values: str) -> None:
    diagnostic = f"{error!s}\n{error!r}"
    for value in (SENTINEL, *secret_values):
        assert value not in diagnostic
    assert error.__cause__ is None
    assert error.__context__ is None


def test_response_cache_parse_error_hides_path_payload_and_context(tmp_path: Path) -> None:
    cache_dir = tmp_path / SENTINEL
    cache_dir.mkdir(mode=0o700)
    cache_path = cache_dir / ResponseCache.JSONL_FILENAME
    cache_path.write_text("{invalid-json-" + SENTINEL, encoding="utf-8")
    cache_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    with pytest.raises(ValueError) as caught:
        ResponseCache(cache_dir=cache_dir, mode=CacheMode.REPLAY)

    _assert_secret_safe(caught.value, str(tmp_path), str(cache_path))
    assert str(caught.value) == "Response cache contains invalid JSON at line 1"


@pytest.mark.parametrize("payload", ["{invalid-" + SENTINEL, json.dumps({"secret": SENTINEL})])
def test_replay_manifest_errors_hide_path_payload_and_context(
    tmp_path: Path,
    payload: str,
) -> None:
    path = tmp_path / f"{SENTINEL}.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError) as caught:
        load_manifest(path)

    _assert_secret_safe(caught.value, str(tmp_path), str(path))


def test_model_supply_chain_parse_error_hides_path_payload_and_context(tmp_path: Path) -> None:
    path = tmp_path / f"{SENTINEL}.json"
    path.write_text("{invalid-" + SENTINEL, encoding="utf-8")

    with pytest.raises(ConfigurationError) as caught:
        require_resolved_drawing_model_supply_chain(path)

    _assert_secret_safe(caught.value, str(tmp_path), str(path))
    assert str(caught.value) == "Cannot read drawing ML-BOM manifest (JSONDecodeError)"


def test_worker_model_manifest_error_hides_path_payload_and_context(tmp_path: Path) -> None:
    path = tmp_path / f"{SENTINEL}.json"
    path.write_text("{invalid-" + SENTINEL, encoding="utf-8")

    with pytest.raises(ModelChecksumError) as caught:
        expected_model_sha256("test/model", manifest_path=path)

    _assert_secret_safe(caught.value, str(tmp_path), str(path))
    assert str(caught.value) == "cannot read ML-BOM manifest"


def test_dryrun_serialization_error_hides_exception_text_and_context() -> None:
    class SecretString:
        def __str__(self) -> str:
            raise ValueError(SENTINEL)

    with pytest.raises(DryRunAssertionError) as caught:
        assert_report_valid({"payload": SecretString()})

    _assert_secret_safe(caught.value)
    assert "ValueError" in str(caught.value)


def test_worker_error_helper_exposes_only_exception_type() -> None:
    error = RuntimeError(SENTINEL)
    diagnostic = safe_worker_error("Inference", error)
    assert diagnostic == "Inference failed (RuntimeError)"
    assert SENTINEL not in diagnostic


def test_representative_worker_json_errors_hide_secret_text_and_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_path = str(tmp_path / SENTINEL)

    monkeypatch.setattr(
        chemsam_seg_worker,
        "_load_predictor",
        lambda: (_ for _ in ()).throw(RuntimeError(SENTINEL)),
    )
    chemsam_error = chemsam_seg_worker.segment(secret_path, str(tmp_path / "output"))[0]["error"]
    markush_error = markushgrapher_worker.predict(secret_path)["error"]
    doc2sar_error = doc2sar_worker._base_error(RuntimeError(SENTINEL), 0, "Inference")["error"]
    molparser_error = molparser_worker._base_error(RuntimeError(SENTINEL), 0, "Inference")["error"]

    for diagnostic in (
        chemsam_error,
        markush_error,
        doc2sar_error,
        molparser_error,
    ):
        assert SENTINEL not in diagnostic
        assert secret_path not in diagnostic
        assert "RuntimeError" in diagnostic or "FileNotFoundError" in diagnostic


def test_molclassifier_env_parse_error_hides_raw_value_and_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MOLCLASSIFIER_BOX_THRESH", SENTINEL)

    with pytest.raises(RuntimeError) as caught:
        molclassifier_worker._required_float_env("MOLCLASSIFIER_BOX_THRESH")

    _assert_secret_safe(caught.value)
    assert str(caught.value) == "MOLCLASSIFIER_BOX_THRESH must be a valid float"


def test_governed_files_do_not_format_or_chain_caught_exceptions() -> None:
    source_root = Path(__file__).parents[1] / "src" / "praviar_pipeline"
    governed = [
        source_root / "response_cache.py",
        source_root / "replay.py",
        source_root / "cli_replay.py",
        source_root / "cli_validate.py",
        source_root / "cli_bigquery.py",
        source_root / "model_supply_chain.py",
        source_root / "dryrun.py",
        source_root / "pipeline" / "runtime" / "cli_runner.py",
        *sorted((source_root / "ocsr" / "workers").glob("*.py")),
    ]
    violations: list[str] = []
    for path in governed:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for handler in (node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler)):
            if not handler.name:
                continue
            for node in ast.walk(handler):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in {"str", "repr"}
                    and any(
                        isinstance(argument, ast.Name) and argument.id == handler.name
                        for argument in node.args
                    )
                ):
                    violations.append(f"{path.name}:{node.lineno}: raw exception conversion")
                if (
                    isinstance(node, ast.FormattedValue)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == handler.name
                ):
                    violations.append(f"{path.name}:{node.lineno}: raw exception formatting")
                if (
                    isinstance(node, ast.Raise)
                    and isinstance(node.cause, ast.Name)
                    and node.cause.id == handler.name
                ):
                    violations.append(f"{path.name}:{node.lineno}: exception chaining")
    assert violations == []
