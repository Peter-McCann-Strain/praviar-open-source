"""Regulatory enrichment source-health regressions."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from praviar_pipeline.clients.pte_data import PTECertificateDataset
from praviar_pipeline.models.report_common import SourceHealth, SourceStatus
from praviar_pipeline.pipeline.runtime.flow_models import RunBootstrapResult
from praviar_pipeline.pipeline.runtime.post_analysis import run_regulatory_enrichment


@pytest.mark.asyncio
async def test_regulatory_enrichment_records_failed_pte_source(monkeypatch) -> None:
    sentinel = "pte-provider-query-credential-sentinel"

    async def _raise_pte_failure(*_args, **_kwargs):
        raise RuntimeError(f"pte source unavailable?api_key={sentinel}")

    monkeypatch.setattr(
        "praviar_pipeline.clients.pte_data.fetch_pte_certificate_dataset",
        _raise_pte_failure,
    )
    source_health = SourceHealth(entries=[])

    result = await run_regulatory_enrichment(
        SimpleNamespace(
            name="aspirin",
            nda_number="",
            bla_number="",
            compound_type="small_molecule",
        ),
        source_health=source_health,
    )

    assert result is not None
    assert result.data_sources_queried == ["pte_data"]
    assert len(result.source_statuses) == 1
    assert result.source_statuses[0].source == "pte_data"
    assert result.source_statuses[0].status == SourceStatus.FAILED
    assert result.source_statuses[0].error_message == "PTE enrichment failed (RuntimeError)"
    assert sentinel not in result.model_dump_json()
    assert len(source_health.entries) == 1
    entry = source_health.entries[0]
    assert entry.source == "pte_data"
    assert entry.status == SourceStatus.FAILED
    assert entry.error_message == "PTE enrichment failed (RuntimeError)"
    assert sentinel not in entry.model_dump_json()


@pytest.mark.asyncio
async def test_regulatory_enrichment_uses_issued_certificates_with_dataset_provenance(
    monkeypatch,
) -> None:
    retrieved_at = datetime(2026, 5, 8, 12, tzinfo=UTC)

    async def _issued_dataset():
        return PTECertificateDataset(
            records=[
                {
                    "patent_number": "US7654321",
                    "product_name": "Aspirin",
                    "nda_bla_number": "NDA012345",
                    "extension_days": "365",
                    "status": "issued",
                }
            ],
            source_url="https://www.uspto.gov/pte_certs.xls",
            official_page_url="https://www.uspto.gov/patent-term-extension",
            coverage_scope="all_time_issued_certificates_excluding_interim_only",
            coverage_note="Issued certificates; interim-only extensions excluded.",
            retrieved_at=retrieved_at,
            publisher_last_modified="Fri, 08 May 2026 12:00:00 GMT",
        )

    monkeypatch.setattr(
        "praviar_pipeline.clients.pte_data.fetch_pte_certificate_dataset",
        _issued_dataset,
    )

    result = await run_regulatory_enrichment(
        SimpleNamespace(
            name="aspirin",
            nda_number="NDA012345",
            bla_number="",
            compound_type="small_molecule",
        )
    )

    assert result is not None
    assert len(result.pte_extensions) == 1
    assert result.pte_extensions[0].status == "issued"
    assert result.pte_source_scope == "all_time_issued_certificates_excluding_interim_only"
    assert result.pte_source_retrieved_at == retrieved_at
    assert result.pte_source_publisher_last_modified == "Fri, 08 May 2026 12:00:00 GMT"
    pte_health = next(entry for entry in result.source_statuses if entry.source == "pte_data")
    assert pte_health.attempted_count == 1
    assert pte_health.covered_count == 1


def test_run_bootstrap_result_can_store_regulatory_exclusivity() -> None:
    state = RunBootstrapResult(
        settings=SimpleNamespace(),
        checkpoint_integrity_keys=object(),
        execution_profile="world_class_adaptive",
        analysis_escalation_reasons=[],
        user_input="aspirin",
        run_id="run_123",
        checkpoint_dir=Path("/tmp/run_123"),
        started_at_epoch=1.0,
        deadline_epoch=None,
    )

    state.regulatory_exclusivity = {"source": "pte_data"}

    assert state.regulatory_exclusivity == {"source": "pte_data"}
