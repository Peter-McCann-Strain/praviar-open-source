"""Validator helpers for Praviar Pipeline settings."""

from __future__ import annotations

import re

from praviar_pipeline.errors import ConfigurationError

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_BIGQUERY_PROJECT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_BIGQUERY_DATASET_OR_TABLE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,1023}$")


def normalize_policy_string(value: str) -> str:
    """Normalize a policy enum-like string field."""
    return str(value).strip().lower()


def normalize_required_record_components(value: list[str] | str | None) -> list[str]:
    """Normalize required record components from env or direct input."""
    if value is None or value == "":
        return []
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",") if part.strip()]

    normalized: list[str] = []
    seen: set[str] = set()
    for component in value:
        cleaned = str(component).strip().lower()
        if not cleaned or cleaned in seen:
            continue
        normalized.append(cleaned)
        seen.add(cleaned)
    return normalized


def validate_log_level(value: str) -> str:
    """Normalize and validate the configured log level."""
    normalized = str(value).strip().upper()
    if normalized not in _VALID_LOG_LEVELS:
        raise ValueError(
            f"Invalid log_level '{normalized}'. Must be one of: "
            f"{', '.join(sorted(_VALID_LOG_LEVELS))}"
        )
    return normalized


def check_api_keys(settings):
    """Validate required API keys and log availability of optional sources."""
    import structlog

    _log = structlog.get_logger()

    if not settings.anthropic_api_key:
        raise ConfigurationError(
            "Missing API key: anthropic_api_key. Set it in .env or environment variables.",
        )

    optional_keys = {
        "patentsview_api_key": settings.patentsview_api_key,
        "uspto_odp_api_key": settings.uspto_odp_api_key,
        "ops_consumer_key": settings.ops_consumer_key,
        "kipris_api_key": settings.kipris_api_key,
        "tavily_api_key": settings.tavily_api_key,
    }
    available = [key for key, candidate in optional_keys.items() if candidate]
    unavailable = [key for key, candidate in optional_keys.items() if not candidate]
    if available:
        _log.info("api_keys_configured", keys=available)
    if unavailable:
        _log.warning("api_keys_missing", keys=unavailable, status="sources_disabled")

    return settings


def validate_hybrid_retrieval_settings(settings):
    """Fail settings construction when hybrid retrieval prerequisites conflict."""
    if not settings.hybrid_retrieval_enabled:
        return settings
    if not settings.search_enable_bigquery:
        raise ValueError(
            "search_enable_bigquery must be true when hybrid_retrieval_enabled is true"
        )
    if _BIGQUERY_PROJECT_PATTERN.fullmatch(settings.bigquery_project_id) is None:
        raise ValueError(
            "bigquery_project_id must be a valid non-empty project identifier "
            "when hybrid_retrieval_enabled is true"
        )
    if _BIGQUERY_DATASET_OR_TABLE_PATTERN.fullmatch(settings.bigquery_dataset) is None:
        raise ValueError(
            "bigquery_dataset must be a valid dataset identifier "
            "when hybrid_retrieval_enabled is true"
        )
    if _BIGQUERY_DATASET_OR_TABLE_PATTERN.fullmatch(settings.bigquery_table) is None:
        raise ValueError(
            "bigquery_table must be a valid table identifier when hybrid_retrieval_enabled is true"
        )
    return settings
