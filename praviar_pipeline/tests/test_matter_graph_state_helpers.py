from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.models.report import EvidenceArtifact, EvidenceArtifactType, SourceHealth
from praviar_pipeline.pipeline.runtime.matter_graph_snapshot import (
    enrich_runtime_coverage_context,
    extend_with_live_patent_hit_artifacts,
    normalize_source_health,
)


def test_normalize_source_health_accepts_mapping() -> None:
    source_health = normalize_source_health({"entries": []})

    assert isinstance(source_health, SourceHealth)
    assert source_health.entries == []


def test_enrich_runtime_coverage_context_uses_patent_hits_when_analyses_missing() -> None:
    coverage_context = SimpleNamespace(us_patents=0, ep_patents=0)

    enrich_runtime_coverage_context(
        coverage_context,
        analyses=[],
        patent_hits=[
            SimpleNamespace(jurisdiction="US"),
            SimpleNamespace(jurisdiction="EP"),
            SimpleNamespace(jurisdiction="US"),
        ],
    )

    assert coverage_context.us_patents == 2
    assert coverage_context.ep_patents == 1


def test_extend_with_live_patent_hit_artifacts_dedupes_existing_search_hit() -> None:
    existing = [
        EvidenceArtifact(
            artifact_id="US123:search_hit",
            artifact_type=EvidenceArtifactType.SEARCH_HIT,
            source_name="patentsview",
            patent_id="US123",
        )
    ]

    extended = extend_with_live_patent_hit_artifacts(
        existing,
        patent_hits=[
            SimpleNamespace(
                patent_id="US123",
                jurisdiction="US",
                family=SimpleNamespace(family_id="fam-1"),
                sources=[SimpleNamespace(value="patentsview")],
                claims_text="Claim 1",
                ptab_proceedings=[],
                orange_book_listed=False,
            )
        ],
        prosecution_cache={},
    )

    search_hits = [
        artifact
        for artifact in extended
        if artifact.artifact_type == EvidenceArtifactType.SEARCH_HIT
    ]
    assert len(search_hits) == 1
