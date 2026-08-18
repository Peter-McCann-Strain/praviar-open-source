"""Tests for apply_markush_scope_verdicts post-pass (Phase E wire-in)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from praviar_pipeline.models.drawing import (
    DrawingAnalysisResults,
    DrawingStructure,
    MarkushScopeVerdict,
    PatentDrawingAnalysis,
)
from praviar_pipeline.pipeline.drawings.markush_scope_apply import apply_markush_scope_verdicts


def _markush_struct(
    patent_id: str = "US1",
    idx: int = 0,
    cxsmiles: str = "[*:1]c1ccccc1",
    verdict: MarkushScopeVerdict | None = None,
) -> DrawingStructure:
    return DrawingStructure(
        patent_id=patent_id,
        page_number=1,
        structure_index=idx,
        is_markush=True,
        markush_cxsmiles=cxsmiles,
        markush_scope_verdict=verdict,
    )


def _non_markush_struct(patent_id: str = "US1", idx: int = 0) -> DrawingStructure:
    return DrawingStructure(
        patent_id=patent_id,
        page_number=1,
        structure_index=idx,
        raw_smiles="CCO",
        canonical_smiles="CCO",
    )


def _results(patent_id: str, structures: list[DrawingStructure]) -> DrawingAnalysisResults:
    return DrawingAnalysisResults(
        patent_analyses=[
            PatentDrawingAnalysis(
                patent_id=patent_id,
                pages_fetched=1,
                structures_found=len(structures),
                structures=structures,
            )
        ]
    )


class _Settings:
    def __init__(
        self,
        enabled: bool = True,
        max_turns: int = 8,
        max_output_tokens: int = 6000,
        model: str = "claude-opus-4-7-test",
        rollout_state: str = "shadow",
    ) -> None:
        self.drawing_markush_scope_agent_enabled = enabled
        self.drawing_markush_scope_agent_max_turns = max_turns
        self.drawing_markush_scope_agent_max_output_tokens = max_output_tokens
        self.drawing_markush_scope_agent_model = model
        self.claude_deep_model = model
        self.drawing_analysis_rollout_state = rollout_state


@pytest.mark.asyncio
async def test_noop_when_disabled():
    results = _results("US1", [_markush_struct()])
    claude = MagicMock()
    claude.complete_text = AsyncMock(return_value=("", {}))
    count = await apply_markush_scope_verdicts(
        results,
        target_smiles="Clc1ccccc1",
        claim_text_by_patent={"US1": "R1 is halogen"},
        claude=claude,
        settings=_Settings(enabled=False),
    )
    assert count == 0
    claude.complete_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_noop_when_claude_missing():
    results = _results("US1", [_markush_struct()])
    count = await apply_markush_scope_verdicts(
        results,
        target_smiles="Clc1ccccc1",
        claim_text_by_patent={},
        claude=None,
        settings=_Settings(enabled=True),
    )
    assert count == 0


@pytest.mark.asyncio
async def test_noop_when_target_empty():
    results = _results("US1", [_markush_struct()])
    claude = MagicMock()
    count = await apply_markush_scope_verdicts(
        results,
        target_smiles="",
        claim_text_by_patent={},
        claude=claude,
        settings=_Settings(enabled=True),
    )
    assert count == 0


@pytest.mark.asyncio
async def test_live_drawing_rollout_rejects_experimental_scope_agent():
    results = _results("US1", [_markush_struct()])
    claude = MagicMock()
    claude.complete_text = AsyncMock()

    with pytest.raises(RuntimeError, match="shadow-only"):
        await apply_markush_scope_verdicts(
            results,
            target_smiles="Clc1ccccc1",
            claim_text_by_patent={"US1": "R1 is halogen"},
            claude=claude,
            settings=_Settings(enabled=True, rollout_state="production"),
        )

    claude.complete_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_happy_path_populates_verdict():
    results = _results("US1", [_markush_struct()])
    claude = MagicMock()

    async def _complete_text(*, toolkit, **_kwargs):
        await toolkit.execute("rdkit_canonical", {"smiles": "Clc1ccccc1"})
        return (
            "<verdict>"
            '{"verdict": "in_scope", "reasoning": "R1=Cl matches halogen", '
            '"confidence": 0.9}'
            "</verdict>"
        ), {}

    claude.complete_text = AsyncMock(side_effect=_complete_text)

    count = await apply_markush_scope_verdicts(
        results,
        target_smiles="Clc1ccccc1",
        claim_text_by_patent={"US1": "R1 is halogen"},
        claude=claude,
        settings=_Settings(enabled=True),
        rgroup_definitions_by_patent={"US1": {"1": ["F", "Cl", "Br", "I"]}},
    )
    assert count == 1
    verdict = results.patent_analyses[0].structures[0].markush_scope_verdict
    assert verdict is not None
    assert verdict.verdict == "in_scope"
    assert verdict.tool_calls == 1


@pytest.mark.asyncio
async def test_skips_non_markush_structures():
    results = _results(
        "US1",
        [_non_markush_struct(idx=0), _markush_struct(idx=1)],
    )
    claude = MagicMock()

    async def _complete_text(*, toolkit, **_kwargs):
        await toolkit.execute("rdkit_canonical", {"smiles": "Clc1ccccc1"})
        return '<verdict>{"verdict": "out_of_scope", "reasoning": "x"}</verdict>', {}

    claude.complete_text = AsyncMock(side_effect=_complete_text)

    count = await apply_markush_scope_verdicts(
        results,
        target_smiles="Clc1ccccc1",
        claim_text_by_patent={"US1": ""},
        claude=claude,
        settings=_Settings(enabled=True),
    )
    assert count == 1
    assert results.patent_analyses[0].structures[0].markush_scope_verdict is None
    assert results.patent_analyses[0].structures[1].markush_scope_verdict is not None


@pytest.mark.asyncio
async def test_idempotent_does_not_overwrite_existing_verdict():
    existing = MarkushScopeVerdict(verdict="out_of_scope", reasoning="prior", confidence=0.7)
    results = _results("US1", [_markush_struct(verdict=existing)])
    claude = MagicMock()
    claude.complete_text = AsyncMock()

    count = await apply_markush_scope_verdicts(
        results,
        target_smiles="Clc1ccccc1",
        claim_text_by_patent={"US1": ""},
        claude=claude,
        settings=_Settings(enabled=True),
    )
    assert count == 0
    claude.complete_text.assert_not_awaited()
    assert results.patent_analyses[0].structures[0].markush_scope_verdict is existing


@pytest.mark.asyncio
async def test_skips_structure_without_scaffold():
    """If MG2 never populated markush_cxsmiles AND canonical_smiles is empty,
    there's nothing to reason about — skip cleanly."""
    struct = DrawingStructure(
        patent_id="US1",
        page_number=1,
        structure_index=0,
        is_markush=True,
        markush_cxsmiles="",
        canonical_smiles="",
    )
    results = _results("US1", [struct])
    claude = MagicMock()
    claude.complete_text = AsyncMock()

    count = await apply_markush_scope_verdicts(
        results,
        target_smiles="Clc1ccccc1",
        claim_text_by_patent={},
        claude=claude,
        settings=_Settings(enabled=True),
    )
    assert count == 0


@pytest.mark.asyncio
async def test_agent_exception_logged_and_skipped():
    """If the agent raises, the structure is left alone and the next one is tried."""
    good = _markush_struct(patent_id="US1", idx=0)
    bad = _markush_struct(patent_id="US1", idx=1)
    results = _results("US1", [bad, good])

    claude = MagicMock()
    call_count = {"n": 0}

    async def _complete_text(*, toolkit, **_kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("transient API error")
        await toolkit.execute("rdkit_canonical", {"smiles": "Clc1ccccc1"})
        return '<verdict>{"verdict": "in_scope", "reasoning": "ok"}</verdict>', {}

    claude.complete_text = AsyncMock(side_effect=_complete_text)

    count = await apply_markush_scope_verdicts(
        results,
        target_smiles="Clc1ccccc1",
        claim_text_by_patent={"US1": ""},
        claude=claude,
        settings=_Settings(enabled=True),
    )
    assert count == 1  # only the 2nd structure succeeded
    assert results.patent_analyses[0].structures[0].markush_scope_verdict is None
    assert results.patent_analyses[0].structures[1].markush_scope_verdict is not None
