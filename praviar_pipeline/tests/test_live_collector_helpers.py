from __future__ import annotations

from types import SimpleNamespace

import pytest

from praviar_pipeline.models.report import SourceHealth
from praviar_pipeline.models.report_common import SourceHealthEntry, SourceStatus
from praviar_pipeline.pipeline.runtime.live_collector_context import (
    collect_counting_enrichment_runtime,
    collect_uspto_odp_runtime_context_impl,
)
from praviar_pipeline.pipeline.runtime.live_collector_helpers import (
    directive_targets_by_adapter,
    merge_source_health_entries,
)
from praviar_pipeline.pipeline.search.enrichment import EnrichmentOutcome


def test_directive_targets_by_adapter_dedupes_targets_and_skips_empty_directives() -> None:
    directives = [
        SimpleNamespace(
            target_patent_ids=["US1", "US1"],
            recommended_adapters=["ptab", "orange_book"],
        ),
        SimpleNamespace(
            target_patent_ids=[],
            recommended_adapters=["epo_register"],
        ),
        SimpleNamespace(
            target_patent_ids=["EP1"],
            recommended_adapters=["epo_register"],
        ),
    ]

    assert directive_targets_by_adapter(directives) == {
        "ptab": ["US1"],
        "orange_book": ["US1"],
        "epo_register": ["EP1"],
    }


def test_merge_source_health_entries_replaces_existing_sources_in_place() -> None:
    existing = SourceHealth(
        entries=[
            SourceHealthEntry(
                source="ptab",
                status=SourceStatus.SKIPPED,
                patent_count=0,
                error_message="missing key",
            )
        ]
    )
    updates = [
        SourceHealthEntry(
            source="ptab",
            status=SourceStatus.OK,
            patent_count=2,
            error_message="",
        ),
        SourceHealthEntry(
            source="epo_register",
            status=SourceStatus.OK,
            patent_count=1,
            error_message="",
        ),
    ]

    merged = merge_source_health_entries(existing, updates)

    assert [entry.source for entry in merged.entries] == ["ptab", "epo_register"]
    assert merged.entries[0].status == SourceStatus.OK
    assert merged.entries[0].patent_count == 2


@pytest.mark.asyncio
async def test_collect_counting_enrichment_runtime_marks_failures() -> None:
    async def failing_collector(_hits) -> int:
        raise RuntimeError("collector-failed")

    entry = await collect_counting_enrichment_runtime(
        source="ptab",
        patent_hits=[SimpleNamespace(patent_id="US1")],
        collector_fn=failing_collector,
    )

    assert entry.status == SourceStatus.FAILED
    assert entry.error_message == "live collector failed (RuntimeError)"


@pytest.mark.asyncio
async def test_collect_counting_enrichment_runtime_rejects_bare_zero_count() -> None:
    async def ambiguous_collector(_hits) -> int:
        return 0

    entry = await collect_counting_enrichment_runtime(
        source="ptab",
        patent_hits=[SimpleNamespace(patent_id="US1")],
        collector_fn=ambiguous_collector,
    )

    assert entry.status == SourceStatus.FAILED
    assert entry.attempted_count == 1
    assert entry.covered_count == 0


@pytest.mark.asyncio
async def test_collect_counting_enrichment_runtime_distinguishes_covered_zero() -> None:
    async def covered_negative(_hits) -> EnrichmentOutcome:
        return EnrichmentOutcome(attempted_count=1, covered_count=1, evidence_count=0)

    entry = await collect_counting_enrichment_runtime(
        source="ptab",
        patent_hits=[SimpleNamespace(patent_id="US1")],
        collector_fn=covered_negative,
    )

    assert entry.status == SourceStatus.OK
    assert entry.patent_count == 0
    assert entry.attempted_count == 1
    assert entry.covered_count == 1


@pytest.mark.asyncio
async def test_collect_counting_enrichment_runtime_marks_partial_coverage_failed() -> None:
    async def partial_collector(_hits) -> EnrichmentOutcome:
        return EnrichmentOutcome(attempted_count=2, covered_count=1, evidence_count=1)

    entry = await collect_counting_enrichment_runtime(
        source="ptab",
        patent_hits=[
            SimpleNamespace(patent_id="US1"),
            SimpleNamespace(patent_id="US2"),
        ],
        collector_fn=partial_collector,
    )

    assert entry.status == SourceStatus.FAILED
    assert entry.patent_count == 1
    assert entry.attempted_count == 2
    assert entry.covered_count == 1


@pytest.mark.asyncio
async def test_collect_uspto_odp_runtime_context_marks_partial_coverage_failed() -> None:
    async def fake_fetch(patent_id: str) -> dict[str, object]:
        if patent_id == "US2":
            raise RuntimeError("timeout")
        return {"sections_available": ["us_file_wrapper_dossier"]}

    entry, cache = await collect_uspto_odp_runtime_context_impl(
        patent_ids=["US1", "US2"],
        prosecution_cache={"US1": {"sections_available": ["us_file_wrapper_dossier"]}},
        fetch_prosecution_context_fn=fake_fetch,
    )

    assert entry.status == SourceStatus.FAILED
    assert entry.patent_count == 1
    assert entry.attempted_count == 2
    assert entry.covered_count == 1
    assert entry.error_message == "live collector failed (RuntimeError)"
    assert "US1" in cache
    assert "US2" not in cache
