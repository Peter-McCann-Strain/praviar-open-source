"""Tests for MarkushScopeVerdict model (Phase E.1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from praviar_pipeline.models.drawing import DrawingStructure, MarkushScopeVerdict


def test_default_verdict_is_ambiguous():
    v = MarkushScopeVerdict()
    assert v.verdict == "ambiguous"
    assert v.enumerated_hits == []
    assert v.confidence == 0.0
    assert v.tool_calls == 0


def test_in_scope_verdict_with_evidence():
    v = MarkushScopeVerdict(
        verdict="in_scope",
        reasoning="R1=Cl matches halogen enumeration; scaffold substructure matches",
        enumerated_hits=["ClC1=CC=CC=C1"],
        confidence=0.92,
        tool_calls=4,
        agent_model="claude-opus-4-7",
    )
    assert v.verdict == "in_scope"
    assert len(v.enumerated_hits) == 1
    assert v.confidence == 0.92


def test_out_of_scope_verdict():
    v = MarkushScopeVerdict(
        verdict="out_of_scope",
        reasoning="Scaffold matches but target R2 is nitro, not in {halogen, alkyl}",
        confidence=0.88,
        tool_calls=5,
        agent_model="claude-opus-4-7",
    )
    assert v.verdict == "out_of_scope"


def test_ambiguous_with_abstain_reason():
    v = MarkushScopeVerdict(
        verdict="ambiguous",
        reasoning="R-group enumeration would exceed 10,000 variants; cannot confirm",
        abstained_reason="enumeration_overflow",
        tool_calls=2,
    )
    assert v.verdict == "ambiguous"
    assert v.abstained_reason == "enumeration_overflow"


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        MarkushScopeVerdict(verdict="in_scope", gibberish="x")  # type: ignore[call-arg]


def test_drawing_structure_markush_scope_verdict_default_none():
    s = DrawingStructure(patent_id="US1", page_number=1, structure_index=0)
    assert s.markush_scope_verdict is None


def test_drawing_structure_with_markush_verdict():
    verdict = MarkushScopeVerdict(verdict="in_scope", reasoning="matches", confidence=0.9)
    s = DrawingStructure(
        patent_id="US1",
        page_number=1,
        structure_index=0,
        is_markush=True,
        markush_cxsmiles="[*:1]c1ccccc1",
        markush_scope_verdict=verdict,
    )
    assert s.markush_scope_verdict is verdict
    assert s.markush_scope_verdict.verdict == "in_scope"


def test_drawing_structure_serializes_verdict():
    """Round-trip through pydantic serialization must preserve the verdict."""
    s = DrawingStructure(
        patent_id="US1",
        page_number=1,
        structure_index=0,
        is_markush=True,
        markush_scope_verdict=MarkushScopeVerdict(verdict="in_scope", confidence=0.9, tool_calls=3),
    )
    dumped = s.model_dump()
    assert dumped["markush_scope_verdict"]["verdict"] == "in_scope"
    restored = DrawingStructure.model_validate(dumped)
    assert restored.markush_scope_verdict is not None
    assert restored.markush_scope_verdict.verdict == "in_scope"
    assert restored.markush_scope_verdict.tool_calls == 3
