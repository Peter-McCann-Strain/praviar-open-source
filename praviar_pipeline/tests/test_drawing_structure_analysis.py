from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from praviar_pipeline.errors import DrawingAnalysisError
from praviar_pipeline.models.drawing import DrawingRiskLevel, DrawingStructure, OCSRResult
from praviar_pipeline.ocsr.classifier_v2 import ImageCategory
from praviar_pipeline.ocsr.runner import OCSROutputError
from praviar_pipeline.pipeline.drawings.structure_analysis import (
    finalize_structure_analysis,
    prepare_structure_ocsr,
)
from praviar_pipeline.pipeline.drawings.structure_analysis_helpers import (
    aggregate_drawing_analysis_results,
    build_drawing_analysis_results,
    build_final_drawing_structure,
    build_markush_prepared_structure,
    build_patent_drawing_analysis,
    compute_risk_level,
    extract_text_formula_signal,
    summarize_patent_drawing_analysis,
)
from praviar_pipeline.pipeline.step2d_drawings import (
    _analyze_structure_image,
    _image_hash,
    _result_cache,
)


def _drawing_settings() -> MagicMock:
    settings = MagicMock()
    settings.drawing_result_cache_enabled = False
    settings.drawing_analysis_rollout_state = "shadow"
    settings.drawing_classifier_enabled = True
    settings.drawing_analysis_jurisdictions = ["US"]
    settings.drawing_markushgrapher_enabled = False
    settings.drawing_jurisdiction_aware = False
    settings.drawing_preprocessing = []
    settings.drawing_cascade_high_threshold = 0.95
    settings.drawing_cascade_medium_threshold = 0.7
    settings.drawing_cascade_min_resolved_conf = 0.65
    settings.drawing_max_resolved_atoms = 100
    settings.drawing_confidence_threshold = 0.5
    settings.drawing_cascade_enabled = True
    settings.drawing_text_validation_enabled = False
    settings.drawing_tanimoto_high = 0.7
    settings.drawing_tanimoto_medium = 0.3
    settings.drawing_timeout_per_patent_s = 30
    return settings


class _FakeImage:
    def save(self, target, **_kwargs) -> None:
        target.write(b"prep")


@pytest.mark.asyncio
async def test_finalize_structure_analysis_builds_expected_fields(tmp_path) -> None:
    image_path = tmp_path / "segment.png"
    image_path.write_bytes(b"segment")
    settings = _drawing_settings()
    settings.drawing_text_validation_enabled = True
    fused = OCSRResult(smiles="CCO", confidence=0.91, valid=True, tool="molscribe")
    text_result = SimpleNamespace(
        validated=True,
        method="pubchem_lookup",
        details="matched expected formula",
    )

    with (
        patch(
            "praviar_pipeline.ocsr.postprocessing.postprocess",
            return_value=("CCO", ["canonicalise"]),
        ),
        patch(
            "praviar_pipeline.ocsr.text_validation.validate_against_text",
            new=AsyncMock(return_value=text_result),
        ),
        patch("praviar_pipeline.ocsr.postprocessing.to_inchi_key", return_value="TEST-INCHI"),
    ):
        structure = await finalize_structure_analysis(
            fused=fused,
            image_path=image_path,
            patent_id="US123",
            page_number=2,
            structure_index=5,
            target_smiles="CCCO",
            settings=settings,
            patent_text="Formula C2H6O",
            applied_steps=["clahe"],
            input_image_sha256="a" * 64,
            compute_tanimoto_fn=lambda _left, _right: 0.8123,
            check_substructure_fn=MagicMock(side_effect=[True, False]),
        )

    assert structure.canonical_smiles == "CCO"
    assert structure.inchi_key == "TEST-INCHI"
    assert structure.preprocessing_applied == ["clahe"]
    assert structure.postprocessing_applied == ["canonicalise"]
    assert structure.pubchem_match is True
    assert structure.tanimoto_to_target == 0.8123
    assert structure.is_substructure_of_target is True
    assert structure.target_is_substructure is False
    assert structure.drawing_risk_signal == DrawingRiskLevel.HIGH
    assert structure.cropped_structure_image == str(image_path)
    assert structure.input_image_sha256 == "a" * 64


@pytest.mark.asyncio
async def test_non_chemical_classifier_cannot_preempt_ocsr(tmp_path) -> None:
    image_path = tmp_path / "segment.png"
    image_path.write_bytes(b"segment")
    settings = _drawing_settings()
    classification = SimpleNamespace(
        category=ImageCategory.NON_CHEMICAL,
        confidence=0.99,
        reason="diagram",
    )

    cascade = AsyncMock(return_value=OCSRResult(smiles="CCO", confidence=0.9, valid=True))
    prepared = await prepare_structure_ocsr(
        image_path=image_path,
        patent_id="US123",
        page_number=1,
        structure_index=0,
        all_runners={},
        settings=settings,
        patent_text="",
        result_cache={},
        image_hash_fn=lambda _value: "hash",
        bytes_to_image_fn=lambda _value: _FakeImage(),
        classify_image_fn=lambda _value: classification,
        get_runners_fn=lambda _names, _settings: {},
        jurisdiction_from_patent_id_fn=lambda _pid: "US",
        get_preprocessing_steps_fn=lambda _jurisdiction, _settings: [],
        preprocess_fn=lambda image, _steps: (image, []),
        run_cascade_ocsr_fn=cascade,
    )

    assert prepared is not None
    assert prepared.fused is not None
    cascade.assert_awaited_once()


@pytest.mark.asyncio
async def test_molparser_markush_result_routes_to_drawing_structure(tmp_path) -> None:
    image_path = tmp_path / "segment.png"
    image_path.write_bytes(b"segment")
    settings = _drawing_settings()
    settings.drawing_classifier_enabled = False
    cxsmiles = "c1ccc([*:1])cc1 |$;;;;R1;;$|"

    prepared = await prepare_structure_ocsr(
        image_path=image_path,
        patent_id="US123",
        page_number=2,
        structure_index=3,
        all_runners={},
        settings=settings,
        patent_text="",
        result_cache={},
        image_hash_fn=lambda _value: "hash",
        bytes_to_image_fn=lambda _value: _FakeImage(),
        classify_image_fn=lambda _value: None,
        get_runners_fn=lambda _names, _settings: {},
        jurisdiction_from_patent_id_fn=lambda _pid: "US",
        get_preprocessing_steps_fn=lambda _jurisdiction, _settings: [],
        preprocess_fn=lambda image, _steps: (image, []),
        run_cascade_ocsr_fn=AsyncMock(
            return_value=OCSRResult(
                smiles=cxsmiles,
                tool="molparser",
                is_markush=True,
                cxsmiles=cxsmiles,
                confidence=0.85,
                confidence_available=True,
                valid=True,
                markush_validation="passed",
            )
        ),
    )

    assert prepared is not None
    assert prepared.fused is None
    assert prepared.direct_structure is not None
    assert prepared.direct_structure.is_markush is True
    assert prepared.direct_structure.markush_cxsmiles == cxsmiles
    assert prepared.direct_structure.extraction_tool == "molparser"


@pytest.mark.asyncio
async def test_analyze_structure_image_uses_cached_fused_result(tmp_path) -> None:
    image_path = tmp_path / "segment.png"
    image_path.write_bytes(b"segment")
    settings = _drawing_settings()
    settings.drawing_result_cache_enabled = True
    cached_result = OCSRResult(smiles="CCO", confidence=0.88, valid=True, tool="cache")
    expected = DrawingStructure(
        patent_id="US123",
        page_number=1,
        structure_index=0,
        canonical_smiles="CCO",
    )
    content_hash = _image_hash(image_path.read_bytes())
    previous_cache = dict(_result_cache)
    _result_cache.clear()
    _result_cache[content_hash] = cached_result

    try:
        with (
            patch(
                "praviar_pipeline.pipeline.step2d_drawings._run_cascade_ocsr",
                new=AsyncMock(),
            ) as cascade_mock,
            patch(
                "praviar_pipeline.pipeline.step2d_drawings.drawing_structure_analysis.finalize_structure_analysis",
                new=AsyncMock(return_value=expected),
            ) as finalize_mock,
        ):
            structure = await _analyze_structure_image(
                image_path=image_path,
                patent_id="US123",
                page_number=1,
                structure_index=0,
                all_runners={},
                target_smiles="CCO",
                settings=settings,
            )
    finally:
        _result_cache.clear()
        _result_cache.update(previous_cache)

    assert structure == expected
    cascade_mock.assert_not_awaited()
    finalize_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_prepare_structure_ocsr_reapplies_current_gates_to_shadow_cache(tmp_path) -> None:
    image_path = tmp_path / "segment.png"
    image_path.write_bytes(b"segment")
    settings = _drawing_settings()
    settings.drawing_result_cache_enabled = True
    settings.drawing_cascade_min_resolved_conf = 0.65
    settings.drawing_max_resolved_atoms = 100
    content_hash = "a" * 64
    cached = OCSRResult(
        smiles="C" * 101,
        confidence=0.99,
        valid=True,
        tool="cached-weak-policy",
    )
    cascade = AsyncMock()

    prepared = await prepare_structure_ocsr(
        image_path=image_path,
        patent_id="US123",
        page_number=1,
        structure_index=0,
        all_runners={},
        settings=settings,
        patent_text="",
        result_cache={content_hash: cached},
        image_hash_fn=lambda _value: content_hash,
        bytes_to_image_fn=lambda _value: _FakeImage(),
        classify_image_fn=lambda _value: None,
        get_runners_fn=lambda _names, _settings: {},
        jurisdiction_from_patent_id_fn=lambda _pid: "US",
        get_preprocessing_steps_fn=lambda _jurisdiction, _settings: [],
        preprocess_fn=lambda image, _steps: (image, []),
        run_cascade_ocsr_fn=cascade,
    )

    assert prepared is None
    cascade.assert_not_awaited()


@pytest.mark.asyncio
async def test_prepare_structure_ocsr_never_reuses_or_populates_cache_in_live_rollout(
    tmp_path,
) -> None:
    image_path = tmp_path / "segment.png"
    image_path.write_bytes(b"segment")
    settings = _drawing_settings()
    settings.drawing_result_cache_enabled = True
    settings.drawing_analysis_rollout_state = "production"
    settings.drawing_classifier_enabled = False
    content_hash = "b" * 64
    cache = {
        content_hash: OCSRResult(
            smiles="C" * 101,
            confidence=0.99,
            valid=True,
            tool="cached-other-governance",
        )
    }
    fresh = OCSRResult(smiles="CCO", confidence=0.91, valid=True, tool="fresh")
    cascade = AsyncMock(return_value=fresh)

    prepared = await prepare_structure_ocsr(
        image_path=image_path,
        patent_id="US123",
        page_number=1,
        structure_index=0,
        all_runners={},
        settings=settings,
        patent_text="",
        result_cache=cache,
        image_hash_fn=lambda _value: content_hash,
        bytes_to_image_fn=lambda _value: _FakeImage(),
        classify_image_fn=lambda _value: None,
        get_runners_fn=lambda _names, _settings: {},
        jurisdiction_from_patent_id_fn=lambda _pid: "US",
        get_preprocessing_steps_fn=lambda _jurisdiction, _settings: [],
        preprocess_fn=lambda image, _steps: (image, []),
        run_cascade_ocsr_fn=cascade,
    )

    assert prepared is not None
    assert prepared.fused == fresh
    cascade.assert_awaited_once()
    assert cache[content_hash].tool == "cached-other-governance"


@pytest.mark.asyncio
async def test_analyze_structure_image_routes_markush_to_markushgrapher(tmp_path) -> None:
    image_path = tmp_path / "segment.png"
    image_path.write_bytes(b"segment")
    settings = _drawing_settings()
    settings.drawing_markushgrapher_enabled = True
    classification = SimpleNamespace(
        category=ImageCategory.MARKUSH,
        confidence=0.97,
        reason="r-group labels",
    )
    mg_result = SimpleNamespace(
        smiles="[*:1]C",
        confidence=0.72,
        confidence_available=True,
        valid=True,
        markush_validation="passed",
    )
    mg_runner = MagicMock()
    mg_runner.run = AsyncMock(return_value=mg_result)

    with (
        patch("praviar_pipeline.pipeline.step2d_drawings.bytes_to_image", return_value=object()),
        patch(
            "praviar_pipeline.pipeline.step2d_drawings.classify_image", return_value=classification
        ),
        patch(
            "praviar_pipeline.pipeline.step2d_drawings._get_runners",
            return_value={"markushgrapher": mg_runner},
        ),
    ):
        structure = await _analyze_structure_image(
            image_path=image_path,
            patent_id="US123",
            page_number=4,
            structure_index=2,
            all_runners={},
            target_smiles="CCO",
            settings=settings,
        )

    assert structure is not None
    assert structure.is_markush is True
    assert structure.page_number == 4
    assert structure.structure_index == 2
    assert structure.extraction_tool == "markushgrapher"
    assert structure.markush_cxsmiles == "[*:1]C"


@pytest.mark.asyncio
async def test_live_markush_worker_infrastructure_failure_is_not_swallowed(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from praviar_pipeline.ocsr import calibration_contract

    monkeypatch.setattr(calibration_contract, "calibration_is_verified", lambda _settings: True)
    image_path = tmp_path / "segment.png"
    image_path.write_bytes(b"segment")
    settings = _drawing_settings()
    settings.drawing_markushgrapher_enabled = True
    settings.drawing_analysis_rollout_state = "production"
    settings.drawing_analysis_evidence_gate_passed = True
    settings.drawing_markush_rollout_state = "production"
    classification = SimpleNamespace(
        category=ImageCategory.MARKUSH,
        confidence=0.97,
        reason="r-group labels",
    )
    mg_runner = SimpleNamespace(
        predict=AsyncMock(side_effect=OCSROutputError("invalid worker output"))
    )

    with pytest.raises(OCSROutputError):
        await prepare_structure_ocsr(
            image_path=image_path,
            patent_id="US123",
            page_number=4,
            structure_index=2,
            all_runners={},
            settings=settings,
            patent_text="",
            result_cache={},
            image_hash_fn=lambda _bytes: "hash",
            bytes_to_image_fn=lambda _bytes: _FakeImage(),
            classify_image_fn=lambda _image: classification,
            get_runners_fn=lambda _tools, _settings: {"markushgrapher": mg_runner},
            jurisdiction_from_patent_id_fn=lambda _patent_id: "US",
            get_preprocessing_steps_fn=lambda _jurisdiction, _settings: [],
            preprocess_fn=lambda image, _steps: (image, []),
            run_cascade_ocsr_fn=AsyncMock(),
        )


@pytest.mark.asyncio
async def test_markush_specialist_abstains_below_resolved_confidence_floor(tmp_path) -> None:
    image_path = tmp_path / "segment.png"
    image_path.write_bytes(b"segment")
    settings = _drawing_settings()
    settings.drawing_markushgrapher_enabled = True
    classification = SimpleNamespace(
        category=ImageCategory.MARKUSH,
        confidence=0.97,
        reason="r-group labels",
    )
    mg_result = OCSRResult(
        smiles="[*:1]C",
        cxsmiles="[*:1]C",
        confidence=0.01,
        confidence_available=True,
        valid=True,
        is_markush=True,
        markush_validation="passed",
        tool="markushgrapher",
    )
    mg_runner = MagicMock()
    mg_runner.run = AsyncMock(return_value=mg_result)
    cascade = AsyncMock(return_value=OCSRResult(error="no fallback prediction"))

    prepared = await prepare_structure_ocsr(
        image_path=image_path,
        patent_id="US123",
        page_number=4,
        structure_index=2,
        all_runners={},
        settings=settings,
        patent_text="",
        result_cache={},
        image_hash_fn=lambda _bytes: "hash",
        bytes_to_image_fn=lambda _bytes: _FakeImage(),
        classify_image_fn=lambda _image: classification,
        get_runners_fn=lambda _tools, _settings: {"markushgrapher": mg_runner},
        jurisdiction_from_patent_id_fn=lambda _patent_id: "US",
        get_preprocessing_steps_fn=lambda _jurisdiction, _settings: [],
        preprocess_fn=lambda image, _steps: (image, []),
        run_cascade_ocsr_fn=cascade,
    )

    assert prepared is not None
    assert prepared.direct_structure is None
    assert prepared.fused is not None
    assert prepared.fused.valid is False
    cascade.assert_awaited_once()


@pytest.mark.asyncio
async def test_markush_specialist_abstains_above_atom_limit(tmp_path) -> None:
    image_path = tmp_path / "segment.png"
    image_path.write_bytes(b"segment")
    settings = _drawing_settings()
    settings.drawing_markushgrapher_enabled = True
    classification = SimpleNamespace(
        category=ImageCategory.MARKUSH,
        confidence=0.97,
        reason="r-group labels",
    )
    cxsmiles = f"{'C' * 101}[*:1]"
    mg_result = OCSRResult(
        smiles=cxsmiles,
        cxsmiles=cxsmiles,
        confidence=0.99,
        confidence_available=True,
        valid=True,
        is_markush=True,
        markush_validation="passed",
        tool="markushgrapher",
    )
    mg_runner = MagicMock()
    mg_runner.run = AsyncMock(return_value=mg_result)
    cascade = AsyncMock(return_value=OCSRResult(error="no fallback prediction"))

    prepared = await prepare_structure_ocsr(
        image_path=image_path,
        patent_id="US123",
        page_number=4,
        structure_index=2,
        all_runners={},
        settings=settings,
        patent_text="",
        result_cache={},
        image_hash_fn=lambda _bytes: "hash",
        bytes_to_image_fn=lambda _bytes: _FakeImage(),
        classify_image_fn=lambda _image: classification,
        get_runners_fn=lambda _tools, _settings: {"markushgrapher": mg_runner},
        jurisdiction_from_patent_id_fn=lambda _patent_id: "US",
        get_preprocessing_steps_fn=lambda _jurisdiction, _settings: [],
        preprocess_fn=lambda image, _steps: (image, []),
        run_cascade_ocsr_fn=cascade,
    )

    assert prepared is not None
    assert prepared.direct_structure is None
    cascade.assert_awaited_once()


@pytest.mark.asyncio
async def test_prepare_structure_ocsr_blocks_shadow_markush_when_global_drawing_is_live(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from praviar_pipeline.ocsr import calibration_contract

    monkeypatch.setattr(calibration_contract, "calibration_is_verified", lambda _settings: True)
    image_path = tmp_path / "segment.png"
    image_path.write_bytes(b"segment")
    settings = _drawing_settings()
    settings.drawing_markushgrapher_enabled = True
    settings.drawing_analysis_rollout_state = "production"
    settings.drawing_analysis_evidence_gate_passed = True
    settings.drawing_markush_rollout_state = "shadow"
    classification = SimpleNamespace(
        category=ImageCategory.MARKUSH,
        confidence=0.97,
        reason="r-group labels",
    )
    mg_runner = MagicMock()
    mg_runner.run = AsyncMock()
    get_runners = MagicMock(return_value={"markushgrapher": mg_runner})
    cascade_result = OCSRResult(smiles="CCO", confidence=0.86, valid=True, tool="molscribe")

    prepared = await prepare_structure_ocsr(
        image_path=image_path,
        patent_id="US123",
        page_number=4,
        structure_index=2,
        all_runners={},
        settings=settings,
        patent_text="",
        result_cache={},
        image_hash_fn=lambda _bytes: "hash",
        bytes_to_image_fn=lambda _bytes: _FakeImage(),
        classify_image_fn=lambda _image: classification,
        get_runners_fn=get_runners,
        jurisdiction_from_patent_id_fn=lambda _patent_id: "US",
        get_preprocessing_steps_fn=lambda _jurisdiction, _settings: [],
        preprocess_fn=lambda image, _steps: (image, []),
        run_cascade_ocsr_fn=AsyncMock(return_value=cascade_result),
    )

    get_runners.assert_not_called()
    mg_runner.run.assert_not_awaited()
    assert prepared is not None
    assert prepared.direct_structure is None
    assert prepared.fused == cascade_result


@pytest.mark.asyncio
async def test_prepare_structure_ocsr_never_emits_uncalibrated_markush(tmp_path) -> None:
    image_path = tmp_path / "segment.png"
    image_path.write_bytes(b"segment")
    settings = _drawing_settings()
    settings.drawing_markushgrapher_enabled = True
    settings.drawing_analysis_rollout_state = "shadow"
    settings.drawing_markush_rollout_state = "shadow"
    classification = SimpleNamespace(
        category=ImageCategory.MARKUSH,
        confidence=0.97,
        reason="r-group labels",
    )
    mg_result = OCSRResult(
        smiles="*C |$R1;$|",
        cxsmiles="*C |$R1;$|",
        confidence=0.0,
        confidence_available=False,
        valid=False,
        is_markush=True,
        markush_validation="reference_required",
        tool="markushgrapher",
    )
    mg_runner = MagicMock()
    mg_runner.run = AsyncMock(return_value=mg_result)
    cascade_result = OCSRResult(smiles="CCO", confidence=0.86, valid=True, tool="molscribe")
    cascade = AsyncMock(return_value=cascade_result)

    prepared = await prepare_structure_ocsr(
        image_path=image_path,
        patent_id="US123",
        page_number=4,
        structure_index=2,
        all_runners={},
        settings=settings,
        patent_text="",
        result_cache={},
        image_hash_fn=lambda _bytes: "hash",
        bytes_to_image_fn=lambda _bytes: _FakeImage(),
        classify_image_fn=lambda _image: classification,
        get_runners_fn=lambda _tools, _settings: {"markushgrapher": mg_runner},
        jurisdiction_from_patent_id_fn=lambda _patent_id: "US",
        get_preprocessing_steps_fn=lambda _jurisdiction, _settings: [],
        preprocess_fn=lambda image, _steps: (image, []),
        run_cascade_ocsr_fn=cascade,
    )

    assert prepared is not None
    assert prepared.direct_structure is None
    assert prepared.fused == cascade_result
    cascade.assert_awaited_once()


def test_build_patent_drawing_analysis_counts_and_summary() -> None:
    structures = [
        DrawingStructure(
            patent_id="US123",
            page_number=1,
            structure_index=0,
            canonical_smiles="CCO",
            confidence=0.9,
            rdkit_valid=True,
            pubchem_match=True,
            llm_verified=True,
            tanimoto_to_target=0.84,
            drawing_risk_signal=DrawingRiskLevel.HIGH,
        ),
        DrawingStructure(
            patent_id="US123",
            page_number=2,
            structure_index=1,
            canonical_smiles="CO",
            confidence=0.7,
            rdkit_valid=False,
            tanimoto_to_target=0.22,
            drawing_risk_signal=DrawingRiskLevel.LOW,
        ),
    ]

    analysis = build_patent_drawing_analysis(
        patent_id="US123",
        drawing_pages=[(1, b"p1"), (2, b"p2")],
        structures=structures,
        patent_text="See FIG. 5",
        fetch_time=1.2,
        seg_time=0.5,
        ocsr_time=2.4,
        total_time=4.1,
        figure_gap_fn=lambda _text, _pages: ["Figure 5 missing"],
    )

    assert analysis.pages_fetched == 2
    assert analysis.pages_with_structures == 2
    assert analysis.structures_found == 2
    assert analysis.structures_valid == 1
    assert analysis.structures_pubchem_confirmed == 1
    assert analysis.structures_llm_verified == 1
    assert analysis.highest_risk_signal == DrawingRiskLevel.HIGH
    assert analysis.highest_tanimoto == 0.84
    assert "HIGH risk" in analysis.drawing_summary
    assert analysis.figure_reference_gaps == ["Figure 5 missing"]


def test_structure_analysis_helpers_summarize_and_risk() -> None:
    settings = _drawing_settings()
    structures = [
        DrawingStructure(
            patent_id="US123",
            page_number=1,
            structure_index=0,
            canonical_smiles="CCO",
            rdkit_valid=True,
            pubchem_match=True,
            llm_verified=True,
            tanimoto_to_target=0.84,
            drawing_risk_signal=DrawingRiskLevel.HIGH,
        ),
        DrawingStructure(
            patent_id="US123",
            page_number=2,
            structure_index=1,
            canonical_smiles="CO",
            rdkit_valid=False,
            tanimoto_to_target=0.22,
            drawing_risk_signal=DrawingRiskLevel.LOW,
        ),
    ]

    assert compute_risk_level(0.82, settings) == DrawingRiskLevel.HIGH
    assert compute_risk_level(0.4, settings) == DrawingRiskLevel.MEDIUM
    assert compute_risk_level(0.1, settings) == DrawingRiskLevel.LOW

    (
        n_valid,
        n_pubchem,
        n_llm,
        pages_with_structures,
        highest_risk,
        highest_tanimoto,
        summary,
    ) = summarize_patent_drawing_analysis(
        drawing_pages=[(1, b"p1"), (2, b"p2")], structures=structures
    )

    assert (n_valid, n_pubchem, n_llm, pages_with_structures) == (1, 1, 1, 2)
    assert highest_risk == DrawingRiskLevel.HIGH
    assert highest_tanimoto == 0.84
    assert "HIGH risk" in summary


def test_structure_analysis_helper_builders_and_formula_signal() -> None:
    prepared = build_markush_prepared_structure(
        patent_id="US123",
        page_number=3,
        structure_index=7,
        smiles="[*:1]CC",
        confidence=0.74,
    )

    assert prepared.direct_structure is not None
    assert prepared.direct_structure.patent_id == "US123"
    assert prepared.direct_structure.is_markush is True
    assert prepared.direct_structure.markush_cxsmiles == "[*:1]CC"

    with patch(
        "praviar_pipeline.ocsr.text_validation.extract_molecular_formulas",
        return_value=["C2H6O", "C3H8O"],
    ):
        signal, error = extract_text_formula_signal("Formula C2H6O")

    assert signal == "C2H6O"
    assert error is None

    structure = build_final_drawing_structure(
        patent_id="US123",
        page_number=1,
        structure_index=2,
        raw_smiles="CCO",
        processed_smiles="CCO",
        inchi_key="TEST-INCHI",
        confidence=0.91,
        extraction_tool="molscribe",
        input_image_sha256="b" * 64,
        applied_steps=["clahe"],
        post_steps=["canonicalise"],
        rdkit_valid=True,
        pubchem_match=False,
        tanimoto_to_target=0.81234,
        is_substructure_of_target=True,
        target_is_substructure=False,
        drawing_risk_signal=DrawingRiskLevel.HIGH,
        cropped_structure_image="/tmp/segment.png",
    )

    assert structure.tanimoto_to_target == 0.8123
    assert structure.cropped_structure_image == "/tmp/segment.png"
    assert structure.drawing_risk_signal == DrawingRiskLevel.HIGH
    assert structure.input_image_sha256 == "b" * 64


def test_build_drawing_analysis_results_aggregates_totals() -> None:
    analyses = [
        build_patent_drawing_analysis(
            patent_id="US123",
            drawing_pages=[(1, b"p1")],
            structures=[
                DrawingStructure(
                    patent_id="US123",
                    page_number=1,
                    structure_index=0,
                    canonical_smiles="CCO",
                    tanimoto_to_target=0.81,
                    drawing_risk_signal=DrawingRiskLevel.HIGH,
                )
            ],
            patent_text="",
            fetch_time=1.0,
            seg_time=1.0,
            ocsr_time=1.0,
            total_time=3.0,
            figure_gap_fn=lambda _text, _pages: [],
        ),
        build_patent_drawing_analysis(
            patent_id="US456",
            drawing_pages=[],
            structures=[],
            patent_text="",
            fetch_time=0.2,
            seg_time=0.0,
            ocsr_time=0.0,
            total_time=0.2,
            figure_gap_fn=lambda _text, _pages: [],
        ),
    ]

    aggregate = build_drawing_analysis_results(analyses)

    assert aggregate.total_patents_with_images == 1
    assert aggregate.total_structures_extracted == 1
    assert aggregate.total_high_risk_structures == 1
    assert aggregate.total_time_s == 3.2


def test_aggregate_drawing_analysis_results_helper() -> None:
    analyses = [
        build_patent_drawing_analysis(
            patent_id="US123",
            drawing_pages=[(1, b"p1")],
            structures=[
                DrawingStructure(
                    patent_id="US123",
                    page_number=1,
                    structure_index=0,
                    canonical_smiles="CCO",
                    tanimoto_to_target=0.81,
                    drawing_risk_signal=DrawingRiskLevel.HIGH,
                )
            ],
            patent_text="",
            fetch_time=1.0,
            seg_time=1.0,
            ocsr_time=1.0,
            total_time=3.0,
            figure_gap_fn=lambda _text, _pages: [],
        ),
        build_patent_drawing_analysis(
            patent_id="US456",
            drawing_pages=[],
            structures=[],
            patent_text="",
            fetch_time=0.2,
            seg_time=0.0,
            ocsr_time=0.0,
            total_time=0.2,
            figure_gap_fn=lambda _text, _pages: [],
        ),
    ]

    assert aggregate_drawing_analysis_results(analyses) == (1, 1, 1, 0.0, 3.2)


@pytest.mark.asyncio
async def test_analyze_patent_drawings_handles_unexpected_gather_exception() -> None:
    settings = _drawing_settings()
    settings.drawing_analysis_enabled = True
    settings.drawing_ensemble_tools = ["molscribe"]
    settings.drawing_image_cache_dir = None
    settings.drawing_max_patents = 0
    settings.drawing_concurrency = 1
    settings.drawing_timeout_per_patent_s = 30
    patent = SimpleNamespace(patent_id="US999", abstract="", claims_text="")

    with (
        patch(
            "praviar_pipeline.pipeline.step2d_drawings._get_runners",
            return_value={"molscribe": MagicMock()},
        ),
        patch(
            "praviar_pipeline.pipeline.step2d_drawings._get_segmentation_runner", return_value=None
        ),
        patch(
            "praviar_pipeline.pipeline.step2d_drawings.EPOOPSClient",
            side_effect=ValueError("no credentials"),
        ),
        patch(
            "praviar_pipeline.pipeline.step2d_drawings._analyze_single_patent",
            new=AsyncMock(side_effect=TypeError("unexpected boom")),
        ),
    ):
        from praviar_pipeline.pipeline.step2d_drawings import analyze_patent_drawings

        with pytest.raises(DrawingAnalysisError) as exc_info:
            await analyze_patent_drawings([patent], "CCO", settings)

    assert exc_info.value.failure_types == ("TypeError",)
    assert "unexpected boom" not in str(exc_info.value)
