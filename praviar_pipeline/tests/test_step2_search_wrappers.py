from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from praviar_pipeline.errors import SourceUnavailableError


@pytest.mark.asyncio
async def test_source_wrapper_delegates_to_primary_sources(succinic_acid):
    from praviar_pipeline.pipeline.search import wiring

    with patch(
        "praviar_pipeline.pipeline.search.primary_sources.search_pubchem_sdq",
        new_callable=AsyncMock,
        return_value=[{"publicationnumber": "US1"}],
    ) as mocked:
        result = await wiring._search_pubchem_sdq(succinic_acid)

    mocked.assert_awaited_once_with(succinic_acid)
    assert result == [{"publicationnumber": "US1"}]


@pytest.mark.asyncio
async def test_expanded_source_wrapper_injects_bigquery_client(succinic_acid):
    from praviar_pipeline.models.search import ExpandedSearchQueries
    from praviar_pipeline.pipeline.search import wiring

    expanded = ExpandedSearchQueries(cpc_codes=["C12P"])
    with patch(
        "praviar_pipeline.pipeline.search.expansion_sources.search_bigquery_cpc",
        new_callable=AsyncMock,
        return_value=[],
    ) as mocked:
        await wiring._search_bigquery_cpc(succinic_acid, expanded)

    _, kwargs = mocked.await_args
    assert kwargs["client_factory"].__name__ == "BigQueryClient"


@pytest.mark.asyncio
async def test_enrichment_wrapper_delegates_without_injectable_client(sample_patent_hits):
    from praviar_pipeline.pipeline.search import wiring

    with patch(
        "praviar_pipeline.pipeline.search.enrichment.enrich_legal_status",
        new_callable=AsyncMock,
        return_value=3,
    ) as mocked:
        count = await wiring._enrich_legal_status(sample_patent_hits)

    _, kwargs = mocked.await_args
    assert "client_factory" not in kwargs
    assert kwargs["derive_legal_status"] is not None
    assert count == 3


@pytest.mark.asyncio
async def test_facade_wrapper_still_delegates_through_step2_search(succinic_acid):
    from praviar_pipeline.pipeline.step2_search import _search_pubchem_sdq

    with patch(
        "praviar_pipeline.pipeline.search.primary_sources.search_pubchem_sdq",
        new_callable=AsyncMock,
        return_value=[{"publicationnumber": "US2"}],
    ) as mocked:
        result = await _search_pubchem_sdq(succinic_acid)

    mocked.assert_awaited_once_with(succinic_acid)
    assert result == [{"publicationnumber": "US2"}]


class _FakeSettings:
    def __init__(
        self,
        *,
        continuation_expansion_enabled=True,
        continuation_max_patents=50,
        continuation_max_depth=2,
        continuation_expansion_timeout_s=300.0,
    ):
        self.continuation_expansion_enabled = continuation_expansion_enabled
        self.continuation_max_patents = continuation_max_patents
        self.continuation_max_depth = continuation_max_depth
        self.continuation_expansion_timeout_s = continuation_expansion_timeout_s


@pytest.mark.asyncio
async def test_expand_continuations_wrapper_calls_expansion_with_factories(
    sample_patent_hits,
):
    """SG-122: the wiring wrapper should thread USPTO ODP + EPO OPS factories in."""
    from praviar_pipeline.clients.epo_ops import EPOOPSClient
    from praviar_pipeline.clients.uspto_odp import USPTOODPClient
    from praviar_pipeline.pipeline.search import wiring

    with (
        patch(
            "praviar_pipeline.config.get_settings",
            return_value=_FakeSettings(),
        ),
        patch(
            "praviar_pipeline.pipeline.search.continuation_expansion.expand_continuations",
            new_callable=AsyncMock,
            return_value=5,
        ) as mocked,
    ):
        count = await wiring._expand_continuations(sample_patent_hits)

    args, kwargs = mocked.await_args
    assert args[0] is sample_patent_hits
    assert kwargs["odp_client_factory"] is USPTOODPClient
    assert kwargs["epo_client_factory"] is EPOOPSClient
    assert kwargs["max_patents"] == 50
    assert kwargs["max_depth"] == 2
    assert count == 5


@pytest.mark.asyncio
async def test_expand_continuations_wrapper_skips_when_disabled(sample_patent_hits):
    """continuation_expansion_enabled=False must short-circuit to 0 with no call."""
    from praviar_pipeline.pipeline.search import wiring

    with (
        patch(
            "praviar_pipeline.config.get_settings",
            return_value=_FakeSettings(continuation_expansion_enabled=False),
        ),
        patch(
            "praviar_pipeline.pipeline.search.continuation_expansion.expand_continuations",
            new_callable=AsyncMock,
            return_value=99,
        ) as mocked,
    ):
        count = await wiring._expand_continuations(sample_patent_hits)

    mocked.assert_not_awaited()
    assert count == 0


@pytest.mark.asyncio
async def test_expand_continuations_wrapper_fails_closed_on_timeout(sample_patent_hits):
    from praviar_pipeline.pipeline.search import wiring

    with (
        patch(
            "praviar_pipeline.config.get_settings",
            return_value=_FakeSettings(continuation_expansion_timeout_s=0.01),
        ),
        patch(
            "praviar_pipeline.pipeline.search.continuation_expansion.expand_continuations",
            new_callable=AsyncMock,
            side_effect=TimeoutError,
        ),
    ):
        with pytest.raises(SourceUnavailableError) as exc_info:
            await wiring._expand_continuations(sample_patent_hits)

    assert exc_info.value.source == "continuation_expansion"


@pytest.mark.asyncio
async def test_step2_search_facade_passes_expand_continuations(succinic_acid):
    """The facade must thread wiring._expand_continuations into the impl kwargs."""
    from praviar_pipeline.pipeline import step2_search

    with patch(
        "praviar_pipeline.pipeline.step2_search.search_orchestration.execute_search_coordinator",
        new_callable=AsyncMock,
        return_value=([], None, []),
    ) as mocked:
        await step2_search.search_patents(succinic_acid)

    _, kwargs = mocked.await_args
    assert kwargs["enrich_hits_fn"] is not None
