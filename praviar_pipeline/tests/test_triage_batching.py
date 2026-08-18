from __future__ import annotations

from types import SimpleNamespace

import pytest

from praviar_pipeline.models.triage import Relevance, TriageBatch, TriageResult
from praviar_pipeline.pipeline.triage.batching import run_llm_triage_batches


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        triage_batch_size=2,
        triage_concurrency=1,
        triage_max_tokens=256,
    )


@pytest.mark.asyncio
async def test_failed_triage_batch_preserves_every_patent_as_unknown() -> None:
    patents = [SimpleNamespace(patent_id="US-LOST-1"), SimpleNamespace(patent_id="EP-LOST-2")]

    async def fail_batch(*_args, **_kwargs):
        raise RuntimeError("provider-secret-must-not-escape")

    result = await run_llm_triage_batches(
        claude=SimpleNamespace(),
        llm_patents=patents,
        known_patent_ids={patent.patent_id for patent in patents},
        compound=SimpleNamespace(),
        system_prompt="triage",
        settings=_settings(),
        auto_results=[],
        drawing_evidence=None,
        triage_batch_fn=fail_batch,
    )

    assert [item.patent_id for item in result.all_results] == ["US-LOST-1", "EP-LOST-2"]
    assert all(item.relevance == Relevance.UNKNOWN for item in result.all_results)
    assert [item.patent_id for item in result.filtered] == ["US-LOST-1", "EP-LOST-2"]
    assert result.failed_patent_count == 2
    assert result.failed_batch_count == 1
    assert "provider-secret" not in repr(result)


@pytest.mark.asyncio
async def test_incomplete_triage_response_creates_unknown_coverage_record() -> None:
    patents = [SimpleNamespace(patent_id="US-COVERED"), SimpleNamespace(patent_id="US-MISSING")]

    async def incomplete_batch(*_args, **_kwargs):
        return TriageBatch(
            results=[
                TriageResult(
                    patent_id="US-COVERED",
                    relevance=Relevance.NOT_RELEVANT,
                    reason="not material",
                )
            ]
        )

    result = await run_llm_triage_batches(
        claude=SimpleNamespace(),
        llm_patents=patents,
        known_patent_ids={patent.patent_id for patent in patents},
        compound=SimpleNamespace(),
        system_prompt="triage",
        settings=_settings(),
        auto_results=[],
        drawing_evidence=None,
        triage_batch_fn=incomplete_batch,
    )

    by_id = {item.patent_id: item for item in result.all_results}
    assert by_id["US-COVERED"].relevance == Relevance.NOT_RELEVANT
    assert by_id["US-MISSING"].relevance == Relevance.UNKNOWN
    assert [item.patent_id for item in result.filtered] == ["US-MISSING"]
    assert result.failed_patent_count == 1
