"""Tests for SG-112: report data-sufficiency gate.

Verifies that `_validate_data_sufficiency` refuses to render when too many
sources failed, not just when all sources failed.
"""

from __future__ import annotations

import pytest

from praviar_pipeline.errors import InsufficientDataError
from praviar_pipeline.models.report import SourceHealth, SourceHealthEntry, SourceStatus
from praviar_pipeline.pipeline.report.policy import (
    SOURCE_FAILURE_ABORT_THRESHOLD,
    _validate_data_sufficiency,
)


def _entry(source: str, status: SourceStatus, count: int = 0, error: str = "") -> SourceHealthEntry:
    return SourceHealthEntry(
        source=source,
        status=status,
        patent_count=count,
        error_message=error,
    )


def test_all_ok_passes() -> None:
    health = SourceHealth(
        entries=[
            _entry("pubchem", SourceStatus.OK, count=5),
            _entry("lens", SourceStatus.OK, count=3),
            _entry("surechembl", SourceStatus.OK, count=8),
        ]
    )
    _validate_data_sufficiency(health)


def test_all_failed_raises() -> None:
    health = SourceHealth(
        entries=[
            _entry("pubchem", SourceStatus.FAILED, error="timeout"),
            _entry("lens", SourceStatus.FAILED, error="500"),
        ]
    )
    with pytest.raises(InsufficientDataError, match="All search sources failed"):
        _validate_data_sufficiency(health)


def test_below_threshold_passes() -> None:
    # 1 failed out of 5 queried (20% < 40%) — continue with degraded confidence.
    health = SourceHealth(
        entries=[
            _entry("pubchem", SourceStatus.OK, count=5),
            _entry("lens", SourceStatus.OK, count=3),
            _entry("surechembl", SourceStatus.OK, count=8),
            _entry("bigquery", SourceStatus.OK, count=2),
            _entry("epo_ops", SourceStatus.FAILED, error="timeout"),
        ]
    )
    _validate_data_sufficiency(health)


def test_regulatory_source_failures_do_not_count_toward_search_failure_ratio() -> None:
    health = SourceHealth(
        entries=[
            _entry("pubchem", SourceStatus.OK, count=5),
            _entry("lens", SourceStatus.OK, count=3),
            _entry("pte_data", SourceStatus.FAILED, error="unavailable"),
            _entry("paragraph_iv", SourceStatus.NOT_CONFIGURED, error="missing pdf url"),
            _entry("orange_book", SourceStatus.FAILED, error="unavailable"),
        ]
    )

    _validate_data_sufficiency(health)


def test_at_threshold_raises() -> None:
    # 3 failed out of 5 queried = 60% — must raise (>= threshold).
    health = SourceHealth(
        entries=[
            _entry("pubchem", SourceStatus.OK, count=5),
            _entry("lens", SourceStatus.OK, count=3),
            _entry("surechembl", SourceStatus.FAILED, error="500"),
            _entry("bigquery", SourceStatus.FAILED, error="quota"),
            _entry("epo_ops", SourceStatus.FAILED, error="timeout"),
        ]
    )
    with pytest.raises(InsufficientDataError, match="Too many search sources failed"):
        _validate_data_sufficiency(health)


def test_above_threshold_raises() -> None:
    # 4 failed out of 5 queried (80% > 60%) — raises.
    health = SourceHealth(
        entries=[
            _entry("pubchem", SourceStatus.OK, count=5),
            _entry("lens", SourceStatus.FAILED, error="500"),
            _entry("surechembl", SourceStatus.FAILED, error="500"),
            _entry("bigquery", SourceStatus.FAILED, error="quota"),
            _entry("epo_ops", SourceStatus.FAILED, error="timeout"),
        ]
    )
    with pytest.raises(InsufficientDataError, match=r"4/5"):
        _validate_data_sufficiency(health)


def test_skipped_sources_do_not_count_in_denominator() -> None:
    # 2 failed / 3 queried = 66%; 2 skipped sources should be excluded from
    # the ratio. This matters because SKIPPED is a configuration choice
    # (missing credentials), not a failure — excluding it makes the gate
    # reflect actual source outages.
    health = SourceHealth(
        entries=[
            _entry("pubchem", SourceStatus.OK, count=5),
            _entry("lens", SourceStatus.FAILED, error="500"),
            _entry("surechembl", SourceStatus.FAILED, error="500"),
            _entry("kipris", SourceStatus.SKIPPED, error="no API key"),
            _entry("epo_ops", SourceStatus.SKIPPED, error="no credentials"),
        ]
    )
    with pytest.raises(InsufficientDataError, match=r"2/3"):
        _validate_data_sufficiency(health)


def test_all_skipped_raises_insufficient_data() -> None:
    # If every source was skipped, the report has no queried source coverage.
    health = SourceHealth(
        entries=[
            _entry("kipris", SourceStatus.SKIPPED, error="no API key"),
            _entry("epo_ops", SourceStatus.SKIPPED, error="no credentials"),
        ]
    )
    with pytest.raises(InsufficientDataError, match="No queried search sources"):
        _validate_data_sufficiency(health)


def test_empty_source_health_raises_insufficient_data() -> None:
    with pytest.raises(InsufficientDataError, match="No queried search sources"):
        _validate_data_sufficiency(SourceHealth(entries=[]))


def test_threshold_constant_is_sixty_percent() -> None:
    # Guard against accidental threshold changes — making this stricter or
    # looser is a deliberate product call, not something to flip in passing.
    # Raised from 40% to 60% to accommodate BigQuery-quota-exhausted runs
    # where BigQuery (3 sources) plus a handful of supplementary sources fail
    # while the primary search sources (PubChem SDQ, EPO OPS, PatentsView)
    # succeed and return thousands of patents.
    assert SOURCE_FAILURE_ABORT_THRESHOLD == 0.6
