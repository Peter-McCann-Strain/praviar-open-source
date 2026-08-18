"""Step 7: Verification — deterministic checks against source data."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.models.verification import VerificationCheck, VerificationResult
from praviar_pipeline.pipeline.verification import checks as verification_checks
from praviar_pipeline.pipeline.verification.orange_book import check_orange_book

if TYPE_CHECKING:
    from praviar_pipeline.clients.orange_book import OrangeBookIndex
    from praviar_pipeline.models.analysis import PatentAnalysis
    from praviar_pipeline.models.equivalents import DoEAssessment
    from praviar_pipeline.models.invalidity import InvalidityAssessment
    from praviar_pipeline.models.patent import PatentHit

logger = structlog.get_logger()


# Direct aliases for the verification check helpers — preserve the
# underscore-prefixed names that tests and the orchestrator below reference,
# while removing wrapper indirection.
_check_citations = verification_checks.check_citations
_looks_like_smiles = verification_checks.looks_like_smiles
_check_chemical_entities = verification_checks.check_chemical_entities
_check_risk_consistency = verification_checks.check_risk_consistency
_check_date_consistency = verification_checks.check_date_consistency
_check_legal_status = verification_checks.check_legal_status
_check_doe_consistency = verification_checks.check_doe_consistency
_check_invalidity_consistency = verification_checks.check_invalidity_consistency
_check_claims_grounded = verification_checks.check_claims_grounded
_check_claim_charts = verification_checks.check_claim_charts
_check_prosecution_history = verification_checks.check_prosecution_history
_check_orange_book = check_orange_book
_detect_vacuous_pass = verification_checks.detect_vacuous_pass


def verify_analysis(
    analyses: list[PatentAnalysis],
    doe_assessments: list[DoEAssessment],
    invalidity_assessments: list[InvalidityAssessment],
    search_results: list[PatentHit],
    orange_book: OrangeBookIndex | None = None,
) -> VerificationResult:
    """Run all deterministic verification checks.

    This is Step 7 — no LLM calls, purely rule-based validation.
    """
    logger.info("verification_start", patent_count=len(analyses))
    logger.debug(
        "step7_entry",
        analyses_count=len(analyses),
        doe_count=len(doe_assessments),
        invalidity_count=len(invalidity_assessments),
        search_results_count=len(search_results),
        has_orange_book=orange_book is not None,
    )

    check_fns = [
        lambda: _check_citations(analyses, search_results),
        lambda: _check_chemical_entities(analyses),
        lambda: _check_risk_consistency(analyses),
        lambda: _check_date_consistency(analyses),
        lambda: _check_legal_status(analyses, search_results),
        lambda: _check_doe_consistency(doe_assessments, analyses),
        lambda: _check_invalidity_consistency(invalidity_assessments, analyses),
        lambda: _check_claims_grounded(analyses, search_results),
        lambda: _check_claim_charts(invalidity_assessments),
        lambda: _check_prosecution_history(doe_assessments),
        lambda: _check_orange_book(analyses, orange_book),
    ]

    checks: list[VerificationCheck] = []
    for fn in check_fns:
        check = fn()
        # Detect vacuous passes: check passed but validated 0 items
        if check.passed:
            severity = _detect_vacuous_pass(
                check,
                analyses,
                doe_assessments,
                invalidity_assessments,
            )
            check.severity = severity
        else:
            check.severity = "fail"
        checks.append(check)

    # Look up checks by name instead of index position
    def _check_passed(name: str) -> bool:
        return next((c.passed for c in checks if c.check_name == name), False)

    issues = [c.details for c in checks if not c.passed]

    result = VerificationResult(
        checks=checks,
        all_citations_valid=_check_passed("citation_grounding"),
        all_claims_grounded=_check_passed("claims_grounded"),
        all_entities_valid=_check_passed("chemical_entity_validation"),
        dates_consistent=_check_passed("date_consistency"),
        risk_levels_justified=_check_passed("risk_level_consistency"),
        issues=issues,
    )

    logger.info(
        "verification_complete",
        all_passed=result.all_passed,
        issues_count=len(issues),
    )
    logger.debug(
        "step7_output_summary",
        total_checks=len(checks),
        passed=sum(1 for c in checks if c.passed),
        failed=sum(1 for c in checks if not c.passed),
        vacuous_warnings=sum(1 for c in checks if c.severity == "warning"),
        failed_check_names=[c.check_name for c in checks if not c.passed],
    )

    return result
