"""Search source fail-closed regressions."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from praviar_pipeline.errors import (
    ConfigurationError,
    PatCIDDatabaseNotFoundError,
    SearchSourceFailedError,
    SourceUnavailableError,
)
from praviar_pipeline.models.report import SourceHealth, SourceHealthEntry, SourceStatus
from praviar_pipeline.pipeline.search import enrichment as search_enrichment
from praviar_pipeline.pipeline.search import global_sources
from praviar_pipeline.pipeline.search.models import SearchExecutionSummary
from praviar_pipeline.pipeline.search.orchestration import (
    execute_search_coordinator,
    partition_source_outcomes,
)


def test_partition_source_outcomes_marks_missing_config_not_configured():
    sentinel = "lens-config-credential-sentinel"
    summary = partition_source_outcomes(
        [
            (
                "lens",
                None,
                ConfigurationError(
                    f"Lens API key not configured: {sentinel}",
                    source="lens",
                    step="search",
                ),
                3,
            )
        ]
    )

    entry = summary.health.entries[0]
    assert entry.status == SourceStatus.NOT_CONFIGURED
    assert summary.health.any_failed is True
    assert summary.failures["lens"] == "source search failed (ConfigurationError)"
    assert sentinel not in repr(summary.failures)
    assert sentinel not in summary.health.model_dump_json()


def test_partition_source_outcomes_marks_missing_patcid_db_not_configured():
    sentinel = "patcid-database-path-sentinel"
    summary = partition_source_outcomes(
        [
            (
                "patcid",
                None,
                PatCIDDatabaseNotFoundError(f"/missing/{sentinel}/patcid.sqlite"),
                4,
            )
        ]
    )

    entry = summary.health.entries[0]
    assert entry.status == SourceStatus.NOT_CONFIGURED
    assert summary.health.any_failed is True
    assert summary.failures["patcid"] == ("source search failed (PatCIDDatabaseNotFoundError)")
    assert sentinel not in repr(summary.failures)
    assert sentinel not in summary.health.model_dump_json()


@pytest.mark.asyncio
async def test_global_source_missing_credentials_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        global_sources,
        "get_settings",
        lambda: SimpleNamespace(lens_api_key="", lens_max_patent_results=10),
    )

    with pytest.raises(ConfigurationError):
        await global_sources.search_lens(SimpleNamespace(name="aspirin", synonyms=[]))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("func", "settings", "expected_source"),
    [
        (
            search_enrichment.enrich_application_data,
            SimpleNamespace(uspto_odp_api_key="", search_max_patent_term_calc=5),
            "uspto_odp",
        ),
        (
            search_enrichment.enrich_epo_register,
            SimpleNamespace(ops_consumer_key="", ops_consumer_secret=""),
            "epo_register",
        ),
    ],
)
async def test_post_search_enrichment_missing_credentials_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    func,
    settings,
    expected_source,
):
    monkeypatch.setattr(search_enrichment, "get_settings", lambda: settings)

    with pytest.raises(ConfigurationError) as excinfo:
        await func([])

    assert excinfo.value.source == expected_source


@pytest.mark.asyncio
async def test_ptab_enrichment_fails_closed_when_no_key(
    monkeypatch: pytest.MonkeyPatch,
):
    """Missing PTAB authority must not be represented as a valid zero."""
    monkeypatch.setattr(
        search_enrichment, "get_settings", lambda: SimpleNamespace(uspto_odp_api_key="")
    )

    with pytest.raises(ConfigurationError) as exc_info:
        await search_enrichment.enrich_ptab_proceedings([])
    assert exc_info.value.source == "ptab"


@pytest.mark.asyncio
async def test_ptab_enrichment_fails_closed_on_auth_error(
    monkeypatch: pytest.MonkeyPatch,
):
    """PTAB auth failure is a coverage failure, not empty proceedings."""
    from unittest.mock import patch

    from praviar_pipeline.errors import AuthenticationError

    monkeypatch.setattr(
        search_enrichment, "get_settings", lambda: SimpleNamespace(uspto_odp_api_key="bad-key")
    )
    hit = SimpleNamespace(patent_id="US1234567B2", is_granted=True, ptab_proceedings=[])
    client = AsyncMock()
    client.get_proceedings = AsyncMock(
        side_effect=AuthenticationError("PTAB ODP API key is invalid or missing", source="ptab")
    )
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch("praviar_pipeline.clients.ptab.PTABClient", return_value=client):
        with pytest.raises(SourceUnavailableError) as exc_info:
            await search_enrichment.enrich_ptab_proceedings([hit])
    assert exc_info.value.source == "ptab"


@pytest.mark.asyncio
async def test_application_data_enrichment_source_failure_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        search_enrichment,
        "get_settings",
        lambda: SimpleNamespace(uspto_odp_api_key="odp-key", search_max_patent_term_calc=5),
    )
    hit = SimpleNamespace(
        patent_id="US1234567B2",
        is_granted=True,
        assignments=[],
        inventors=[],
        assignees=[],
    )
    client = AsyncMock()
    client.get_application_data.side_effect = httpx.ConnectError("offline")
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with pytest.raises(SourceUnavailableError) as excinfo:
        await search_enrichment.enrich_application_data([hit], client_factory=lambda: client)

    assert excinfo.value.source == "uspto_odp"


@pytest.mark.asyncio
async def test_search_coordinator_raises_when_any_required_source_failed():
    async def execute_plan(_plan, _run_source):
        return SearchExecutionSummary(
            health=SourceHealth(
                entries=[
                    SourceHealthEntry(
                        source="pubchem_sdq",
                        status=SourceStatus.OK,
                        patent_count=1,
                    ),
                    SourceHealthEntry(
                        source="lens",
                        status=SourceStatus.NOT_CONFIGURED,
                        error_message="Lens API key not configured",
                    ),
                ]
            ),
            failures={"lens": "Lens API key not configured"},
        )

    with pytest.raises(SearchSourceFailedError):
        await execute_search_coordinator(
            compound=SimpleNamespace(name="aspirin"),
            expanded_queries=SimpleNamespace(),
            has_expansion=False,
            settings=SimpleNamespace(),
            build_search_plan_fn=lambda **_kwargs: [],
            execute_search_plan_fn=execute_plan,
            run_source_fn=lambda *_args: None,
            prepare_search_results_fn=lambda **_kwargs: None,
            build_source_map_fn=lambda *_args, **_kwargs: {},
            rank_patents_fn=lambda *_args, **_kwargs: [],
            assemble_hits_fn=lambda *_args, **_kwargs: [],
            build_search_contribution_summary_fn=lambda *_args, **_kwargs: None,
            normalize_patent_id=lambda value: value,
            maybe_expand_via_citations_fn=lambda **_kwargs: None,
            expand_via_citations_fn=lambda *_args, **_kwargs: None,
            finalize_search_run_fn=lambda *_args, **_kwargs: None,
            enrich_hits_fn=lambda *_args, **_kwargs: None,
            emit_search_completion_logs_fn=lambda *_args, **_kwargs: None,
        )
