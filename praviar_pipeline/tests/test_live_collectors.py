from __future__ import annotations

from types import SimpleNamespace

import pytest

from praviar_pipeline.errors import ConfigurationError, SourceUnavailableError
from praviar_pipeline.models.patent import PatentHit
from praviar_pipeline.models.report import (
    CollectionAttempt,
    EvidenceCollectionDirective,
    EvidenceCollectorDefinition,
    EvidenceCollectorRun,
    SourceHealth,
)
from praviar_pipeline.models.report_common import SourceHealthEntry, SourceStatus
from praviar_pipeline.models.report_evidence_artifacts import (
    EvidenceAdapterKind,
    EvidenceAuthorityTier,
    EvidenceCollectionState,
)
from praviar_pipeline.pipeline.runtime import live_collectors as module
from praviar_pipeline.pipeline.runtime.live_collectors import execute_live_evidence_collectors
from praviar_pipeline.pipeline.search.enrichment import EnrichmentOutcome


def _hit(patent_id: str) -> PatentHit:
    return PatentHit(
        patent_id=patent_id,
        title=f"Patent {patent_id}",
    )


@pytest.mark.asyncio
async def test_execute_live_evidence_collectors_runs_uspto_and_regulatory_collectors(
    mock_settings,
) -> None:
    us_hit = _hit("US1234567B2")
    ep_hit = _hit("EP1234567B1")
    directives = [
        EvidenceCollectionDirective(
            directive_id="collect-uspto",
            directive_type="collect_us_prosecution_context",
            target_patent_ids=["US1234567B2"],
            recommended_adapters=["uspto_odp", "ptab", "orange_book"],
        ),
        EvidenceCollectionDirective(
            directive_id="collect-ep",
            directive_type="collect_ep_register_context",
            target_patent_ids=["EP1234567B1"],
            recommended_adapters=["epo_register"],
        ),
    ]
    snapshot = SimpleNamespace(matter_store=SimpleNamespace(evidence_collection_plan=directives))

    async def fake_fetch_prosecution_context(patent_id: str) -> dict[str, object]:
        assert patent_id == "US1234567B2"
        return {
            "sections_available": ["office_actions", "us_file_wrapper_dossier"],
            "office_action_count": 1,
            "file_wrapper_document_count": 4,
        }

    async def fake_enrich_ptab(hits, max_patents: int = 50) -> EnrichmentOutcome:
        assert [hit.patent_id for hit in hits] == ["US1234567B2"]
        return EnrichmentOutcome(attempted_count=1, covered_count=1, evidence_count=1)

    async def fake_enrich_epo_register(hits, max_patents: int = 50) -> EnrichmentOutcome:
        assert [hit.patent_id for hit in hits] == ["EP1234567B1"]
        return EnrichmentOutcome(attempted_count=1, covered_count=1, evidence_count=1)

    async def fake_enrich_orange_book(hits) -> EnrichmentOutcome:
        assert [hit.patent_id for hit in hits] == ["US1234567B2"]
        return EnrichmentOutcome(attempted_count=1, covered_count=1, evidence_count=1)

    result = await execute_live_evidence_collectors(
        compound=SimpleNamespace(name="aspirin"),
        patent_hits=[us_hit, ep_hit],
        source_health=SourceHealth(entries=[]),
        prosecution_cache={},
        settings=SimpleNamespace(
            uspto_odp_api_key="odp-key",
            ops_consumer_key="ops-key",
            ops_consumer_secret="ops-secret",
        ),
        build_runtime_evidence_snapshot_fn=lambda **_: snapshot,
        fetch_prosecution_context_fn=fake_fetch_prosecution_context,
        enrich_ptab_proceedings_fn=fake_enrich_ptab,
        enrich_epo_register_fn=fake_enrich_epo_register,
        enrich_orange_book_fn=fake_enrich_orange_book,
    )

    assert result.executed_collectors == ["uspto_odp", "ptab", "epo_register", "orange_book"]
    assert result.prosecution_cache["US1234567B2"]["file_wrapper_document_count"] == 4
    by_source = {entry.source: entry for entry in result.source_health.entries}
    assert by_source["uspto_odp"].status == SourceStatus.OK
    assert by_source["uspto_odp"].patent_count == 1
    assert by_source["ptab"].patent_count == 1
    assert by_source["epo_register"].patent_count == 1
    assert by_source["orange_book"].patent_count == 1


@pytest.mark.asyncio
async def test_execute_live_evidence_collectors_fails_closed_on_missing_uspto_credentials(
    mock_settings,
) -> None:
    snapshot = SimpleNamespace(
        matter_store=SimpleNamespace(
            evidence_collection_plan=[
                EvidenceCollectionDirective(
                    directive_id="collect-uspto",
                    directive_type="collect_us_prosecution_context",
                    target_patent_ids=["US1234567B2"],
                    recommended_adapters=["uspto_odp", "ptab"],
                ),
                EvidenceCollectionDirective(
                    directive_id="collect-ep",
                    directive_type="collect_ep_register_context",
                    target_patent_ids=["EP1234567B1"],
                    recommended_adapters=["epo_register"],
                ),
            ]
        )
    )

    with pytest.raises(ConfigurationError) as excinfo:
        await execute_live_evidence_collectors(
            compound=SimpleNamespace(name="aspirin"),
            patent_hits=[_hit("US1234567B2"), _hit("EP1234567B1")],
            source_health=SourceHealth(entries=[]),
            prosecution_cache={},
            settings=SimpleNamespace(
                uspto_odp_api_key="",
                ops_consumer_key="",
                ops_consumer_secret="",
            ),
            build_runtime_evidence_snapshot_fn=lambda **_: snapshot,
        )

    assert excinfo.value.source == "uspto_odp"


@pytest.mark.parametrize(
    ("adapter", "expected_source"),
    [
        ("patentsview", "patentsview"),
        ("epo_search", "epo_search"),
    ],
)
@pytest.mark.asyncio
async def test_execute_live_evidence_collectors_fails_closed_on_missing_claim_source_credentials(
    adapter,
    expected_source,
    mock_settings,
) -> None:
    snapshot = SimpleNamespace(
        matter_store=SimpleNamespace(
            evidence_collection_plan=[
                EvidenceCollectionDirective(
                    directive_id="claims",
                    directive_type="collect_claims_text",
                    target_patent_ids=["US1234567B2"],
                    recommended_adapters=[adapter],
                )
            ]
        )
    )

    with pytest.raises(ConfigurationError) as excinfo:
        await execute_live_evidence_collectors(
            compound=SimpleNamespace(name="aspirin"),
            patent_hits=[_hit("US1234567B2")],
            source_health=SourceHealth(entries=[]),
            prosecution_cache={},
            settings=SimpleNamespace(
                patentsview_api_key="",
                ops_consumer_key="",
                ops_consumer_secret="",
                uspto_odp_api_key="",
            ),
            build_runtime_evidence_snapshot_fn=lambda **_: snapshot,
        )

    assert excinfo.value.source == expected_source


@pytest.mark.parametrize(
    ("adapter", "expected_source"),
    [
        ("ptab", "ptab"),
        ("epo_register", "epo_register"),
    ],
)
@pytest.mark.asyncio
async def test_execute_live_evidence_collectors_fails_closed_on_missing_counting_source_credentials(
    adapter,
    expected_source,
    mock_settings,
) -> None:
    snapshot = SimpleNamespace(
        matter_store=SimpleNamespace(
            evidence_collection_plan=[
                EvidenceCollectionDirective(
                    directive_id=f"collect-{adapter}",
                    directive_type="collect_authoritative_context",
                    target_patent_ids=["US1234567B2"],
                    recommended_adapters=[adapter],
                )
            ]
        )
    )

    with pytest.raises(ConfigurationError) as excinfo:
        await execute_live_evidence_collectors(
            compound=SimpleNamespace(name="aspirin"),
            patent_hits=[_hit("US1234567B2")],
            source_health=SourceHealth(entries=[]),
            prosecution_cache={},
            settings=SimpleNamespace(
                uspto_odp_api_key="",
                ops_consumer_key="",
                ops_consumer_secret="",
            ),
            build_runtime_evidence_snapshot_fn=lambda **_: snapshot,
        )

    assert excinfo.value.source == expected_source


@pytest.mark.asyncio
async def test_execute_live_evidence_collectors_runs_claims_and_family_collectors(
    mock_settings,
    monkeypatch,
) -> None:
    us_hit = _hit("US1234567B2")
    ep_hit = _hit("EP1234567B1")
    snapshot = SimpleNamespace(
        matter_store=SimpleNamespace(
            evidence_collection_plan=[
                EvidenceCollectionDirective(
                    directive_id="claims",
                    directive_type="collect_claims_text",
                    target_patent_ids=["US1234567B2", "EP1234567B1"],
                    recommended_adapters=["bigquery", "patentsview", "epo_search"],
                ),
                EvidenceCollectionDirective(
                    directive_id="family",
                    directive_type="expand_family_context",
                    target_patent_ids=["EP1234567B1"],
                    recommended_adapters=["family_record"],
                ),
            ]
        )
    )

    async def fake_bigquery(hits):
        assert [hit.patent_id for hit in hits] == ["US1234567B2", "EP1234567B1"]
        us_hit.claims_text = "US claim text"
        us_hit.claims_text_source = "bigquery"
        return (
            SourceHealthEntry(
                source="bigquery",
                status=SourceStatus.OK,
                patent_count=1,
                error_message="",
            ),
            ["US1234567B2"],
        )

    async def fake_patentsview(hits):
        assert [hit.patent_id for hit in hits] == ["US1234567B2", "EP1234567B1"]
        return (
            SourceHealthEntry(
                source="patentsview",
                status=SourceStatus.OK,
                patent_count=0,
                error_message="",
            ),
            [],
        )

    async def fake_epo(hits):
        assert [hit.patent_id for hit in hits] == ["US1234567B2", "EP1234567B1"]
        ep_hit.claims_text = "EP claim text"
        ep_hit.claims_text_source = "epo_search"
        return (
            SourceHealthEntry(
                source="epo_search",
                status=SourceStatus.OK,
                patent_count=1,
                error_message="",
            ),
            ["EP1234567B1"],
        )

    async def fake_family(*, patent_hits, expand_families_fn):
        assert [hit.patent_id for hit in patent_hits] == ["EP1234567B1"]
        ep_hit.family = SimpleNamespace(family_id="fam-1")
        return SourceHealthEntry(
            source="family_record",
            status=SourceStatus.OK,
            patent_count=1,
            error_message="",
        )

    monkeypatch.setattr(module, "_collect_claims_from_bigquery", fake_bigquery)
    monkeypatch.setattr(module, "_collect_claims_from_patentsview", fake_patentsview)
    monkeypatch.setattr(module, "_collect_claims_from_epo", fake_epo)
    monkeypatch.setattr(module, "_collect_family_context_runtime", fake_family)

    result = await execute_live_evidence_collectors(
        compound=SimpleNamespace(name="aspirin"),
        patent_hits=[us_hit, ep_hit],
        source_health=SourceHealth(entries=[]),
        prosecution_cache={},
        settings=SimpleNamespace(
            patentsview_api_key="pv-key",
            ops_consumer_key="ops-key",
            ops_consumer_secret="ops-secret",
            uspto_odp_api_key="odp-key",
        ),
        build_runtime_evidence_snapshot_fn=lambda **_: snapshot,
    )

    assert us_hit.claims_text == "US claim text"
    assert us_hit.claims_text_source == "bigquery"
    assert ep_hit.claims_text == "EP claim text"
    assert ep_hit.claims_text_source == "epo_search"
    assert ep_hit.family.family_id == "fam-1"
    assert result.executed_collectors == ["bigquery", "patentsview", "epo_search", "family_record"]
    by_source = {entry.source: entry for entry in result.source_health.entries}
    assert by_source["bigquery"].patent_count == 1
    assert by_source["epo_search"].patent_count == 1
    assert by_source["family_record"].patent_count == 1


@pytest.mark.asyncio
async def test_execute_live_evidence_collectors_stops_on_required_authoritative_claim_failure(
    mock_settings,
    monkeypatch,
) -> None:
    snapshot = SimpleNamespace(
        matter_store=SimpleNamespace(
            evidence_collection_plan=[
                EvidenceCollectionDirective(
                    directive_id="claims",
                    directive_type="collect_claims_text",
                    required_before_clear=True,
                    target_patent_ids=["US1234567B2"],
                    recommended_adapters=["patentsview"],
                )
            ]
        )
    )

    async def fake_patentsview(hits):
        return (
            SourceHealthEntry(
                source="patentsview",
                status=SourceStatus.FAILED,
                patent_count=0,
                error_message="source offline",
            ),
            [],
        )

    monkeypatch.setattr(module, "_collect_claims_from_patentsview", fake_patentsview)

    with pytest.raises(SourceUnavailableError) as excinfo:
        await execute_live_evidence_collectors(
            compound=SimpleNamespace(name="aspirin"),
            patent_hits=[_hit("US1234567B2")],
            source_health=SourceHealth(entries=[]),
            prosecution_cache={},
            settings=SimpleNamespace(
                patentsview_api_key="pv-key",
                ops_consumer_key="",
                ops_consumer_secret="",
                uspto_odp_api_key="",
            ),
            build_runtime_evidence_snapshot_fn=lambda **_: snapshot,
        )

    assert excinfo.value.source == "patentsview"
    assert "source offline" in str(excinfo.value)


@pytest.mark.asyncio
async def test_execute_live_evidence_collectors_preserves_live_attempt_history(
    mock_settings,
    monkeypatch,
) -> None:
    us_hit = _hit("US1234567B2")
    snapshot = SimpleNamespace(
        matter_store=SimpleNamespace(
            evidence_collection_plan=[
                EvidenceCollectionDirective(
                    directive_id="claims",
                    directive_type="collect_claims_text",
                    target_patent_ids=["US1234567B2"],
                    recommended_adapters=["bigquery"],
                )
            ]
        ),
        collector_runs=[
            EvidenceCollectorRun(
                definition=EvidenceCollectorDefinition(
                    collector_name="bigquery",
                    adapter_kind=EvidenceAdapterKind.SEARCH,
                    authority_tier=EvidenceAuthorityTier.SUPPORTING,
                    expected_components=["claims_text"],
                ),
                collection_state=EvidenceCollectionState.MISSING,
                required_before_clear=True,
                target_patent_ids=["US1234567B2"],
                missing_patent_ids=["US1234567B2"],
                expected_components=["claims_text"],
                missing_components=["claims_text"],
                attempts=[
                    CollectionAttempt(
                        attempt_number=1,
                        status=SourceStatus.SKIPPED,
                        collection_state=EvidenceCollectionState.MISSING,
                        artifact_count=0,
                        warnings=["first pass skipped"],
                        summary="Initial collector attempt was skipped.",
                    )
                ],
            )
        ],
    )

    async def fake_bigquery(hits):
        us_hit.claims_text = "claim text"
        us_hit.claims_text_source = "bigquery"
        return (
            SourceHealthEntry(
                source="bigquery",
                status=SourceStatus.OK,
                patent_count=1,
                error_message="",
            ),
            ["US1234567B2"],
        )

    monkeypatch.setattr(module, "_collect_claims_from_bigquery", fake_bigquery)

    result = await execute_live_evidence_collectors(
        compound=SimpleNamespace(name="aspirin"),
        patent_hits=[us_hit],
        source_health=SourceHealth(entries=[]),
        prosecution_cache={},
        collector_runs=list(snapshot.collector_runs),
        settings=SimpleNamespace(
            patentsview_api_key="",
            ops_consumer_key="",
            ops_consumer_secret="",
            uspto_odp_api_key="",
        ),
        build_runtime_evidence_snapshot_fn=lambda **_: snapshot,
    )

    by_name = {run.definition.collector_name: run for run in result.collector_runs}
    assert by_name["bigquery"].attempts[0].attempt_number == 1
    assert by_name["bigquery"].attempts[1].attempt_number == 2
    assert by_name["bigquery"].attempts[1].status == SourceStatus.OK
