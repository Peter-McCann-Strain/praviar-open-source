from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_search_patents_wires_dependencies(succinic_acid, mock_settings):
    from praviar_pipeline.pipeline.step2_search import search_patents

    execute = AsyncMock(return_value=([], SimpleNamespace(), []))

    with (
        patch(
            "praviar_pipeline.pipeline.step2_search.search_orchestration.execute_search_coordinator",
            execute,
        ),
        patch(
            "praviar_pipeline.pipeline.step2_search.primary_sources.clear_surechembl_similarity_cache",
        ) as clear_cache,
    ):
        await search_patents(succinic_acid)

    clear_cache.assert_called_once()
    _, kwargs = execute.await_args
    assert kwargs["compound"] is succinic_acid
    assert kwargs["has_expansion"] is False
    assert kwargs["expand_via_citations_fn"] is not None
    assert kwargs["rank_patents_fn"] is not None
