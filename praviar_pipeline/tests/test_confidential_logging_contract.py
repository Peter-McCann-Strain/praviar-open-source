"""Structural guardrails for confidential pipeline telemetry."""

from __future__ import annotations

import ast
from pathlib import Path

_LOGGER_METHODS = {"debug", "info", "warning", "error", "exception", "critical"}
_LOGGER_NAMES = {
    "_gate_log",
    "_log",
    "_logger",
    "bound_logger",
    "log",
    "logger",
}
_CONFIDENTIAL_FIELDS = {
    "app_number",
    "applicant",
    "before",
    "cid",
    "claim",
    "claim_number",
    "claim_numbers",
    "context",
    "drug_name",
    "family_id",
    "functional_groups",
    "image_path",
    "inchi",
    "issues",
    "name",
    "paper_id",
    "parent",
    "path",
    "patent_id",
    "patent_number",
    "proceeding_number",
    "query",
    "query_primary",
    "smarts",
    "smiles",
    "suggestion_preview",
    "title",
    "url",
    "user_input",
}


def _is_logger_call(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute) or node.func.attr not in _LOGGER_METHODS:
        return False
    receiver = node.func.value
    if isinstance(receiver, ast.Name):
        return receiver.id in _LOGGER_NAMES
    if isinstance(receiver, ast.Attribute):
        return receiver.attr in _LOGGER_NAMES
    return (
        isinstance(receiver, ast.Call)
        and isinstance(receiver.func, ast.Attribute)
        and receiver.func.attr in {"getLogger", "get_logger"}
    )


def test_logger_calls_exclude_confidential_fields_and_tracebacks() -> None:
    source_root = Path(__file__).parents[1] / "src" / "praviar_pipeline"
    violations: list[str] = []

    for source_path in source_root.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _is_logger_call(node):
                continue
            if isinstance(node.func, ast.Attribute) and node.func.attr == "exception":
                violations.append(
                    f"{source_path.relative_to(source_root)}:{node.lineno}:implicit_traceback"
                )
            for argument in node.args[1:]:
                if isinstance(argument, ast.Name) and argument.id in {"e", "err", "error", "exc"}:
                    violations.append(
                        f"{source_path.relative_to(source_root)}:{node.lineno}:raw_exception_arg"
                    )
                if (
                    isinstance(argument, ast.Call)
                    and isinstance(argument.func, ast.Name)
                    and argument.func.id == "str"
                ):
                    violations.append(
                        f"{source_path.relative_to(source_root)}:{node.lineno}:raw_dynamic_text_arg"
                    )
            for keyword in node.keywords:
                if keyword.arg in _CONFIDENTIAL_FIELDS or keyword.arg == "exc_info":
                    violations.append(
                        f"{source_path.relative_to(source_root)}:{node.lineno}:{keyword.arg}"
                    )
                if (
                    keyword.arg in {"error", "reason", "detail", "message"}
                    and isinstance(keyword.value, ast.Call)
                    and isinstance(keyword.value.func, ast.Name)
                    and keyword.value.func.id == "str"
                ):
                    violations.append(
                        f"{source_path.relative_to(source_root)}:{node.lineno}:raw_exception_text"
                    )

    assert violations == []
