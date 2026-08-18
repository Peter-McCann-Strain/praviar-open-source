from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

from praviar_pipeline.models.drawing import DrawingAnalysisResults, PatentDrawingAnalysis
from praviar_pipeline.pipeline.runtime.search_enrichment import (
    run_claims_enrichment,
    run_post_search_enrichment,
    run_post_triage_drawing_enrichment,
)


async def test_run_post_search_enrichment_returns_early_when_no_work_needed() -> None:
    make_timing = MagicMock()

    patent_hits, changed = await run_post_search_enrichment(
        completed_step=5,
        patent_hits=["US1"],
        timing_data=[],
        make_timing=make_timing,
    )

    assert patent_hits == ["US1"]
    assert changed is False
    make_timing.assert_not_called()


async def test_run_post_search_enrichment_runs_families_only(monkeypatch) -> None:
    families_module = ModuleType("praviar_pipeline.pipeline.step2c_families")

    async def fake_expand_and_select_families(patent_hits):
        assert patent_hits == ["US1"]
        return ["US1-family"]

    families_module.expand_and_select_families = fake_expand_and_select_families
    monkeypatch.setitem(
        sys.modules,
        "praviar_pipeline.pipeline.step2c_families",
        families_module,
    )

    timing_data = []
    patent_hits, changed = await run_post_search_enrichment(
        completed_step=2,
        patent_hits=["US1"],
        timing_data=timing_data,
        make_timing=lambda step, _start, before, after: (step, before, after),
    )

    assert patent_hits == ["US1-family"]
    assert changed is True
    assert ("step2c_families", 1, 1) in timing_data


async def test_run_post_triage_drawing_enrichment(monkeypatch) -> None:
    drawings_module = ModuleType("praviar_pipeline.pipeline.step2d_drawings")
    notify_calls = []

    async def fake_analyze_patent_drawings(patent_hits, canonical_smiles, settings):
        assert patent_hits == ["US1"]
        assert canonical_smiles == "CCO"
        assert settings.drawing_analysis_enabled is True
        return DrawingAnalysisResults(
            patent_analyses=[
                PatentDrawingAnalysis(
                    patent_id="US1",
                    pages_with_structures=1,
                    structures_found=1,
                )
            ],
            total_patents_with_images=1,
            total_structures_extracted=1,
            total_high_risk_structures=0,
        )

    drawings_module.analyze_patent_drawings = fake_analyze_patent_drawings
    monkeypatch.setitem(
        sys.modules,
        "praviar_pipeline.pipeline.step2d_drawings",
        drawings_module,
    )

    timing_data = []
    evidence = await run_post_triage_drawing_enrichment(
        patent_hits=["US1"],
        compound=SimpleNamespace(canonical_smiles="CCO"),
        settings=SimpleNamespace(drawing_analysis_enabled=True),
        timing_data=timing_data,
        notify=lambda *args: notify_calls.append(args),
        make_timing=lambda step, _start, before, after: (step, before, after),
    )

    assert evidence.has_structures("US1") is True
    assert ("step2d_drawings", 1, 1) in timing_data
    assert notify_calls[0][:3] == (2, "drawings", "started")
    assert notify_calls[1][:3] == (2, "drawings", "completed")


async def test_run_claims_enrichment_invokes_step_when_needed(monkeypatch) -> None:
    families_module = ModuleType("praviar_pipeline.pipeline.step2c_families")
    claims_calls = []
    biblio_calls = []

    async def fake_enrich_claims_text(patent_hits):
        claims_calls.append(patent_hits)
        return 2

    async def fake_enrich_biblio_from_epo_ops(patent_hits):
        biblio_calls.append(patent_hits)
        return 1

    families_module.enrich_claims_text = fake_enrich_claims_text
    families_module.enrich_biblio_from_epo_ops = fake_enrich_biblio_from_epo_ops
    monkeypatch.setitem(
        sys.modules,
        "praviar_pipeline.pipeline.step2c_families",
        families_module,
    )

    await run_claims_enrichment(completed_step=4, patent_hits=["US1", "US2"])
    await run_claims_enrichment(completed_step=6, patent_hits=["US3"])
    await run_claims_enrichment(completed_step=1, patent_hits=[])

    assert claims_calls == [["US1", "US2"]]
    assert biblio_calls == [["US1", "US2"]]
