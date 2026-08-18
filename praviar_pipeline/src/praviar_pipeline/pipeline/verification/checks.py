"""Deterministic verification checks used by Step 7."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from praviar_pipeline.pipeline.verification.checks_impl import (
    VALID_STRENGTHS as _VALID_STRENGTHS,
)
from praviar_pipeline.pipeline.verification.checks_impl import (
    check_chemical_entities as _check_chemical_entities_impl,
)
from praviar_pipeline.pipeline.verification.checks_impl import (
    check_citations as _check_citations_impl,
)
from praviar_pipeline.pipeline.verification.checks_impl import (
    check_claim_charts as _check_claim_charts_impl,
)
from praviar_pipeline.pipeline.verification.checks_impl import (
    check_claims_grounded as _check_claims_grounded_impl,
)
from praviar_pipeline.pipeline.verification.checks_impl import (
    check_date_consistency as _check_date_consistency_impl,
)
from praviar_pipeline.pipeline.verification.checks_impl import (
    check_doe_consistency as _check_doe_consistency_impl,
)
from praviar_pipeline.pipeline.verification.checks_impl import (
    check_invalidity_consistency as _check_invalidity_consistency_impl,
)
from praviar_pipeline.pipeline.verification.checks_impl import (
    check_legal_status as _check_legal_status_impl,
)
from praviar_pipeline.pipeline.verification.checks_impl import (
    check_prosecution_history as _check_prosecution_history_impl,
)
from praviar_pipeline.pipeline.verification.checks_impl import (
    check_risk_consistency as _check_risk_consistency_impl,
)
from praviar_pipeline.pipeline.verification.checks_impl import (
    detect_vacuous_pass as _detect_vacuous_pass_impl,
)
from praviar_pipeline.pipeline.verification.checks_impl import (
    looks_like_smiles as _looks_like_smiles_impl,
)

if TYPE_CHECKING:
    from praviar_pipeline.models.analysis import PatentAnalysis
    from praviar_pipeline.models.equivalents import DoEAssessment
    from praviar_pipeline.models.invalidity import InvalidityAssessment
    from praviar_pipeline.models.patent import PatentHit
    from praviar_pipeline.models.verification import VerificationCheck

VALID_STRENGTHS = _VALID_STRENGTHS


def check_citations(
    analyses: list[PatentAnalysis],
    search_results: list[PatentHit],
) -> VerificationCheck:
    return _check_citations_impl(analyses, search_results)


def looks_like_smiles(text: str) -> bool:
    return _looks_like_smiles_impl(text)


def check_chemical_entities(analyses: list[PatentAnalysis]) -> VerificationCheck:
    return _check_chemical_entities_impl(analyses)


def check_risk_consistency(analyses: list[PatentAnalysis]) -> VerificationCheck:
    return _check_risk_consistency_impl(analyses)


def check_date_consistency(analyses: list[PatentAnalysis]) -> VerificationCheck:
    return _check_date_consistency_impl(analyses)


def check_legal_status(
    analyses: list[PatentAnalysis],
    search_results: list[PatentHit],
) -> VerificationCheck:
    return _check_legal_status_impl(analyses, search_results)


def check_doe_consistency(
    doe_assessments: list[DoEAssessment],
    analyses: list[PatentAnalysis],
) -> VerificationCheck:
    return _check_doe_consistency_impl(doe_assessments, analyses)


def check_invalidity_consistency(
    invalidity_assessments: list[InvalidityAssessment],
    analyses: list[PatentAnalysis],
) -> VerificationCheck:
    return _check_invalidity_consistency_impl(invalidity_assessments, analyses)


def check_claims_grounded(
    analyses: list[PatentAnalysis],
    search_results: list[PatentHit],
) -> VerificationCheck:
    return _check_claims_grounded_impl(analyses, search_results)


def check_claim_charts(
    invalidity_assessments: list[InvalidityAssessment],
) -> VerificationCheck:
    return _check_claim_charts_impl(invalidity_assessments)


def check_prosecution_history(
    doe_assessments: list[DoEAssessment],
) -> VerificationCheck:
    return _check_prosecution_history_impl(doe_assessments)


def detect_vacuous_pass(
    check: VerificationCheck,
    analyses: list[PatentAnalysis],
    doe_assessments: list[DoEAssessment],
    invalidity_assessments: list[InvalidityAssessment],
) -> Literal["pass", "warning"]:
    return _detect_vacuous_pass_impl(check, analyses, doe_assessments, invalidity_assessments)
