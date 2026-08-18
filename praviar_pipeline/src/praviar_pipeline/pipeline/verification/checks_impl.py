"""Implementation helpers for deterministic verification checks."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import structlog

from praviar_pipeline.config import get_settings
from praviar_pipeline.models.verification import VerificationCheck
from praviar_pipeline.pipeline.verification.checks_helpers import (
    VALID_STRENGTHS as _VALID_STRENGTHS,
)
from praviar_pipeline.pipeline.verification.checks_helpers import (
    collect_invalid_smiles,
    find_claim_chart_issues,
    find_date_issues,
    find_doe_orphaned_issues,
    find_invalidity_issues,
    find_legal_status_issues,
    find_missing_claims,
    find_prosecution_history_issues,
    find_risk_inconsistencies,
    is_vacuous_check,
)
from praviar_pipeline.pipeline.verification.checks_helpers import (
    looks_like_smiles as _looks_like_smiles,
)

if TYPE_CHECKING:
    from praviar_pipeline.models.analysis import PatentAnalysis
    from praviar_pipeline.models.equivalents import DoEAssessment
    from praviar_pipeline.models.invalidity import InvalidityAssessment
    from praviar_pipeline.models.patent import PatentHit

logger = structlog.get_logger()
VALID_STRENGTHS = _VALID_STRENGTHS


def check_citations(
    analyses: list[PatentAnalysis],
    search_results: list[PatentHit],
) -> VerificationCheck:
    search_ids = {patent.patent_id for patent in search_results}
    missing = [analysis.patent_id for analysis in analyses if analysis.patent_id not in search_ids]

    return VerificationCheck(
        check_name="citation_grounding",
        passed=len(missing) == 0,
        details=(
            f"All {len(analyses)} patent IDs found in search results"
            if not missing
            else f"Missing from search results: {missing}"
        ),
    )


def looks_like_smiles(text: str) -> bool:
    return _looks_like_smiles(text)


def check_chemical_entities(analyses: list[PatentAnalysis]) -> VerificationCheck:
    try:
        from rdkit import Chem
    except ImportError:
        logger.warning("rdkit_not_available", check="chemical_entity_validation")
        return VerificationCheck(
            check_name="chemical_entity_validation",
            passed=False,
            details="Chemical entity validation unavailable",
        )

    invalid = collect_invalid_smiles(analyses, Chem.MolFromSmiles)

    return VerificationCheck(
        check_name="chemical_entity_validation",
        passed=len(invalid) == 0,
        details=(
            "No invalid SMILES found in analysis output"
            if not invalid
            else f"Invalid SMILES: {invalid[:5]}"
        ),
    )


def check_risk_consistency(analyses: list[PatentAnalysis]) -> VerificationCheck:
    inconsistent = find_risk_inconsistencies(analyses)

    return VerificationCheck(
        check_name="risk_level_consistency",
        passed=len(inconsistent) == 0,
        details=(
            "All risk levels consistent with claim analysis"
            if not inconsistent
            else f"Inconsistencies: {inconsistent}"
        ),
    )


def check_date_consistency(analyses: list[PatentAnalysis]) -> VerificationCheck:
    settings = get_settings()
    issues = find_date_issues(
        analyses,
        settings.patent_expiry_year_min,
        settings.patent_expiry_year_max,
    )

    return VerificationCheck(
        check_name="date_consistency",
        passed=len(issues) == 0,
        details=("All expiry dates are plausible" if not issues else f"Date issues: {issues}"),
    )


def check_legal_status(
    analyses: list[PatentAnalysis],
    search_results: list[PatentHit],
) -> VerificationCheck:
    status_map = {hit.patent_id: hit.legal_status for hit in search_results}
    issues = find_legal_status_issues(analyses, status_map)

    return VerificationCheck(
        check_name="legal_status_consistency",
        passed=len(issues) == 0,
        details=(
            "All HIGH-risk patents have active or unknown legal status"
            if not issues
            else f"Legal status issues: {issues}"
        ),
    )


def check_doe_consistency(
    doe_assessments: list[DoEAssessment],
    analyses: list[PatentAnalysis],
) -> VerificationCheck:
    orphaned = find_doe_orphaned_issues(doe_assessments, analyses)

    return VerificationCheck(
        check_name="doe_consistency",
        passed=len(orphaned) == 0,
        details=(
            f"All {len(doe_assessments)} DoE assessments reference valid claims"
            if not orphaned
            else f"Orphaned DoE assessments: {orphaned}"
        ),
    )


def check_invalidity_consistency(
    invalidity_assessments: list[InvalidityAssessment],
    analyses: list[PatentAnalysis],
) -> VerificationCheck:
    analyzed_ids = {analysis.patent_id for analysis in analyses}
    issues = find_invalidity_issues(invalidity_assessments, analyzed_ids)

    return VerificationCheck(
        check_name="invalidity_consistency",
        passed=len(issues) == 0,
        details=(
            f"All {len(invalidity_assessments)} invalidity assessments are consistent"
            if not issues
            else f"Invalidity issues: {issues}"
        ),
    )


def check_claims_grounded(
    analyses: list[PatentAnalysis],
    search_results: list[PatentHit],
) -> VerificationCheck:
    patents_with_claims = {patent.patent_id for patent in search_results if patent.claims_text}
    missing_claims = find_missing_claims(analyses, patents_with_claims)

    settings = get_settings()
    details = (
        f"All {len(analyses)} analyzed patents have claims text"
        if not missing_claims
        else f"Patents without claims: {missing_claims[: settings.verification_max_items_detail]}"
    )
    return VerificationCheck(
        check_name="claims_grounded",
        passed=len(missing_claims) == 0,
        details=details,
    )


def check_claim_charts(
    invalidity_assessments: list[InvalidityAssessment],
) -> VerificationCheck:
    issues = find_claim_chart_issues(invalidity_assessments)

    settings = get_settings()
    return VerificationCheck(
        check_name="claim_chart_consistency",
        passed=len(issues) == 0,
        details=(
            "All claim chart references are valid"
            if not issues
            else f"Orphaned references: {issues[: settings.verification_max_orphaned_display]}"
        ),
    )


def check_prosecution_history(
    doe_assessments: list[DoEAssessment],
) -> VerificationCheck:
    issues = find_prosecution_history_issues(doe_assessments)

    return VerificationCheck(
        check_name="prosecution_history_consistency",
        passed=len(issues) == 0,
        details=(
            "Prosecution history is consistent with estoppel findings"
            if not issues
            else f"Prosecution history issues: {issues}"
        ),
    )


def detect_vacuous_pass(
    check: VerificationCheck,
    analyses: list[PatentAnalysis],
    doe_assessments: list[DoEAssessment],
    invalidity_assessments: list[InvalidityAssessment],
) -> Literal["pass", "warning"]:
    if is_vacuous_check(
        check.check_name,
        len(analyses),
        len(doe_assessments),
        len(invalidity_assessments),
    ):
        return "warning"
    return "pass"
