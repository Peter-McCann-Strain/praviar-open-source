"""Shared validator helpers for analysis-related Pydantic models."""

from __future__ import annotations

from typing import overload

import structlog

from praviar_pipeline.errors import LLMResponseError

logger = structlog.get_logger()


@overload
def validate_governed_enum_value(
    value: str,
    *,
    valid_values: set[str],
    replace_spaces: bool = False,
) -> str: ...


@overload
def validate_governed_enum_value(
    value: None,
    *,
    valid_values: set[str],
    replace_spaces: bool = False,
) -> None: ...


def validate_governed_enum_value(
    value: str | None,
    *,
    valid_values: set[str],
    replace_spaces: bool = False,
) -> str | None:
    """Normalize a governed enum and reject unknown values with safe prose.

    Raising ``ValueError`` is intentional: Pydantic converts it to a
    ``ValidationError`` at the LLM-output boundary without retaining the raw,
    potentially confidential token in application exception text.
    """
    if value is None or not isinstance(value, str):
        return value
    normalized = value.strip().lower()
    if replace_spaces:
        normalized = normalized.replace(" ", "_").replace("-", "_")
    if normalized not in valid_values:
        raise ValueError("Unrecognised value for governed enum")
    return normalized


@overload
def coerce_enum_value(
    value: str,
    *,
    valid_values: set[str],
    default: str,
    log_event: str,
    normalize: bool = True,
    replace_spaces: bool = False,
    raise_on_unknown: bool = False,
) -> str: ...


@overload
def coerce_enum_value(
    value: None,
    *,
    valid_values: set[str],
    default: str,
    log_event: str,
    normalize: bool = True,
    replace_spaces: bool = False,
    raise_on_unknown: bool = False,
) -> None: ...


def coerce_enum_value(
    value: str | None,
    *,
    valid_values: set[str],
    default: str,
    log_event: str,
    normalize: bool = True,
    replace_spaces: bool = False,
    raise_on_unknown: bool = False,
) -> str | None:
    """Normalize common LLM enum drift to a supported value.

    For most enum fields a value that survives normalisation but is still
    unrecognised is coerced to ``default`` so a single rogue token does not
    drop an otherwise valid analysis. Risk-bearing fields pass
    ``raise_on_unknown=True`` instead: silently substituting a default risk
    level can make a blocking patent look non-blocking, which violates the
    "no fallbacks, fail loud" rule. In that mode an unrecognised value raises
    :class:`~praviar_pipeline.errors.LLMResponseError`.
    """
    if value is None or not isinstance(value, str):
        return value

    normalized = value.strip().lower()
    if replace_spaces:
        normalized = normalized.replace(" ", "_").replace("-", "_")
    if not normalize:
        normalized = value

    if normalized not in valid_values:
        if raise_on_unknown:
            logger.error(log_event, raise_on_unknown=True)
            raise LLMResponseError(
                "Unrecognised value for governed enum",
                step="analysis",
            )
        logger.warning(log_event, coerced_to=default)
        return default
    return normalized


def warn_missing_claim_evidence(status: object, evidence: str) -> None:
    """Log when a decisive claim-element assessment lacks supporting evidence."""
    if status == "unclear" or getattr(status, "value", status) == "unclear":
        return
    if evidence.strip():
        return

    logger.warning(
        "claim_element_missing_evidence",
        status=status.value if hasattr(status, "value") else status,
    )
