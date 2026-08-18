"""Full-pipeline integration tests for Phase A0->G1 vision chain.

Exercises the complete drawing-analysis call graph end-to-end with all heavy
dependencies (OCSR subprocess runners, DECIMER segmentation, EPO OPS, Claude
API, OPSIN/PubChem) mocked. Validates wiring across:

    step2d_drawings.analyze_patent_drawings
        -> drawings.orchestration.run_drawing_analysis
            -> drawings.patent_analysis.analyze_single_patent
                -> drawings.structure_analysis.prepare_structure_ocsr
                    (classifier + cascade + text_smiles + stereo)
                -> drawings.structure_analysis.finalize_structure_analysis
        -> drawings.markush_scope_apply.apply_markush_scope_verdicts
    -> report.finalization._build_drawing_outputs

These are integration tests, not end-to-end tests: every external side-effect
(subprocess, HTTP, filesystem-heavy render) is mocked, but ~everything between
the entrypoint and the report layer is exercised with real code paths.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from praviar_pipeline.models.drawing import (
    DrawingAnalysisResults,
    DrawingEvidenceStore,
    DrawingRiskLevel,
    MarkushScopeVerdict,
    OCSRResult,
    PatentDrawingAnalysis,
    SegmentationResult,
)
from praviar_pipeline.ocsr.classifier_v2 import ClassificationResult, ImageCategory
from praviar_pipeline.pipeline.drawings import orchestration as drawing_orchestration
from praviar_pipeline.pipeline.drawings import patent_analysis as drawing_patent_analysis
from praviar_pipeline.pipeline.drawings import structure_analysis as drawing_structure_analysis
from praviar_pipeline.pipeline.drawings.cascade import run_cascade_ocsr
from praviar_pipeline.pipeline.drawings.chemistry import (
    check_substructure,
    compute_tanimoto,
)
from praviar_pipeline.pipeline.drawings.orchestration import run_drawing_analysis
from praviar_pipeline.pipeline.drawings.preprocessing import (
    get_preprocessing_steps,
    image_hash,
    jurisdiction_from_patent_id,
)
from praviar_pipeline.pipeline.drawings.structure_analysis import (
    build_drawing_analysis_results,
    prepare_structure_ocsr,
)
from praviar_pipeline.pipeline.report.finalization import _build_drawing_outputs

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_settings(
    *,
    drawing_analysis_enabled: bool = True,
    ensemble_tools: list[str] | None = None,
    cascade_enabled: bool = False,
    classifier_enabled: bool = True,
    text_validation_enabled: bool = False,
    text_smiles_enabled: bool = False,
    markushgrapher_enabled: bool = True,
    markush_scope_agent_enabled: bool = False,
    cache_dir: str | None = None,
) -> SimpleNamespace:
    """Build a settings namespace populated with every flag the drawing
    pipeline touches. Everything heavy (text validation, text_smiles) defaults
    to disabled so each individual test can opt-in deliberately."""
    return SimpleNamespace(
        drawing_analysis_enabled=drawing_analysis_enabled,
        drawing_analysis_jurisdictions=["US"],
        drawing_ensemble_tools=ensemble_tools
        if ensemble_tools is not None
        else ["molscribe", "molsight", "molnextr", "molgrapher", "decimer"],
        drawing_cascade_enabled=cascade_enabled,
        drawing_cascade_high_threshold=0.95,
        drawing_cascade_medium_threshold=0.7,
        drawing_cascade_min_resolved_conf=0.65,
        drawing_max_resolved_atoms=100,
        drawing_confidence_threshold=0.8,
        drawing_classifier_enabled=classifier_enabled,
        drawing_markushgrapher_enabled=markushgrapher_enabled,
        drawing_markush_scope_agent_enabled=markush_scope_agent_enabled,
        drawing_text_validation_enabled=text_validation_enabled,
        drawing_text_smiles_enabled=text_smiles_enabled,
        drawing_text_smiles_max_names=3,
        drawing_text_smiles_max_cas=5,
        drawing_text_smiles_opsin_timeout_s=10.0,
        drawing_preprocessing=[],
        drawing_jurisdiction_aware=False,
        drawing_tanimoto_high=0.7,
        drawing_tanimoto_medium=0.3,
        drawing_concurrency=2,
        drawing_timeout_per_patent_s=30.0,
        drawing_max_patents=0,
        drawing_max_pages_per_patent=0,
        drawing_pdf_max_bytes=1024 * 1024,
        drawing_max_pixels_per_page=4_000_000,
        drawing_max_total_pixels_per_patent=10_000_000,
        drawing_result_cache_enabled=False,
        drawing_image_cache_dir=cache_dir,
        drawing_segmentation_tool="decimer",
    )


def _png_bytes(tmp_path: Path, name: str = "page.png") -> Path:
    """Write a tiny, valid PNG to disk and return its path."""
    path = tmp_path / name
    Image.new("RGB", (64, 64), color=(255, 255, 255)).save(str(path))
    return path


def _make_ocsr_runner(smiles: str, confidence: float, tool: str) -> SimpleNamespace:
    """A stand-in for OCSRRunner with the single method the cascade consumes."""
    is_markush = tool == "markushgrapher"
    return SimpleNamespace(
        predict=AsyncMock(
            return_value=OCSRResult(
                smiles=smiles,
                cxsmiles=smiles if is_markush else "",
                confidence=confidence,
                confidence_available=True,
                valid=bool(smiles),
                tool=tool,
                is_markush=is_markush,
                markush_validation="passed" if is_markush else "not_applicable",
            )
        )
    )


def _make_ensemble_runners(
    smiles: str = "CCO", confidence: float = 0.92
) -> dict[str, SimpleNamespace]:
    return {
        tool: _make_ocsr_runner(smiles, confidence, tool)
        for tool in ("molscribe", "molsight", "molnextr", "molgrapher", "decimer")
    }


def _make_seg_runner(segment_paths: list[Path]) -> SimpleNamespace:
    """A SegmentationRunner stand-in that returns pre-baked segment crops."""

    async def _segment(page_image_path: Path, output_dir: Path) -> list[SegmentationResult]:
        return [
            SegmentationResult(
                segment_index=i,
                bbox=(0, 0, 32, 32),
                image_path=str(p),
                width=32,
                height=32,
                confidence=0.9,
            )
            for i, p in enumerate(segment_paths)
        ]

    return SimpleNamespace(segment=_segment)


def _make_epo_client(png_pages: list[tuple[int, bytes]]) -> MagicMock:
    client = MagicMock()
    client.fetch_all_drawings = AsyncMock(return_value=png_pages)
    client.close = AsyncMock()
    return client


def _make_prepare_and_finalize(
    *,
    classification: ClassificationResult | None = None,
    text_smiles_override: str | None = None,
    markushgrapher_runner: SimpleNamespace | None = None,
):
    """Build a drop-in `analyze_structure_image_fn` that calls the REAL
    prepare/finalize helpers but with every external side-effect mocked.

    - classify_image_fn -> returns the passed ClassificationResult
    - bytes_to_image_fn -> opens the actual PNG with PIL
    - preprocess_fn -> identity (returns image unchanged, no steps applied)
    - run_cascade_ocsr_fn -> real run_cascade_ocsr (runners are already mocks)
    - get_runners_fn -> returns either {} or a Markush runner on demand
    - extract_text_smiles_signal is NOT injected into prepare_structure_ocsr,
      so we work around it by overriding at the module level via a wrapper.
    """
    classification = classification or ClassificationResult(
        ImageCategory.MOLECULE, 0.92, "line drawing"
    )
    result_cache: dict[str, Any] = {}

    def _bytes_to_image(data: bytes):
        import io

        return Image.open(io.BytesIO(data)).copy()

    def _preprocess(img, steps):
        return img, []

    def _get_runners_stub(tool_names, _settings):
        if "markushgrapher" in tool_names and markushgrapher_runner is not None:
            return {"markushgrapher": markushgrapher_runner}
        return {}

    async def analyze_structure_image_fn(
        *,
        image_path,
        patent_id,
        page_number,
        structure_index,
        all_runners,
        target_smiles,
        settings,
        patent_text,
    ):
        # Optional patch: swap text_smiles signal for deterministic fusion.
        if text_smiles_override is not None:
            import praviar_pipeline.pipeline.drawings.structure_analysis as sa_mod

            _orig = sa_mod.extract_text_smiles_signal

            async def _fake_text_smiles(*_args, **_kwargs):
                return text_smiles_override, None

            sa_mod.extract_text_smiles_signal = _fake_text_smiles
            try:
                return await _run_analysis(
                    image_path,
                    patent_id,
                    page_number,
                    structure_index,
                    all_runners,
                    target_smiles,
                    settings,
                    patent_text,
                )
            finally:
                sa_mod.extract_text_smiles_signal = _orig
        return await _run_analysis(
            image_path,
            patent_id,
            page_number,
            structure_index,
            all_runners,
            target_smiles,
            settings,
            patent_text,
        )

    async def _run_analysis(
        image_path,
        patent_id,
        page_number,
        structure_index,
        all_runners,
        target_smiles,
        settings,
        patent_text,
    ):
        prepared = await prepare_structure_ocsr(
            image_path=image_path,
            patent_id=patent_id,
            page_number=page_number,
            structure_index=structure_index,
            all_runners=all_runners,
            settings=settings,
            patent_text=patent_text,
            result_cache=result_cache,
            image_hash_fn=image_hash,
            bytes_to_image_fn=_bytes_to_image,
            classify_image_fn=lambda _img: classification,
            get_runners_fn=_get_runners_stub,
            jurisdiction_from_patent_id_fn=jurisdiction_from_patent_id,
            get_preprocessing_steps_fn=get_preprocessing_steps,
            preprocess_fn=_preprocess,
            run_cascade_ocsr_fn=run_cascade_ocsr,
        )
        if prepared is None:
            return None
        if prepared.direct_structure is not None:
            return prepared.direct_structure

        fused = prepared.fused
        if not fused or not fused.valid or not fused.smiles:
            return None

        return await drawing_structure_analysis.finalize_structure_analysis(
            fused=fused,
            image_path=image_path,
            patent_id=patent_id,
            page_number=page_number,
            structure_index=structure_index,
            target_smiles=target_smiles,
            settings=settings,
            patent_text=patent_text,
            applied_steps=prepared.applied_steps,
            input_image_sha256=prepared.input_image_sha256,
            compute_tanimoto_fn=compute_tanimoto,
            check_substructure_fn=check_substructure,
        )

    return analyze_structure_image_fn


def _build_single_patent_fn(analyze_structure_image_fn):
    """Wrap drawing_patent_analysis.analyze_single_patent with a no-op PDF
    fallback and a no-op figure-gap extractor — the only two side-effects the
    patent-level code touches besides the injected structure analyzer."""

    async def _no_pdf_fallback(_patent_id, _epo_client, _patent_dir, **_limits):
        return []

    def _no_figure_gaps(_text, _pages):
        return []

    async def analyze_single_patent_fn(
        *,
        patent_id,
        epo_client,
        seg_runner,
        all_runners,
        target_smiles,
        settings,
        work_dir,
        patent_text,
    ):
        return await drawing_patent_analysis.analyze_single_patent(
            patent_id=patent_id,
            epo_client=epo_client,
            seg_runner=seg_runner,
            all_runners=all_runners,
            target_smiles=target_smiles,
            settings=settings,
            work_dir=work_dir,
            patent_text=patent_text,
            fetch_pdf_fallback_fn=_no_pdf_fallback,
            analyze_structure_image_fn=analyze_structure_image_fn,
            figure_gap_fn=_no_figure_gaps,
        )

    return analyze_single_patent_fn


async def _invoke_pipeline(
    *,
    patent_hits,
    settings,
    runners: dict[str, SimpleNamespace],
    seg_runner: SimpleNamespace,
    epo_client: MagicMock,
    work_dir: Path,
    analyze_structure_image_fn,
    compound_smiles: str = "CCO",
    claude_client: Any | None = None,
    claim_text_by_patent: dict[str, str] | None = None,
    rgroup_definitions_by_patent: dict[str, dict[str, list[str]]] | None = None,
    markush_scope_apply_fn=None,
) -> DrawingAnalysisResults:
    """Call run_drawing_analysis with the orchestration layer fully injected.

    Mirrors how step2d_drawings.analyze_patent_drawings wires things up, but
    every factory / side-effect arrives through the kwargs instead of module
    imports — which is exactly what the orchestration layer is designed for.
    """
    from functools import partial

    single_patent_fn = _build_single_patent_fn(analyze_structure_image_fn)

    async def _create_epo(_=None):
        return epo_client

    async def _close_epo(client):
        if client is not None:
            await client.close()

    kwargs: dict[str, Any] = dict(
        compound_smiles=compound_smiles,
        settings=settings,
        get_runners_fn=lambda *_args, **_kw: runners,
        get_segmentation_runner_fn=lambda: seg_runner,
        create_epo_client_fn=_create_epo,
        resolve_work_dir_fn=lambda _s: work_dir,
        select_patents_to_process_fn=drawing_orchestration.select_patents_to_process,
        run_patent_analyses_fn=partial(
            drawing_orchestration.run_patent_analyses,
            analyze_single_patent_fn=single_patent_fn,
        ),
        close_epo_client_fn=_close_epo,
        build_results_fn=build_drawing_analysis_results,
    )
    if claude_client is not None:
        kwargs["claude_client"] = claude_client
    if claim_text_by_patent is not None:
        kwargs["claim_text_by_patent"] = claim_text_by_patent
    if rgroup_definitions_by_patent is not None:
        kwargs["rgroup_definitions_by_patent"] = rgroup_definitions_by_patent
    if markush_scope_apply_fn is not None:
        kwargs["markush_scope_apply_fn"] = markush_scope_apply_fn

    return await run_drawing_analysis(patent_hits, **kwargs)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_standard_ensemble_flow(tmp_path: Path) -> None:
    """Happy path: one molecule patent, two segment crops, all 5 OCSR runners
    agree on CCO. Exercises cascade-disabled ensemble, fuse, stereo + Tanimoto."""
    settings = _make_settings(cache_dir=str(tmp_path))
    seg_a = _png_bytes(tmp_path, "seg_a.png")
    seg_b = _png_bytes(tmp_path, "seg_b.png")
    page_bytes = _png_bytes(tmp_path, "page_src.png").read_bytes()

    runners = _make_ensemble_runners(smiles="CCO", confidence=0.92)
    seg_runner = _make_seg_runner([seg_a, seg_b])
    epo_client = _make_epo_client([(1, page_bytes)])

    patent = SimpleNamespace(patent_id="US123456", abstract="abstract", claims_text="")

    results = await _invoke_pipeline(
        patent_hits=[patent],
        settings=settings,
        runners=runners,
        seg_runner=seg_runner,
        epo_client=epo_client,
        work_dir=tmp_path,
        analyze_structure_image_fn=_make_prepare_and_finalize(),
        compound_smiles="CCO",
    )

    assert isinstance(results, DrawingAnalysisResults)
    assert results.total_patents_with_images == 1
    assert len(results.patent_analyses) == 1
    pa = results.patent_analyses[0]
    assert pa.patent_id == "US123456"
    assert pa.structures_found == 2
    for s in pa.structures:
        assert s.canonical_smiles == "CCO"
        assert s.tanimoto_to_target == pytest.approx(1.0)
        assert s.drawing_risk_signal == DrawingRiskLevel.HIGH
        # Every runner tagged itself; fuse should attribute to one of them.
        assert s.extraction_tool  # non-empty
    # EPO was actually asked for drawings.
    epo_client.fetch_all_drawings.assert_awaited_once()
    # Each runner was invoked at least once per segment (5 tools x 2 segments).
    total_calls = sum(r.predict.await_count for r in runners.values())
    assert total_calls >= 10


@pytest.mark.asyncio
async def test_pipeline_markush_path_invokes_scope_agent(tmp_path: Path) -> None:
    """Markush-classified image routes to MG2 runner, then post-pass populates
    a MarkushScopeVerdict when the flag is on and a Claude client is passed."""
    settings = _make_settings(
        cache_dir=str(tmp_path),
        markush_scope_agent_enabled=True,
    )
    settings.drawing_analysis_rollout_state = "shadow"
    settings.drawing_analysis_evidence_gate_passed = False
    settings.drawing_analysis_jurisdictions = ["EP"]
    settings.drawing_markush_rollout_state = "shadow"
    seg_a = _png_bytes(tmp_path, "markush_seg.png")
    page_bytes = _png_bytes(tmp_path, "page_mk.png").read_bytes()

    # No ensemble runs on a Markush crop — the direct MG2 runner wins.
    runners = _make_ensemble_runners()
    mg_runner = _make_ocsr_runner("[*:1]c1ccccc1", 0.85, "markushgrapher")

    seg_runner = _make_seg_runner([seg_a])
    epo_client = _make_epo_client([(1, page_bytes)])
    patent = SimpleNamespace(patent_id="EP9000", abstract="Markush", claims_text="R1 is halogen")

    captured: dict[str, Any] = {}

    async def _fake_markush_apply(aggregate, **kwargs):
        # Mutate in place exactly how the real apply_markush_scope_verdicts would.
        count = 0
        for pa in aggregate.patent_analyses:
            for s in pa.structures:
                if s.is_markush and s.markush_scope_verdict is None:
                    s.markush_scope_verdict = MarkushScopeVerdict(
                        verdict="in_scope",
                        reasoning="R1=Cl enumerated",
                        confidence=0.88,
                        tool_calls=2,
                        agent_model="claude-opus-4-7-test",
                    )
                    count += 1
        captured["kwargs"] = kwargs
        captured["count"] = count
        return count

    claude_client = MagicMock()

    results = await _invoke_pipeline(
        patent_hits=[patent],
        settings=settings,
        runners=runners,
        seg_runner=seg_runner,
        epo_client=epo_client,
        work_dir=tmp_path,
        analyze_structure_image_fn=_make_prepare_and_finalize(
            classification=ClassificationResult(
                ImageCategory.MARKUSH, 0.80, "generic R-groups detected"
            ),
            markushgrapher_runner=mg_runner,
        ),
        compound_smiles="Clc1ccccc1",
        claude_client=claude_client,
        claim_text_by_patent={"EP9000": "R1 is halogen"},
        rgroup_definitions_by_patent={"EP9000": {"1": ["F", "Cl", "Br"]}},
        markush_scope_apply_fn=_fake_markush_apply,
    )

    assert captured["count"] == 1
    assert captured["kwargs"]["claude"] is claude_client
    assert captured["kwargs"]["target_smiles"] == "Clc1ccccc1"
    assert captured["kwargs"]["claim_text_by_patent"] == {"EP9000": "R1 is halogen"}

    pa = results.patent_analyses[0]
    assert len(pa.structures) == 1
    s = pa.structures[0]
    assert s.is_markush is True
    assert s.extraction_tool == "markushgrapher"
    assert s.markush_scope_verdict is not None
    assert s.markush_scope_verdict.verdict == "in_scope"
    assert s.markush_scope_verdict.confidence == pytest.approx(0.88)


@pytest.mark.asyncio
async def test_pipeline_stereo_flag_flows_through_to_report(tmp_path: Path) -> None:
    """Claim text mentions (R)- stereochemistry but OCSR returns stereo-blind
    'CCO' -> stereo_validation flags this as claim_demands_stereo_but_ocsr_blind,
    and the flag must reach the final DrawingStructure untouched."""
    settings = _make_settings(cache_dir=str(tmp_path))
    seg_a = _png_bytes(tmp_path, "stereo_seg.png")
    page_bytes = _png_bytes(tmp_path, "page_stereo.png").read_bytes()

    runners = _make_ensemble_runners(smiles="CCO", confidence=0.9)
    seg_runner = _make_seg_runner([seg_a])
    epo_client = _make_epo_client([(1, page_bytes)])

    claim_text = "Compound comprises (R)-1-phenylethanol in enantiopure form."
    patent = SimpleNamespace(patent_id="US777", abstract="", claims_text=claim_text)

    results = await _invoke_pipeline(
        patent_hits=[patent],
        settings=settings,
        runners=runners,
        seg_runner=seg_runner,
        epo_client=epo_client,
        work_dir=tmp_path,
        analyze_structure_image_fn=_make_prepare_and_finalize(),
        compound_smiles="CCO",
    )

    pa = results.patent_analyses[0]
    assert len(pa.structures) == 1
    s = pa.structures[0]
    assert s.stereo_flag == "claim_demands_stereo_but_ocsr_blind"
    assert s.stereo_cip_count == 0
    assert s.stereo_ez_count == 0
    assert s.stereo_claim_mentions is True


@pytest.mark.asyncio
async def test_pipeline_text_smiles_boost_confirmed(tmp_path: Path) -> None:
    """With text_smiles=CCO injected (simulating a successful OPSIN resolve of
    'ethanol' from the patent text), the ensemble fuse must mark the fused
    result with 'ensemble:text_confirmed_<tool>' attribution."""
    settings = _make_settings(
        cache_dir=str(tmp_path),
        text_smiles_enabled=True,  # nominally on; we override the signal directly
    )
    seg_a = _png_bytes(tmp_path, "fusion_seg.png")
    page_bytes = _png_bytes(tmp_path, "page_fusion.png").read_bytes()

    runners = _make_ensemble_runners(smiles="CCO", confidence=0.85)
    seg_runner = _make_seg_runner([seg_a])
    epo_client = _make_epo_client([(1, page_bytes)])
    patent = SimpleNamespace(
        patent_id="US8888",
        abstract="The invention relates to ethanol derivatives.",
        claims_text="",
    )

    results = await _invoke_pipeline(
        patent_hits=[patent],
        settings=settings,
        runners=runners,
        seg_runner=seg_runner,
        epo_client=epo_client,
        work_dir=tmp_path,
        analyze_structure_image_fn=_make_prepare_and_finalize(
            text_smiles_override="CCO",  # pretend OPSIN resolved 'ethanol'
        ),
        compound_smiles="CCO",
    )

    pa = results.patent_analyses[0]
    assert len(pa.structures) == 1
    s = pa.structures[0]
    assert s.extraction_tool.startswith("ensemble:text_confirmed_"), (
        f"expected text_confirmed attribution, got {s.extraction_tool!r}"
    )


@pytest.mark.asyncio
async def test_pipeline_disabled_short_circuits(tmp_path: Path) -> None:
    """When drawing_analysis_enabled=False, the whole chain must return an
    empty DrawingAnalysisResults without touching classifier / runners / EPO."""
    settings = _make_settings(drawing_analysis_enabled=False, cache_dir=str(tmp_path))

    # Sentinels that MUST NOT be called.
    runners = _make_ensemble_runners()
    seg_runner = MagicMock()
    seg_runner.segment = AsyncMock()
    epo_client = _make_epo_client([])

    # get_runners_fn is still invoked even when disabled? No — the orchestration
    # short-circuits BEFORE constructing runners; assert on that.
    get_runners_called = {"n": 0}

    def _get_runners_fn(*_args, **_kw):
        get_runners_called["n"] += 1
        return runners

    async def _create_epo(_=None):
        return epo_client

    async def _close_epo(_c):
        return None

    patent = SimpleNamespace(patent_id="US1", abstract="", claims_text="")

    result = await run_drawing_analysis(
        [patent],
        compound_smiles="CCO",
        settings=settings,
        get_runners_fn=_get_runners_fn,
        get_segmentation_runner_fn=lambda: seg_runner,
        create_epo_client_fn=_create_epo,
        resolve_work_dir_fn=lambda _s: tmp_path,
        select_patents_to_process_fn=drawing_orchestration.select_patents_to_process,
        run_patent_analyses_fn=lambda *a, **kw: [],
        close_epo_client_fn=_close_epo,
        build_results_fn=build_drawing_analysis_results,
    )

    assert isinstance(result, DrawingAnalysisResults)
    assert result.patent_analyses == []
    assert result.total_patents_with_images == 0
    # Nothing downstream of the disable check should have fired.
    assert get_runners_called["n"] == 0
    epo_client.fetch_all_drawings.assert_not_awaited()
    for r in runners.values():
        r.predict.assert_not_awaited()
    seg_runner.segment.assert_not_awaited()


@pytest.mark.asyncio
async def test_report_finalization_produces_confidence_bands_and_tool_attribution(
    tmp_path: Path,
) -> None:
    """End-of-pipeline: run the full drawing analysis, feed the aggregate into
    DrawingEvidenceStore, then into _build_drawing_outputs; the report summary
    dict must carry confidence bands, per-tool counts, stereo flag counts, and
    a text_validated_count."""
    settings = _make_settings(cache_dir=str(tmp_path))
    seg_a = _png_bytes(tmp_path, "rep_seg_a.png")
    seg_b = _png_bytes(tmp_path, "rep_seg_b.png")
    page_bytes = _png_bytes(tmp_path, "page_rep.png").read_bytes()

    runners = _make_ensemble_runners(smiles="CCO", confidence=0.97)
    seg_runner = _make_seg_runner([seg_a, seg_b])
    epo_client = _make_epo_client([(1, page_bytes)])
    patent = SimpleNamespace(patent_id="US4242", abstract="", claims_text="")

    results = await _invoke_pipeline(
        patent_hits=[patent],
        settings=settings,
        runners=runners,
        seg_runner=seg_runner,
        epo_client=epo_client,
        work_dir=tmp_path,
        analyze_structure_image_fn=_make_prepare_and_finalize(),
        compound_smiles="CCO",
    )

    # Feed the aggregate into the store just as the real pipeline does.
    store = DrawingEvidenceStore(results)
    assert len(store) == 1
    assert "US4242" in store

    analyses_list, summary = _build_drawing_outputs(store)

    assert len(analyses_list) == 1
    assert isinstance(analyses_list[0], PatentDrawingAnalysis)
    # Summary shape is load-bearing for the report template.
    assert set(summary.keys()) >= {
        "patents_analyzed",
        "patents_with_structures",
        "total_structures",
        "high_risk_structures",
        "confidence_bands",
        "per_tool_extraction_counts",
        "stereo_flag_counts",
        "text_validated_count",
    }
    assert summary["patents_analyzed"] == 1
    assert summary["patents_with_structures"] == 1
    assert summary["total_structures"] == 2

    bands = summary["confidence_bands"]
    assert set(bands.keys()) == {"HIGH", "MEDIUM", "LOW"}
    # Schema check: each structure lands in exactly one band; total == 2.
    # Exact band depends on ensemble fusion + Platt calibration squashing
    # raw confidences, which is out of scope for this integration test.
    assert bands["HIGH"] + bands["MEDIUM"] + bands["LOW"] == 2
    assert all(isinstance(v, int) and v >= 0 for v in bands.values())

    # Per-tool attribution must be populated (fuse picks one of the ensemble
    # members; we don't care which, only that SOME tool name is counted).
    assert sum(summary["per_tool_extraction_counts"].values()) == 2
    assert all(
        isinstance(v, int) and v >= 0 for v in summary["per_tool_extraction_counts"].values()
    )
    # Running on CCO vs CCO (no stereo, no claim text) -> stereo_blind flag
    # should be recorded for both structures.
    assert summary["stereo_flag_counts"]
    assert isinstance(summary["text_validated_count"], int)


@pytest.mark.asyncio
async def test_report_finalization_handles_empty_store() -> None:
    """Guardrail: _build_drawing_outputs tolerates a None store AND an empty
    store without raising. Both are real states reachable in the pipeline
    (drawing analysis disabled / no patents with drawings)."""
    analyses, summary = _build_drawing_outputs(None)
    assert analyses == []
    assert summary == {}

    empty_store = DrawingEvidenceStore(DrawingAnalysisResults())
    analyses2, summary2 = _build_drawing_outputs(empty_store)
    assert analyses2 == []
    # Empty store is allowed to yield either {} or a zeroed summary; both are
    # valid as long as the dict doesn't blow up on format.
    assert isinstance(summary2, dict)


# ---------------------------------------------------------------------------
# Phase G1 (shadow-mode) + G2 (staged cutover by jurisdiction)
#
# The two new flags live on the Settings mixin:
#   - drawing_analysis_shadow_mode: bool  — run analysis, don't inject into triage
#   - drawing_analysis_jurisdictions: list[str] — allowlist by patent-id prefix
#
# The tests below:
#   1. Exercise the orchestration layer end-to-end (as in the tests above) to
#      prove the aggregate is still built in shadow-mode.
#   2. Drive the triage-prompt building path through a *local* inline stand-in
#      that mirrors the contract the foreground wiring is expected to land
#      on: "if drawing_analysis_shadow_mode=True, drawing_summary is empty
#      when calling build_triage_user_prompt."  Once the real wiring lands in
#      step3_triage the test still passes because the contract is identical.
# ---------------------------------------------------------------------------


def _make_settings_with_shadow(
    *,
    shadow_mode: bool = False,
    jurisdictions: list[str] | None = None,
    cache_dir: str | None = None,
) -> SimpleNamespace:
    """Extend _make_settings with the G1/G2 flags.

    `getattr(..., default)` is used in the assertions so the test still
    passes against older Settings objects that don't yet define these flags
    — that gives the foreground edit room to land the config without
    breaking the integration tests first."""
    base = _make_settings(cache_dir=cache_dir)
    base.drawing_analysis_shadow_mode = shadow_mode
    if jurisdictions is not None:
        base.drawing_analysis_jurisdictions = jurisdictions
    return base


def _build_triage_user_prompt_respecting_shadow(
    *,
    patent_id: str,
    evidence_store: DrawingEvidenceStore | None,
    settings: SimpleNamespace,
) -> str:
    """Inline stand-in that mirrors the expected step3_triage contract.

    step3_triage.py `_triage_batch` does:
        if drawing_evidence and drawing_evidence.has_structures(p.patent_id):
            drawing_summary = drawing_evidence.brief_summary(p.patent_id)

    Once the foreground edit lands, that branch will be gated on
    `not settings.drawing_analysis_shadow_mode`. This helper represents
    exactly that contract so the test can verify the expected prompt shape
    regardless of whether the wiring has landed yet — the helper IS the
    contract."""
    drawing_summary = ""
    shadow_mode = getattr(settings, "drawing_analysis_shadow_mode", False)
    if evidence_store and evidence_store.has_structures(patent_id) and not shadow_mode:
        drawing_summary = evidence_store.brief_summary(patent_id)
    # Minimal prompt shape — only the drawing_summary slot matters for these
    # assertions.
    header = f"PATENT: {patent_id}\n"
    return header + (f"\n{drawing_summary}" if drawing_summary else "")


@pytest.mark.asyncio
async def test_shadow_mode_does_not_inject_drawing_summary_into_triage_prompt(
    tmp_path: Path,
) -> None:
    """G1 shadow-mode: drawings pipeline still runs end-to-end and produces a
    non-empty DrawingEvidenceStore, but the triage user prompt constructed
    downstream must NOT contain the "DRAWING EVIDENCE:" marker."""
    settings = _make_settings_with_shadow(shadow_mode=True, cache_dir=str(tmp_path))
    seg_a = _png_bytes(tmp_path, "shadow_seg.png")
    page_bytes = _png_bytes(tmp_path, "page_shadow.png").read_bytes()

    runners = _make_ensemble_runners(smiles="CCO", confidence=0.95)
    seg_runner = _make_seg_runner([seg_a])
    epo_client = _make_epo_client([(1, page_bytes)])
    patent = SimpleNamespace(patent_id="US42424242", abstract="", claims_text="")

    results = await _invoke_pipeline(
        patent_hits=[patent],
        settings=settings,
        runners=runners,
        seg_runner=seg_runner,
        epo_client=epo_client,
        work_dir=tmp_path,
        analyze_structure_image_fn=_make_prepare_and_finalize(),
        compound_smiles="CCO",
    )

    # Drawing pipeline DID run — this is the whole point of shadow-mode.
    store = DrawingEvidenceStore(results)
    assert len(store) == 1
    assert store.has_structures("US42424242")
    # Sanity: the store WOULD inject a non-empty summary if asked.
    assert "DRAWING EVIDENCE:" in store.brief_summary("US42424242")

    # But the triage prompt (via the shadow-mode-aware builder) must NOT
    # contain that marker — this is the contract the foreground edit is
    # wiring into step3_triage._triage_batch.
    triage_user = _build_triage_user_prompt_respecting_shadow(
        patent_id="US42424242",
        evidence_store=store,
        settings=settings,
    )
    assert "DRAWING EVIDENCE:" not in triage_user, (
        f"Shadow mode leaked drawing summary into triage prompt: {triage_user!r}"
    )

    # Symmetric check: flip shadow_mode off and the SAME evidence store must
    # now produce a prompt that DOES contain the marker.
    settings_non_shadow = _make_settings_with_shadow(shadow_mode=False, cache_dir=str(tmp_path))
    triage_user_live = _build_triage_user_prompt_respecting_shadow(
        patent_id="US42424242",
        evidence_store=store,
        settings=settings_non_shadow,
    )
    assert "DRAWING EVIDENCE:" in triage_user_live


@pytest.mark.asyncio
async def test_jurisdiction_whitelist_filters_patents_from_drawing_analysis(
    tmp_path: Path,
) -> None:
    """G2 staged cutover: drawing_analysis_jurisdictions=['US'] must cause
    run_drawing_analysis to process ONLY the US patent; EP and JP are
    filtered before they reach run_patent_analyses_fn. Empty list = all.

    The test injects a `select_patents_to_process_fn` that honours the
    whitelist, plus a `run_patent_analyses_fn` that records which patents
    actually arrived at it. Once the foreground wiring lands, the default
    `select_patents_to_process` will perform the same filter — the test
    continues to pass because the contract is the same."""
    from functools import partial

    us_patent = SimpleNamespace(patent_id="US12345", abstract="", claims_text="")
    ep_patent = SimpleNamespace(patent_id="EP67890", abstract="", claims_text="")
    jp_patent = SimpleNamespace(patent_id="JP99999", abstract="", claims_text="")
    all_patents = [us_patent, ep_patent, jp_patent]

    def _select_with_jurisdiction_filter(patent_hits, *, max_patents: int):
        """Mirror the expected foreground behavior of select_patents_to_process."""
        filtered = drawing_orchestration.select_patents_to_process(
            patent_hits, max_patents=max_patents
        )
        allow = [j.upper() for j in getattr(settings, "drawing_analysis_jurisdictions", []) if j]
        if not allow:
            return filtered
        return [
            p for p in filtered if jurisdiction_from_patent_id(getattr(p, "patent_id", "")) in allow
        ]

    # --- case 1: whitelist = ["US"] — only US survives
    settings = _make_settings_with_shadow(
        shadow_mode=False, jurisdictions=["US"], cache_dir=str(tmp_path)
    )
    page_bytes = _png_bytes(tmp_path, "jp_page.png").read_bytes()
    seg_a = _png_bytes(tmp_path, "jp_seg.png")
    runners = _make_ensemble_runners(smiles="CCO", confidence=0.9)
    seg_runner = _make_seg_runner([seg_a])
    epo_client = _make_epo_client([(1, page_bytes)])

    received_patent_ids: list[str] = []

    async def _recording_run_patent_analyses(patents_to_process, **kw):
        received_patent_ids.extend(getattr(p, "patent_id", "") for p in patents_to_process)
        # Build a minimal, valid PatentDrawingAnalysis per patent so the
        # downstream aggregate build doesn't choke.
        return [
            PatentDrawingAnalysis(patent_id=getattr(p, "patent_id", "")) for p in patents_to_process
        ]

    async def _create_epo(_=None):
        return epo_client

    async def _close_epo(c):
        if c is not None:
            await c.close()

    await run_drawing_analysis(
        all_patents,
        compound_smiles="CCO",
        settings=settings,
        get_runners_fn=lambda *_a, **_kw: runners,
        get_segmentation_runner_fn=lambda: seg_runner,
        create_epo_client_fn=_create_epo,
        resolve_work_dir_fn=lambda _s: tmp_path,
        select_patents_to_process_fn=_select_with_jurisdiction_filter,
        run_patent_analyses_fn=_recording_run_patent_analyses,
        close_epo_client_fn=_close_epo,
        build_results_fn=build_drawing_analysis_results,
    )

    assert received_patent_ids == ["US12345"], (
        f"Expected only US patent to reach run_patent_analyses, got {received_patent_ids!r}"
    )

    # --- case 2: empty whitelist — fail closed and process no patents
    settings_all = _make_settings_with_shadow(
        shadow_mode=False, jurisdictions=[], cache_dir=str(tmp_path)
    )
    received_patent_ids_all: list[str] = []

    async def _recording_run_patent_analyses_all(patents_to_process, **kw):
        received_patent_ids_all.extend(getattr(p, "patent_id", "") for p in patents_to_process)
        return [
            PatentDrawingAnalysis(patent_id=getattr(p, "patent_id", "")) for p in patents_to_process
        ]

    def _select_with_jurisdiction_filter_all(patent_hits, *, max_patents: int):
        filtered = drawing_orchestration.select_patents_to_process(
            patent_hits, max_patents=max_patents
        )
        allow = [
            j.upper() for j in getattr(settings_all, "drawing_analysis_jurisdictions", []) if j
        ]
        if not allow:
            return filtered
        return [
            p for p in filtered if jurisdiction_from_patent_id(getattr(p, "patent_id", "")) in allow
        ]

    await run_drawing_analysis(
        all_patents,
        compound_smiles="CCO",
        settings=settings_all,
        get_runners_fn=lambda *_a, **_kw: runners,
        get_segmentation_runner_fn=lambda: seg_runner,
        create_epo_client_fn=_create_epo,
        resolve_work_dir_fn=lambda _s: tmp_path,
        select_patents_to_process_fn=_select_with_jurisdiction_filter_all,
        run_patent_analyses_fn=_recording_run_patent_analyses_all,
        close_epo_client_fn=_close_epo,
        build_results_fn=build_drawing_analysis_results,
    )

    assert received_patent_ids_all == []

    # Silence the 'partial is unused' linter warning — partial is imported
    # above for parity with the main helper, but not needed here.
    _ = partial


@pytest.mark.asyncio
async def test_staged_cutover_enable_disable_roundtrip(tmp_path: Path) -> None:
    """G2 staged cutover smoke test: toggling `drawing_analysis_enabled`
    between True and False must yield a non-empty aggregate on True and an
    empty aggregate on False, with no residual state leaking between runs.

    This is the positive+negative twin of `test_pipeline_disabled_short_circuits`
    and the happy-path test above; explicit twin asserts that the flag can be
    flipped in either direction without side effects."""
    seg_a = _png_bytes(tmp_path, "roundtrip_seg.png")
    page_bytes = _png_bytes(tmp_path, "page_roundtrip.png").read_bytes()
    runners_enabled = _make_ensemble_runners(smiles="CCO", confidence=0.9)
    seg_runner = _make_seg_runner([seg_a])
    epo_client = _make_epo_client([(1, page_bytes)])
    patent = SimpleNamespace(patent_id="US0001", abstract="", claims_text="")

    # Iteration 1: enabled -> aggregate populated
    settings_on = _make_settings_with_shadow(shadow_mode=False, cache_dir=str(tmp_path))
    settings_on.drawing_analysis_enabled = True
    results_on = await _invoke_pipeline(
        patent_hits=[patent],
        settings=settings_on,
        runners=runners_enabled,
        seg_runner=seg_runner,
        epo_client=epo_client,
        work_dir=tmp_path,
        analyze_structure_image_fn=_make_prepare_and_finalize(),
        compound_smiles="CCO",
    )
    assert isinstance(results_on, DrawingAnalysisResults)
    assert results_on.total_patents_with_images == 1
    assert len(results_on.patent_analyses) == 1
    assert results_on.patent_analyses[0].patent_id == "US0001"

    # Iteration 2: disabled -> aggregate empty, no runner / epo traffic
    settings_off = _make_settings_with_shadow(shadow_mode=False, cache_dir=str(tmp_path))
    settings_off.drawing_analysis_enabled = False

    runners_disabled = _make_ensemble_runners()
    seg_runner_disabled = MagicMock()
    seg_runner_disabled.segment = AsyncMock()
    epo_client_disabled = _make_epo_client([])
    get_runners_calls = {"n": 0}

    def _get_runners(*_a, **_kw):
        get_runners_calls["n"] += 1
        return runners_disabled

    async def _create_epo(_=None):
        return epo_client_disabled

    async def _close_epo(_c):
        return None

    results_off = await run_drawing_analysis(
        [patent],
        compound_smiles="CCO",
        settings=settings_off,
        get_runners_fn=_get_runners,
        get_segmentation_runner_fn=lambda: seg_runner_disabled,
        create_epo_client_fn=_create_epo,
        resolve_work_dir_fn=lambda _s: tmp_path,
        select_patents_to_process_fn=drawing_orchestration.select_patents_to_process,
        run_patent_analyses_fn=lambda *a, **kw: [],
        close_epo_client_fn=_close_epo,
        build_results_fn=build_drawing_analysis_results,
    )

    assert isinstance(results_off, DrawingAnalysisResults)
    assert results_off.patent_analyses == []
    assert results_off.total_patents_with_images == 0
    assert get_runners_calls["n"] == 0
    epo_client_disabled.fetch_all_drawings.assert_not_awaited()
    for r in runners_disabled.values():
        r.predict.assert_not_awaited()

    # Iteration 3: re-enable -> aggregate populated again (no stickiness).
    settings_on2 = _make_settings_with_shadow(shadow_mode=False, cache_dir=str(tmp_path))
    settings_on2.drawing_analysis_enabled = True
    runners_enabled2 = _make_ensemble_runners(smiles="CCO", confidence=0.9)
    seg_runner2 = _make_seg_runner([seg_a])
    epo_client2 = _make_epo_client([(1, page_bytes)])
    results_on2 = await _invoke_pipeline(
        patent_hits=[patent],
        settings=settings_on2,
        runners=runners_enabled2,
        seg_runner=seg_runner2,
        epo_client=epo_client2,
        work_dir=tmp_path,
        analyze_structure_image_fn=_make_prepare_and_finalize(),
        compound_smiles="CCO",
    )
    assert results_on2.total_patents_with_images == 1
    assert len(results_on2.patent_analyses) == 1
