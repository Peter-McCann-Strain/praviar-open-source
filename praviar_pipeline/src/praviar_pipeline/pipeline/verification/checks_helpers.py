"""Pure helper functions for deterministic verification checks."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from praviar_pipeline.models.analysis import ElementStatus, PatentAnalysis, RiskLevel
from praviar_pipeline.models.patent import LegalStatus

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from praviar_pipeline.models.equivalents import DoEAssessment
    from praviar_pipeline.models.invalidity import InvalidityAssessment

VALID_STRENGTHS = frozenset({"strong", "moderate", "weak", "none", ""})


def looks_like_smiles(text: str) -> bool:
    """Heuristic: does a token look like a SMILES string."""
    if len(text) < 4:
        return False
    if re.match(r"^[A-Z][a-z]?[\d]*[-/][A-Z]", text):
        return False

    has_smiles_feature = any(char in text for char in "=#[]@\\")
    if not has_smiles_feature:
        has_smiles_feature = bool(re.search(r"[cnospb]\d[cnospb]", text))
    if not has_smiles_feature:
        return False
    if " " in text or "," in text:
        return False

    smiles_chars = set("CNOSPFIBrcnospfib0123456789=#[]()@+\\-.")
    valid_ratio = sum(1 for char in text if char in smiles_chars) / len(text)
    return valid_ratio > 0.8


def collect_invalid_smiles(
    analyses: list[PatentAnalysis],
    smiles_validator: Callable[[str], object | None],
) -> list[str]:
    invalid = []
    for analysis in analyses:
        for suggestion in analysis.design_around_suggestions:
            for word in suggestion.suggestion.split():
                clean = word.rstrip(".,;:!?)")
                if not looks_like_smiles(clean):
                    continue
                if smiles_validator(clean) is None:
                    invalid.append(f"{analysis.patent_id}: {clean}")
    return invalid


def find_risk_inconsistencies(analyses: list[PatentAnalysis]) -> list[str]:
    inconsistent = []
    for analysis in analyses:
        if analysis.risk_level != RiskLevel.HIGH:
            continue
        has_potential_block = any(
            claim.overall_status
            in (
                ElementStatus.MET,
                ElementStatus.PARTIALLY_MET,
                ElementStatus.UNCLEAR,
            )
            for claim in analysis.claims_analyzed
        )
        if not has_potential_block:
            inconsistent.append(f"{analysis.patent_id}: HIGH risk but all claims are NOT_MET")
    return inconsistent


def find_date_issues(
    analyses: list[PatentAnalysis],
    patent_expiry_year_min: int,
    patent_expiry_year_max: int,
) -> list[str]:
    issues = []
    for analysis in analyses:
        if analysis.expiry_date:
            year = analysis.expiry_date.year
            if year < patent_expiry_year_min or year > patent_expiry_year_max:
                issues.append(f"{analysis.patent_id}: implausible expiry year {year}")
    return issues


def find_legal_status_issues(
    analyses: list[PatentAnalysis],
    status_map: Mapping[str, LegalStatus],
) -> list[str]:
    issues = []
    for analysis in analyses:
        if analysis.risk_level != RiskLevel.HIGH:
            continue
        status = status_map.get(analysis.patent_id, LegalStatus.UNKNOWN)
        if status in (LegalStatus.EXPIRED, LegalStatus.LAPSED, LegalStatus.REVOKED):
            issues.append(f"{analysis.patent_id}: HIGH risk but legal status is {status.value}")
    return issues


def find_doe_orphaned_issues(
    doe_assessments: list[DoEAssessment],
    analyses: list[PatentAnalysis],
) -> list[str]:
    known_combos = {
        (analysis.patent_id, claim.claim_number)
        for analysis in analyses
        for claim in analysis.claims_analyzed
    }
    return [
        f"{assessment.patent_id}/claim{assessment.claim_number}"
        for assessment in doe_assessments
        if (assessment.patent_id, assessment.claim_number) not in known_combos
    ]


def find_invalidity_issues(
    invalidity_assessments: list[InvalidityAssessment],
    analyzed_ids: set[str],
) -> list[str]:
    issues = []
    for assessment in invalidity_assessments:
        if assessment.patent_id not in analyzed_ids:
            issues.append(f"{assessment.patent_id}: not in analyzed patents")
        if assessment.overall_invalidity_strength not in VALID_STRENGTHS:
            issues.append(
                f"{assessment.patent_id}: invalid strength "
                f"'{assessment.overall_invalidity_strength}'"
            )
    return issues


def find_missing_claims(
    analyses: list[PatentAnalysis],
    patents_with_claims: set[str],
) -> list[str]:
    return [
        analysis.patent_id for analysis in analyses if analysis.patent_id not in patents_with_claims
    ]


def find_claim_chart_issues(
    invalidity_assessments: list[InvalidityAssessment],
) -> list[str]:
    issues = []
    for assessment in invalidity_assessments:
        valid_refs = {reference.reference_id for reference in assessment.prior_art}
        for chart in assessment.claim_charts:
            if chart.prior_art_reference_id not in valid_refs:
                issues.append(
                    f"{assessment.patent_id}: claim chart references "
                    f"unknown prior art '{chart.prior_art_reference_id}'"
                )
            for entry in chart.entries:
                if entry.prior_art_reference_id not in valid_refs:
                    issues.append(
                        f"{assessment.patent_id}: chart entry references "
                        f"unknown prior art '{entry.prior_art_reference_id}'"
                    )
    return issues


def find_prosecution_history_issues(
    doe_assessments: list[DoEAssessment],
) -> list[str]:
    issues = []
    for assessment in doe_assessments:
        if assessment.estoppel.estoppel_applies and not assessment.estoppel.amendments_found:
            issues.append(
                f"{assessment.patent_id}/claim{assessment.claim_number}: "
                "estoppel_applies=True but no amendments found"
            )
        if (
            assessment.estoppel.prosecution_narrowing_count > 0
            and not assessment.estoppel.estoppel_applies
        ):
            issues.append(
                f"{assessment.patent_id}/claim{assessment.claim_number}: "
                f"{assessment.estoppel.prosecution_narrowing_count} narrowing amendments "
                "but estoppel not applied"
            )
    return issues


def is_vacuous_check(
    check_name: str,
    analyses_count: int,
    doe_count: int,
    invalidity_count: int,
) -> bool:
    vacuous_checks = {
        "doe_consistency": doe_count == 0,
        "invalidity_consistency": invalidity_count == 0,
        "claim_chart_consistency": invalidity_count == 0,
        "prosecution_history_consistency": doe_count == 0,
        "chemical_entity_validation": analyses_count == 0,
        "risk_level_consistency": analyses_count == 0,
    }
    return vacuous_checks.get(check_name, False)
