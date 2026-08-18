"""Fail-closed sanitization for customer- and model-visible output."""

from __future__ import annotations

import enum
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict

SAFE_PROVIDER_FAILURE_DETAIL = (
    "Provider request failed; protected diagnostics are available to operators."
)
SAFE_PROVIDER_NOT_CONFIGURED_DETAIL = "Provider was not configured for this run."
SAFE_PROVIDER_SKIPPED_DETAIL = "Provider was skipped for this run."
SAFE_PROCESSING_FAILURE_DETAIL = (
    "Processing failed; protected diagnostics are available to operators."
)
DIAGNOSTIC_SANITIZER_SCHEMA_VERSION: Final[Literal["diagnostic-sanitizer-v1"]] = (
    "diagnostic-sanitizer-v1"
)


class DiagnosticClassification(enum.StrEnum):
    """Public-output handling assigned to a protected diagnostic field."""

    SOURCE = "source"
    PROCESSING = "processing"


class DiagnosticFieldRule(BaseModel):
    """Typed location and handling contract for one protected value."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: tuple[str, ...]
    classification: DiagnosticClassification


class DiagnosticSanitizerSchema(BaseModel):
    """Versioned explicit diagnostic field schema; no key-name inference."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["diagnostic-sanitizer-v1"] = DIAGNOSTIC_SANITIZER_SCHEMA_VERSION
    fields: tuple[DiagnosticFieldRule, ...]


REPORT_DIAGNOSTIC_SANITIZER_SCHEMA = DiagnosticSanitizerSchema(
    fields=(
        DiagnosticFieldRule(
            path=("source_health", "entries", "*", "error_message"),
            classification=DiagnosticClassification.SOURCE,
        ),
        DiagnosticFieldRule(
            path=("analysis_failures", "*", "error_message"),
            classification=DiagnosticClassification.PROCESSING,
        ),
    )
)


def safe_source_error_detail(error_message: object, *, status: object = "") -> str:
    """Return a stable source-health explanation without echoing diagnostics."""
    if not str(error_message or "").strip():
        return ""

    normalized_status = str(getattr(status, "value", status) or "").strip().lower()
    if normalized_status == "not_configured":
        return SAFE_PROVIDER_NOT_CONFIGURED_DETAIL
    if normalized_status == "skipped":
        return SAFE_PROVIDER_SKIPPED_DETAIL
    return SAFE_PROVIDER_FAILURE_DETAIL


def safe_processing_error_detail(error_message: object) -> str:
    """Return a stable processing failure without exposing exception text."""
    if not str(error_message or "").strip():
        return ""
    return SAFE_PROCESSING_FAILURE_DETAIL


def _replace_diagnostic_at_path(
    value: Any,
    path: tuple[str, ...],
    classification: DiagnosticClassification,
) -> None:
    if not path:
        return
    token, *remainder = path
    remaining = tuple(remainder)
    if token == "*":
        if isinstance(value, list):
            for item in value:
                _replace_diagnostic_at_path(item, remaining, classification)
        elif isinstance(value, Mapping):
            for item in value.values():
                _replace_diagnostic_at_path(item, remaining, classification)
        return
    if not isinstance(value, dict) or token not in value:
        return
    if remaining:
        _replace_diagnostic_at_path(value[token], remaining, classification)
        return
    raw = value[token]
    if classification == DiagnosticClassification.SOURCE:
        value[token] = safe_source_error_detail(raw, status=value.get("status", ""))
    else:
        value[token] = safe_processing_error_detail(raw)


def sanitize_error_fields_for_output(
    value: Any,
    *,
    schema: DiagnosticSanitizerSchema = REPORT_DIAGNOSTIC_SANITIZER_SCHEMA,
) -> Any:
    """Sanitize only fields explicitly typed as protected diagnostics.

    Field names such as ``detail`` or ``url`` have no intrinsic safety meaning.
    Provider integrations must classify their diagnostic locations in a schema;
    unreviewed fields are never silently guessed from their names.
    """
    sanitized = deepcopy(value)
    for field in schema.fields:
        _replace_diagnostic_at_path(sanitized, field.path, field.classification)
    return sanitized
