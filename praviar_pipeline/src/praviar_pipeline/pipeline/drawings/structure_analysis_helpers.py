"""Pure helpers for drawing structure analysis aggregation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from praviar_pipeline.models.drawing import (
    DrawingAnalysisResults,
    DrawingRiskLevel,
    DrawingStructure,
    OCSRResult,
    PatentDrawingAnalysis,
)
from praviar_pipeline.utils.safe_diagnostics import safe_failure_message

if TYPE_CHECKING:
    from collections.abc import Callable

    from praviar_pipeline.config import Settings


@dataclass(slots=True)
class PreparedStructureOCSR:
    fused: OCSRResult | None = None
    applied_steps: list[str] = field(default_factory=list)
    direct_structure: DrawingStructure | None = None
    input_image_sha256: str = ""


_RISK_ORDER = {
    DrawingRiskLevel.HIGH: 3,
    DrawingRiskLevel.MEDIUM: 2,
    DrawingRiskLevel.LOW: 1,
    DrawingRiskLevel.NONE: 0,
}


def compute_risk_level(tanimoto: float, settings: Settings) -> DrawingRiskLevel:
    if tanimoto >= settings.drawing_tanimoto_high:
        return DrawingRiskLevel.HIGH
    if tanimoto >= settings.drawing_tanimoto_medium:
        return DrawingRiskLevel.MEDIUM
    return DrawingRiskLevel.LOW


def build_markush_prepared_structure(
    *,
    patent_id: str,
    page_number: int,
    structure_index: int,
    smiles: str,
    confidence: float,
    extraction_tool: str = "markushgrapher",
    input_image_sha256: str = "",
) -> PreparedStructureOCSR:
    return PreparedStructureOCSR(
        direct_structure=DrawingStructure(
            patent_id=patent_id,
            page_number=page_number,
            structure_index=structure_index,
            raw_smiles=smiles,
            canonical_smiles=smiles,
            confidence=confidence,
            extraction_tool=extraction_tool,
            input_image_sha256=input_image_sha256,
            is_markush=True,
            markush_cxsmiles=smiles,
        )
    )


def extract_text_formula_signal(patent_text: str) -> tuple[str, str | None]:
    if not patent_text:
        return "", None

    try:
        from praviar_pipeline.ocsr.text_validation import extract_molecular_formulas

        formulas = extract_molecular_formulas(patent_text)
        if formulas:
            return formulas[0], None
        return "", None
    except (ImportError, ValueError) as exc:
        return "", safe_failure_message("text formula extraction", exc)


def _canonical_text_smiles(smiles: str | None) -> str:
    if not smiles:
        return ""
    try:
        from rdkit import Chem

        mol = Chem.MolFromSmiles(smiles)
        return Chem.MolToSmiles(mol) if mol is not None else ""
    except Exception:
        return ""


async def extract_text_smiles_signal(
    patent_text: str,
    *,
    max_names: int = 3,
    max_cas: int = 5,
) -> tuple[str, str | None]:
    """Resolve a conservative text-derived SMILES signal from patent prose."""

    if not patent_text:
        return "", None

    try:
        from praviar_pipeline.ocsr import text_validation, text_validation_clients
    except ImportError as exc:
        return "", safe_failure_message("text structure extraction", exc)

    try:
        names = text_validation.extract_chemical_names(patent_text)
    except Exception:
        names = []

    for name in names[:max_names]:
        try:
            candidate = await text_validation.opsin_resolve(name)
        except Exception:
            continue
        canonical = _canonical_text_smiles(candidate)
        if canonical:
            return canonical, None

    try:
        cas_numbers = text_validation.extract_cas_numbers(patent_text)
    except Exception:
        cas_numbers = []

    for cas_number in cas_numbers[:max_cas]:
        try:
            candidate = await text_validation_clients._pubchem_cas_lookup(cas_number)
        except Exception:
            continue
        canonical = _canonical_text_smiles(candidate)
        if canonical:
            return canonical, None

    return "", None


def build_final_drawing_structure(
    *,
    patent_id: str,
    page_number: int,
    structure_index: int,
    raw_smiles: str,
    processed_smiles: str,
    inchi_key: str,
    confidence: float,
    extraction_tool: str,
    input_image_sha256: str,
    applied_steps: list[str],
    post_steps: list[str],
    rdkit_valid: bool,
    pubchem_match: bool,
    tanimoto_to_target: float,
    is_substructure_of_target: bool,
    target_is_substructure: bool,
    drawing_risk_signal: DrawingRiskLevel,
    cropped_structure_image: str,
    stereo_flag: str = "",
    stereo_cip_count: int = 0,
    stereo_ez_count: int = 0,
    stereo_target_cip_count: int = 0,
    stereo_target_ez_count: int = 0,
    stereo_claim_mentions: bool = False,
    stereo_details: str = "",
) -> DrawingStructure:
    return DrawingStructure(
        patent_id=patent_id,
        page_number=page_number,
        structure_index=structure_index,
        raw_smiles=raw_smiles,
        canonical_smiles=processed_smiles,
        inchi_key=inchi_key,
        confidence=confidence,
        extraction_tool=extraction_tool,
        input_image_sha256=input_image_sha256,
        preprocessing_applied=list(applied_steps),
        postprocessing_applied=post_steps,
        rdkit_valid=rdkit_valid,
        pubchem_match=pubchem_match,
        tanimoto_to_target=round(tanimoto_to_target, 4),
        is_substructure_of_target=is_substructure_of_target,
        target_is_substructure=target_is_substructure,
        drawing_risk_signal=drawing_risk_signal,
        stereo_flag=stereo_flag,
        stereo_cip_count=stereo_cip_count,
        stereo_ez_count=stereo_ez_count,
        stereo_target_cip_count=stereo_target_cip_count,
        stereo_target_ez_count=stereo_target_ez_count,
        stereo_claim_mentions=stereo_claim_mentions,
        stereo_details=stereo_details,
        cropped_structure_image=cropped_structure_image,
    )


def summarize_patent_drawing_analysis(
    *,
    drawing_pages: list[tuple[int, bytes]],
    structures: list[DrawingStructure],
) -> tuple[
    int,
    int,
    int,
    int,
    DrawingRiskLevel,
    float,
    str,
]:
    highest_risk = DrawingRiskLevel.NONE
    highest_tanimoto = 0.0
    n_valid = 0
    n_pubchem = 0
    n_llm = 0

    for structure in structures:
        if structure.rdkit_valid:
            n_valid += 1
        if structure.pubchem_match:
            n_pubchem += 1
        if structure.llm_verified:
            n_llm += 1
        if structure.tanimoto_to_target > highest_tanimoto:
            highest_tanimoto = structure.tanimoto_to_target
        if _RISK_ORDER.get(structure.drawing_risk_signal, 0) > _RISK_ORDER.get(highest_risk, 0):
            highest_risk = structure.drawing_risk_signal

    summary_parts = [
        f"{len(structures)} structures extracted from {len(drawing_pages)} pages.",
    ]
    if highest_risk == DrawingRiskLevel.HIGH:
        summary_parts.append(
            f"HIGH risk: structure with Tanimoto {highest_tanimoto:.2f} to target."
        )
    elif highest_risk == DrawingRiskLevel.MEDIUM:
        summary_parts.append(f"MEDIUM risk: highest Tanimoto {highest_tanimoto:.2f}.")
    else:
        summary_parts.append("No structurally similar compounds found in drawings.")

    return (
        n_valid,
        n_pubchem,
        n_llm,
        len({structure.page_number for structure in structures}),
        highest_risk,
        round(highest_tanimoto, 4),
        " ".join(summary_parts),
    )


def aggregate_drawing_analysis_results(
    analyses: list[PatentDrawingAnalysis],
) -> tuple[int, int, int, float, float]:
    total_structures = sum(analysis.structures_found for analysis in analyses)
    total_high_risk = sum(
        1 for analysis in analyses if analysis.highest_risk_signal == DrawingRiskLevel.HIGH
    )
    total_cost = sum(analysis.llm_verification_cost_usd for analysis in analyses)
    total_time = sum(analysis.total_time_s for analysis in analyses)
    patents_with_images = sum(1 for analysis in analyses if analysis.pages_fetched > 0)

    return (
        patents_with_images,
        total_structures,
        total_high_risk,
        round(total_cost, 4),
        round(total_time, 1),
    )


def build_patent_drawing_analysis(
    *,
    patent_id: str,
    drawing_pages: list[tuple[int, bytes]],
    structures: list[DrawingStructure],
    patent_text: str,
    fetch_time: float,
    seg_time: float,
    ocsr_time: float,
    total_time: float,
    figure_gap_fn: Callable[[str, int], list[str]],
) -> PatentDrawingAnalysis:
    (
        n_valid,
        n_pubchem,
        n_llm,
        pages_with_structures,
        highest_risk,
        highest_tanimoto,
        drawing_summary,
    ) = summarize_patent_drawing_analysis(drawing_pages=drawing_pages, structures=structures)

    return PatentDrawingAnalysis(
        patent_id=patent_id,
        pages_fetched=len(drawing_pages),
        pages_with_structures=pages_with_structures,
        structures_found=len(structures),
        structures_valid=n_valid,
        structures_pubchem_confirmed=n_pubchem,
        structures_llm_verified=n_llm,
        structures=structures,
        highest_risk_signal=highest_risk,
        highest_tanimoto=highest_tanimoto,
        drawing_summary=drawing_summary,
        figure_reference_gaps=figure_gap_fn(patent_text, len(drawing_pages)),
        fetch_time_s=round(fetch_time, 2),
        segmentation_time_s=round(seg_time, 2),
        ocsr_time_s=round(ocsr_time, 2),
        total_time_s=round(total_time, 2),
    )


def build_drawing_analysis_results(
    analyses: list[PatentDrawingAnalysis],
) -> DrawingAnalysisResults:
    patents_with_images, total_structures, total_high_risk, total_cost, total_time = (
        aggregate_drawing_analysis_results(analyses)
    )

    return DrawingAnalysisResults(
        patent_analyses=analyses,
        total_patents_with_images=patents_with_images,
        total_structures_extracted=total_structures,
        total_high_risk_structures=total_high_risk,
        total_cost_usd=round(total_cost, 4),
        total_time_s=round(total_time, 1),
    )
