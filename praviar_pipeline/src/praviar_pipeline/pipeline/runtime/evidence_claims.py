"""Claim-program decision builders for the evidence-fabric runtime substrate.

This module consolidates the prosecution claim-state helpers and the
claim-program decision builder.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Protocol, cast

from pydantic import ValidationError

from praviar_pipeline.clients.primary_legal_status import (
    EvidenceScope,
    PrimaryLegalStatusReceipt,
    PrimaryLegalStatusRequirement,
    resolve_primary_legal_status_receipts,
)
from praviar_pipeline.models.analysis import ElementStatus
from praviar_pipeline.models.patent import (
    LegalStatus,
    has_trusted_legal_status_provenance,
    trusted_claim_text_provenance,
    trusted_legal_status_conflict,
    trusted_legal_status_observations,
)
from praviar_pipeline.models.report import ClaimProgramDecision
from praviar_pipeline.pipeline.accused_acts import (
    accused_act_supports_claim_category,
    governing_accused_act_records,
    normalize_accused_acts,
    past_acts_in_scope,
    regulatory_safe_harbor_review_required,
    territory_supports_jurisdiction,
)
from praviar_pipeline.pipeline.analysis.context_binding import analysis_context_sha256
from praviar_pipeline.pipeline.report.evidence_index_patent_helpers import derive_jurisdiction
from praviar_pipeline.pipeline.report.evidence_index_shared import unique_strings
from praviar_pipeline.utils.claim_parser_parsing import split_claims

if TYPE_CHECKING:
    from praviar_pipeline.models.analysis_claims import ClaimAnalysis
    from praviar_pipeline.models.analysis_patent import PatentAnalysis
    from praviar_pipeline.models.equivalents import DoEAssessment
    from praviar_pipeline.models.invalidity import InvalidityAssessment
    from praviar_pipeline.models.report_decisioning_exposure import FutureRiskFinding
    from praviar_pipeline.models.report_decisioning_prosecution import ProsecutionFinding
    from praviar_pipeline.models.report_document import FTOReport
    from praviar_pipeline.pipeline.runtime.decisioning_coverage import DecisionCoverageContext
    from praviar_pipeline.utils.claim_parser_parsing import ParsedClaim


class VerificationKeyProvider(Protocol):
    """Read-only key lookup boundary for signed legal-status receipts."""

    def verification_key(self, key_id: str) -> bytes: ...


ReceiptVerificationKeys = dict[str, bytes] | VerificationKeyProvider | None

_PATENT_WIDE_ESTOPPEL_FLAGS = frozenset(
    {
        "continuation_lineage",
        "divisional_lineage",
        "cip_lineage",
        "rce_history",
        "interview_history",
        "appeal_history",
    }
)


_CLAIM_SCOPED_ESTOPPEL_FLAGS = frozenset(
    {
        "after_final_response_history",
        "prior_art_rejection_history",
        "written_description_or_indefiniteness_history",
        "double_patenting_history",
        "terminal_disclaimer_history",
        "amendment_after_office_action_history",
    }
)


_HIGH_PROSECUTION_RISK_FLAGS = frozenset(
    {
        "narrowed_claim_scope",
        "after_final_response_history",
        "prior_art_rejection_history",
        "written_description_or_indefiniteness_history",
        "double_patenting_history",
        "terminal_disclaimer",
        "terminal_disclaimer_history",
        "amendment_after_office_action_history",
    }
)


_MEDIUM_PROSECUTION_RISK_FLAGS = frozenset(
    {
        "rejected_during_prosecution",
        "narrowing_signal",
        "pending_family_signal",
        "ptab_challenged",
        "continuation_lineage",
        "divisional_lineage",
        "cip_lineage",
        "rce_history",
        "interview_history",
        "appeal_history",
    }
)


_HIGH_POST_GRANT_FLAGS = frozenset(
    {
        "ptab_challenged",
        "ep_opposition_history",
        "ep_revocation_history",
    }
)


_MEDIUM_POST_GRANT_FLAGS = frozenset(
    {
        "ep_limitation_history",
        "ep_lapse_history",
        "ep_register_pending",
    }
)


_SCOPE_CONSTRAINING_FLAGS = frozenset(
    {
        "narrowed_claim_scope",
        "terminal_disclaimer",
        "terminal_disclaimer_history",
        "continuation_lineage",
        "divisional_lineage",
        "cip_lineage",
        "written_description_or_indefiniteness_history",
        "double_patenting_history",
    }
)

_INACTIVE_LEGAL_STATUSES = frozenset(
    {
        LegalStatus.EXPIRED.value,
        LegalStatus.LAPSED.value,
        LegalStatus.REVOKED.value,
    }
)

_PAST_ACT_MARKERS = frozenset(
    {
        "already_launched",
        "historical_activity",
        "past_activity",
        "past_import",
        "past_manufacture",
        "past_offer_for_sale",
        "past_sale",
        "past_use",
        "prior_activity",
    }
)


@dataclass(slots=True)
class ProsecutionClaimState:
    patent_flags_by_patent: dict[str, list[str]] = field(default_factory=dict)
    claim_scoped_flags: dict[tuple[str, int], list[str]] = field(default_factory=dict)
    all_flags_by_patent: dict[str, list[str]] = field(default_factory=dict)
    rejected_claim_numbers_by_patent: dict[str, set[int]] = field(default_factory=dict)
    narrowing_claim_numbers_by_patent: dict[str, set[int]] = field(default_factory=dict)
    record_basis_by_patent: dict[str, list[str]] = field(default_factory=dict)


@dataclass(slots=True)
class _ProsecutionStateBuilder:
    patent_flags_by_patent: defaultdict[str, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
    claim_scoped_flags: defaultdict[tuple[str, int], list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
    rejected_claim_numbers_by_patent: defaultdict[str, set[int]] = field(
        default_factory=lambda: defaultdict(set)
    )
    narrowing_claim_numbers_by_patent: defaultdict[str, set[int]] = field(
        default_factory=lambda: defaultdict(set)
    )
    record_basis_by_patent: defaultdict[str, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )


@dataclass(frozen=True, slots=True)
class _LegalStatusContext:
    normalized_status: str
    patent_id: str
    jurisdiction: str
    kind_code: str
    issued_kind: bool
    checked_at: datetime


@dataclass(frozen=True, slots=True)
class _PatentDecisionContext:
    detail: object | None
    jurisdiction: str
    accused_acts: list[str]
    historical_acts_in_scope: bool
    exclusively_historical_acts: bool
    regulatory_safe_harbor_review: bool
    territorial_nexus_verified: bool
    analysis_context_verified: bool
    missing_components: list[str]
    prosecution_flags: list[str]
    future_risk_flags: list[str]
    legal_status: str
    legal_status_provenance_verified: bool
    prospective_enforceability: str
    record_basis: list[str]


LegalStatusDecisionState = tuple[str, bool, str]


def literal_risk_from_status(status: str) -> str:
    normalized = str(status or "").lower()
    if normalized == ElementStatus.MET.value:
        return "high"
    if normalized in {ElementStatus.PARTIALLY_MET.value, ElementStatus.UNCLEAR.value}:
        return "medium"
    if normalized == ElementStatus.NOT_MET.value:
        return "low"
    return ""


def _literal_outcome_from_statuses(statuses: list[str]) -> str:
    """Apply all-limitations precedence to a set of claim-element outcomes."""
    if not statuses:
        return ""
    if ElementStatus.NOT_MET.value in statuses:
        return ElementStatus.NOT_MET.value
    if ElementStatus.UNCLEAR.value in statuses:
        return ElementStatus.UNCLEAR.value
    if ElementStatus.PARTIALLY_MET.value in statuses:
        return ElementStatus.PARTIALLY_MET.value
    if all(status == ElementStatus.MET.value for status in statuses):
        return ElementStatus.MET.value
    return ""


def _claim_element_statuses(claim: ClaimAnalysis) -> list[str]:
    statuses = [
        str(getattr(element.status, "value", element.status) or "")
        for element in claim.elements
        if not (
            element.element_number == 0
            and getattr(claim, "preamble_limiting", "unresolved") == "nonlimiting"
        )
    ]
    if (
        getattr(claim, "preamble", "")
        and getattr(claim, "preamble_limiting", "unresolved") == "unresolved"
    ):
        statuses.append(ElementStatus.UNCLEAR.value)
    return statuses


def _dependent_claim_literal_state(
    claim: ClaimAnalysis,
    *,
    own_outcome: str,
    own_record_consistent: bool,
    claims_by_number: dict[int, ClaimAnalysis],
    duplicate_claim_numbers: set[int],
    cache: dict[int, tuple[str, bool]],
    visiting: set[int],
) -> tuple[str, bool]:
    parent_number = claim.depends_on
    parent = claims_by_number.get(parent_number) if parent_number is not None else None
    if parent is None or parent_number == claim.claim_number:
        return "", False
    parent_outcome, parent_consistent = _claim_literal_state(
        parent,
        claims_by_number=claims_by_number,
        duplicate_claim_numbers=duplicate_claim_numbers,
        cache=cache,
        visiting=visiting,
    )
    combined_statuses = [own_outcome] if own_outcome else []
    if parent_outcome:
        combined_statuses.append(parent_outcome)
    return (
        _literal_outcome_from_statuses(combined_statuses),
        own_record_consistent and parent_consistent and bool(parent_outcome),
    )


def _claim_literal_state(
    claim: ClaimAnalysis,
    *,
    claims_by_number: dict[int, ClaimAnalysis],
    duplicate_claim_numbers: set[int],
    cache: dict[int, tuple[str, bool]],
    visiting: set[int] | None = None,
) -> tuple[str, bool]:
    """Resolve literal status across the complete dependent-claim ancestor chain."""
    claim_number = claim.claim_number
    if claim_number in cache:
        return cache[claim_number]
    if claim_number in duplicate_claim_numbers:
        cache[claim_number] = ("", False)
        return cache[claim_number]

    visiting = set(visiting or ())
    if claim_number in visiting:
        cache[claim_number] = ("", False)
        return cache[claim_number]
    visiting.add(claim_number)

    own_outcome = _literal_outcome_from_statuses(_claim_element_statuses(claim))
    reported_outcome = str(getattr(claim.overall_status, "value", claim.overall_status) or "")
    record_consistent = bool(own_outcome and reported_outcome == own_outcome)
    if claim.claim_type == "dependent":
        cache[claim_number] = _dependent_claim_literal_state(
            claim,
            own_outcome=own_outcome,
            own_record_consistent=record_consistent,
            claims_by_number=claims_by_number,
            duplicate_claim_numbers=duplicate_claim_numbers,
            cache=cache,
            visiting=visiting,
        )
        return cache[claim_number]
    if claim.depends_on is not None:
        record_consistent = False
    cache[claim_number] = (
        _literal_outcome_from_statuses([own_outcome] if own_outcome else []),
        record_consistent,
    )
    return cache[claim_number]


def _primary_status_receipts(
    detail,
    *,
    receipt_verification_keys: ReceiptVerificationKeys,
    now: datetime,
) -> dict[str, PrimaryLegalStatusReceipt] | None:
    raw_receipts = list(getattr(detail, "primary_legal_status_receipts", None) or [])
    try:
        receipts = [PrimaryLegalStatusReceipt.model_validate(receipt) for receipt in raw_receipts]
    except ValidationError:
        return None
    if not receipts or receipt_verification_keys is None:
        return None

    attestation_keys: dict[str, bytes] = {}
    for receipt in receipts:
        try:
            if isinstance(receipt_verification_keys, dict):
                key = receipt_verification_keys[receipt.attestation_key_id]
            else:
                key = receipt_verification_keys.verification_key(receipt.attestation_key_id)
        except (AttributeError, KeyError, ValueError):
            return None
        if not isinstance(key, bytes):
            return None
        attestation_keys[receipt.attestation_key_id] = key

    patent_id = str(getattr(detail, "patent_id", "") or "")
    required_scopes: tuple[EvidenceScope, ...] = (
        "application_prosecution",
        "patent_term",
        "patent_maintenance",
        "post_grant_proceeding",
        "current_claim_set",
    )
    requirements = [
        PrimaryLegalStatusRequirement(
            patent_id=patent_id,
            evidence_scope=scope,
        )
        for scope in required_scopes
    ]
    resolution = resolve_primary_legal_status_receipts(
        receipts=receipts,
        requirements=requirements,
        attestation_keys=attestation_keys,
        now=now,
    )
    if not resolution.coverage.satisfied:
        return None

    selected_by_scope: dict[str, PrimaryLegalStatusReceipt] = {
        str(receipt.evidence_scope): receipt for receipt in resolution.selected_receipts
    }
    if set(selected_by_scope) != {requirement.evidence_scope for requirement in requirements}:
        return None
    return selected_by_scope


def _legal_status_context(detail: object, now: datetime | None) -> _LegalStatusContext:
    status = getattr(detail, "legal_status", LegalStatus.UNKNOWN)
    normalized_status = str(getattr(status, "value", status) or "").strip().lower()
    patent_id = str(getattr(detail, "patent_id", "") or "").strip().upper()
    jurisdiction = str(getattr(detail, "jurisdiction", "") or patent_id[:2]).upper()
    kind_match = re.search(r"([A-Z]\d?)$", patent_id)
    kind_code = kind_match.group(1) if kind_match else ""
    return _LegalStatusContext(
        normalized_status=normalized_status,
        patent_id=patent_id,
        jurisdiction=jurisdiction,
        kind_code=kind_code,
        issued_kind=bool(kind_code and kind_code[0] in {"B", "C", "E", "P", "S"}),
        checked_at=now or datetime.now(UTC),
    )


def _pending_or_unresolved(kind_code: str) -> str:
    return "pending" if kind_code.startswith("A") else "unresolved"


def _terminal_us_receipt_state(
    outcomes: dict[str, object],
) -> LegalStatusDecisionState | None:
    if outcomes["application_prosecution"] == "pending":
        return LegalStatus.PENDING.value, True, "pending"
    if outcomes["application_prosecution"] == "abandoned":
        return "abandoned", True, "inactive"
    if outcomes["patent_term"] == "term_expired":
        return LegalStatus.EXPIRED.value, True, "inactive"
    if outcomes["patent_maintenance"] == "lapsed":
        return LegalStatus.LAPSED.value, True, "inactive"
    return None


def _us_receipt_outcomes_are_current(outcomes: dict[str, object]) -> bool:
    return bool(
        outcomes["application_prosecution"] == "patented"
        and outcomes["patent_term"] == "term_current"
        and outcomes["patent_maintenance"]
        in {"paid", "grace_period", "not_yet_due", "not_applicable"}
        and outcomes["post_grant_proceeding"] in {"none_found", "terminated"}
        and outcomes["current_claim_set"] == "claims_current"
    )


def _controlling_expiry(detail: object, term_info: object | None) -> date | None:
    return (
        getattr(term_info, "adjusted_expiry", None)
        or getattr(term_info, "base_expiry", None)
        or getattr(detail, "expiry_date", None)
    )


def _maintenance_status(
    term_info: object | None,
    kind_code: str,
    *,
    normalize: bool,
) -> object:
    status = getattr(term_info, "maintenance_fee_status", "unknown")
    if normalize:
        status = str(status or "unknown")
    if kind_code[0] in {"P", "S"} and status == "unknown":
        return "not_applicable"
    return status


def _current_claim_receipt_matches(
    detail: object,
    claims_receipt: PrimaryLegalStatusReceipt,
) -> bool:
    claims_text = str(getattr(detail, "claims_text", "") or "")
    parsed_claim_ids = {str(claim.claim_number) for claim in split_claims(claims_text)}
    return bool(
        claims_text
        and hashlib.sha256(claims_text.encode("utf-8")).hexdigest()
        == claims_receipt.current_claim_text_sha256
        and parsed_claim_ids == set(claims_receipt.effective_claim_ids)
    )


def _us_legal_status_decision(
    detail: object,
    context: _LegalStatusContext,
    *,
    receipt_verification_keys: ReceiptVerificationKeys,
) -> LegalStatusDecisionState:
    if getattr(detail, "is_granted", None) is not True or not context.issued_kind:
        return context.normalized_status, False, _pending_or_unresolved(context.kind_code)
    primary_receipts = _primary_status_receipts(
        detail,
        receipt_verification_keys=receipt_verification_keys,
        now=context.checked_at,
    )
    if primary_receipts is None:
        return context.normalized_status, False, "unresolved"
    outcomes: dict[str, object] = {
        scope: receipt.normalized_outcome for scope, receipt in primary_receipts.items()
    }
    terminal_state = _terminal_us_receipt_state(outcomes)
    if terminal_state is not None:
        return terminal_state
    if not _us_receipt_outcomes_are_current(outcomes):
        return context.normalized_status, False, "unresolved"

    term_info = getattr(detail, "patent_term_info", None)
    controlling_expiry = _controlling_expiry(detail, term_info)
    if (
        controlling_expiry is None
        or primary_receipts["patent_term"].term_end_date != controlling_expiry
    ):
        return context.normalized_status, False, "unresolved"
    if controlling_expiry <= context.checked_at.date():
        return LegalStatus.EXPIRED.value, True, "inactive"

    maintenance_status = _maintenance_status(
        term_info,
        context.kind_code,
        normalize=True,
    )
    if maintenance_status != "unknown" and maintenance_status != outcomes["patent_maintenance"]:
        return context.normalized_status, False, "unresolved"
    if not _current_claim_receipt_matches(detail, primary_receipts["current_claim_set"]):
        return context.normalized_status, False, "unresolved"
    return LegalStatus.ACTIVE.value, True, "active"


def _trusted_legal_status_decision(
    detail: object,
    context: _LegalStatusContext,
) -> LegalStatusDecisionState:
    if trusted_legal_status_conflict(detail):
        return context.normalized_status, True, "conflicting"
    if not has_trusted_legal_status_provenance(detail):
        return context.normalized_status, False, "unresolved"
    if context.normalized_status != LegalStatus.ACTIVE.value:
        if context.normalized_status in _INACTIVE_LEGAL_STATUSES:
            return context.normalized_status, True, "inactive"
        if context.normalized_status == LegalStatus.PENDING.value:
            return context.normalized_status, True, "pending"
        return context.normalized_status, True, "unresolved"
    if getattr(detail, "is_granted", None) is not True or not context.issued_kind:
        return context.normalized_status, False, _pending_or_unresolved(context.kind_code)
    term_info = getattr(detail, "patent_term_info", None)
    controlling_expiry = _controlling_expiry(detail, term_info)
    if controlling_expiry is not None and controlling_expiry <= context.checked_at.date():
        return context.normalized_status, True, "conflicting"
    if term_info is None or controlling_expiry is None:
        return context.normalized_status, False, "unresolved"
    maintenance_status = _maintenance_status(
        term_info,
        context.kind_code,
        normalize=False,
    )
    if maintenance_status == "unknown":
        return context.normalized_status, False, "unresolved"
    if maintenance_status == "lapsed":
        return context.normalized_status, True, "conflicting"
    return context.normalized_status, True, "active"


def legal_status_decision_state(
    detail: object,
    *,
    receipt_verification_keys: ReceiptVerificationKeys = None,
    now: datetime | None = None,
) -> tuple[str, bool, str]:
    """Return normalized status, provenance validity, and prospective posture."""
    context = _legal_status_context(detail, now)
    if context.jurisdiction == "US":
        return _us_legal_status_decision(
            detail,
            context,
            receipt_verification_keys=receipt_verification_keys,
        )
    return _trusted_legal_status_decision(detail, context)


def _affirmative_doe_supported(assessment) -> bool:
    fwr = getattr(assessment, "fwr", None)
    estoppel = getattr(assessment, "estoppel", None)
    return bool(
        getattr(assessment, "overall_equivalent", None) is True
        and getattr(assessment, "confidence_band", "") == "HIGH"
        and estoppel is not None
        and getattr(estoppel, "estoppel_applies", None) is False
        and getattr(estoppel, "file_wrapper_available", False)
        and fwr is not None
        and all(
            value is True
            for value in (
                getattr(fwr, "same_function", None),
                getattr(fwr, "same_way", None),
                getattr(fwr, "same_result", None),
            )
        )
    )


def _negative_doe_supported(assessment) -> bool:
    """Require a high-confidence, internally supported negative DoE result."""
    fwr = getattr(assessment, "fwr", None)
    estoppel = getattr(assessment, "estoppel", None)
    return bool(
        getattr(assessment, "overall_equivalent", None) is False
        and getattr(assessment, "confidence_band", "") == "HIGH"
        and (
            getattr(estoppel, "estoppel_applies", None) is True
            or (fwr is not None and getattr(fwr, "equivalent", None) is False)
        )
    )


def _claim_ancestor_chain(
    claim: ClaimAnalysis,
    *,
    claims_by_number: dict[int, ClaimAnalysis],
) -> tuple[list[ClaimAnalysis], bool]:
    """Return claim plus ancestors, failing closed on missing/cyclic dependency data."""
    chain: list[ClaimAnalysis] = []
    seen: set[int] = set()
    current: ClaimAnalysis | None = claim
    while current is not None:
        claim_number = current.claim_number
        if claim_number in seen:
            return chain, False
        seen.add(claim_number)
        chain.append(current)
        if current.claim_type != "dependent":
            return chain, current.depends_on is None
        parent_number = current.depends_on
        if parent_number is None:
            return chain, False
        current = claims_by_number.get(parent_number)
        if current is None:
            return chain, False
    return chain, False


def _doe_limitation_state(
    element: object,
    assessments: list[DoEAssessment],
    *,
    jurisdiction: str,
) -> str:
    status_value = getattr(element, "status", "")
    status = str(getattr(status_value, "value", status_value) or "")
    if status == ElementStatus.MET.value:
        return "literal"
    if status == ElementStatus.UNCLEAR.value or jurisdiction != "US":
        return "unresolved"
    affirmative = [item for item in assessments if _affirmative_doe_supported(item)]
    negative = [item for item in assessments if _negative_doe_supported(item)]
    if affirmative and not negative and len(affirmative) == len(assessments):
        return "equivalent"
    if negative and not affirmative and len(negative) == len(assessments):
        return "non_equivalent"
    return "unresolved"


def _doe_states_for_claim(
    claim: ClaimAnalysis,
    *,
    doe_by_claim: dict[tuple[str, int], list[DoEAssessment]],
    patent_id: str,
    jurisdiction: str,
) -> list[str]:
    assessments_by_element: dict[int, list[DoEAssessment]] = defaultdict(list)
    for assessment in doe_by_claim.get((patent_id, claim.claim_number), []):
        assessments_by_element[assessment.element_number].append(assessment)
    return [
        _doe_limitation_state(
            element,
            assessments_by_element.get(element.element_number, []),
            jurisdiction=jurisdiction,
        )
        for element in claim.elements
    ]


def _claim_doe_state(
    claim: ClaimAnalysis,
    *,
    claims_by_number: dict[int, ClaimAnalysis],
    doe_by_claim: dict[tuple[str, int], list[DoEAssessment]],
    patent_id: str,
    jurisdiction: str,
) -> tuple[str, bool]:
    """Aggregate DoE across every unmet limitation in the complete claim chain."""
    chain, chain_complete = _claim_ancestor_chain(
        claim,
        claims_by_number=claims_by_number,
    )
    if not chain_complete:
        return "medium", False

    limitation_states = [
        state
        for chain_claim in chain
        for state in _doe_states_for_claim(
            chain_claim,
            doe_by_claim=doe_by_claim,
            patent_id=patent_id,
            jurisdiction=jurisdiction,
        )
    ]
    if all(state == "literal" for state in limitation_states):
        return "not_assessed", True
    if "non_equivalent" in limitation_states:
        return "low", True
    if "unresolved" in limitation_states:
        return "medium", False
    if "equivalent" in limitation_states:
        return "high", True
    return "medium", False


def _claim_invalidity_strength(assessment, claim_number: int) -> str:
    """Do not use screening/PTAB aggregates to neutralize a current issued claim."""
    if assessment is None:
        return ""
    del claim_number
    # Automated prior-art charts remain screening evidence until their source
    # documents, dates, citations, and claim mapping have a trusted receipt. A
    # provider PTAB aggregate likewise cannot override the separately attested
    # current issued-claim inventory used by prospective decisioning.
    return "weak"


def _claim_elements_by_number(
    claim: ClaimAnalysis | ParsedClaim,
) -> dict[int, str]:
    return {
        element.element_number: _canonical_claim_limitation_text(element.element_text)
        for element in claim.elements
    }


def _analyzed_claim_matches_parsed(
    analyzed_claim: ClaimAnalysis,
    parsed_claim: ParsedClaim,
) -> bool:
    parsed_elements = _claim_elements_by_number(parsed_claim)
    if parsed_claim.preamble:
        parsed_elements[0] = _canonical_claim_limitation_text(parsed_claim.preamble)
    analyzed_elements = _claim_elements_by_number(analyzed_claim)
    if len(analyzed_elements) != len(analyzed_claim.elements):
        return False
    return bool(
        analyzed_claim.claim_type == parsed_claim.claim_type
        and analyzed_claim.depends_on == parsed_claim.depends_on
        and _canonical_claim_limitation_text(analyzed_claim.preamble)
        == _canonical_claim_limitation_text(parsed_claim.preamble)
        and _canonical_claim_limitation_text(analyzed_claim.transitional_phrase or "")
        == _canonical_claim_limitation_text(parsed_claim.transitional_phrase)
        and analyzed_elements == parsed_elements
        and not (
            bool(parsed_claim.preamble)
            and getattr(analyzed_claim, "preamble_limiting", "unresolved") == "unresolved"
        )
    )


def _claim_inventory_alignment(detail, claim_rows: list[ClaimAnalysis]) -> bool:
    """Bind every analyzed limitation to the authoritative parsed claim text."""
    provenance = trusted_claim_text_provenance(detail)
    if provenance is None:
        return False
    parsed_claims = split_claims(str(getattr(detail, "claims_text", "") or ""))
    parsed_by_number = {claim.claim_number: claim for claim in parsed_claims}
    if len(parsed_by_number) != len(parsed_claims):
        return False
    analyzed_by_number = {claim.claim_number: claim for claim in claim_rows}
    if len(analyzed_by_number) != len(claim_rows):
        return False
    if not set(provenance.independent_claim_numbers).issubset(analyzed_by_number):
        return False
    for claim_number, analyzed_claim in analyzed_by_number.items():
        parsed_claim = parsed_by_number.get(claim_number)
        if parsed_claim is None or not _analyzed_claim_matches_parsed(
            analyzed_claim,
            parsed_claim,
        ):
            return False
    return True


def _canonical_claim_limitation_text(value: object) -> str:
    """Normalize Unicode/whitespace while retaining chemistry-critical symbols."""
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(normalized.split())


def _claim_subject_category(claim) -> str:
    text = " ".join(
        [
            str(getattr(claim, "preamble", "") or ""),
            *(str(getattr(element, "element_text", "") or "") for element in claim.elements),
        ]
    ).lower()
    if any(token in text for token in ("treating", "administering", "dosage", "patient")):
        return "method_of_use"
    if any(
        token in text
        for token in ("method of use", "use of ", "method for using", "method of treating")
    ):
        return "method_of_use"
    if any(
        token in text
        for token in (
            "method of making",
            "method for making",
            "process for",
            "producing",
            "manufacturing",
            "synthesizing",
            "synthesising",
        )
    ):
        return "process"
    return "product"


def _past_act_temporal_nexus(
    detail,
    *,
    accused_acts: list[str],
    product_context: object,
    jurisdiction: str,
) -> bool:
    del accused_acts
    jurisdiction_records = governing_accused_act_records(
        product_context,
        jurisdiction=jurisdiction,
    )
    if not jurisdiction_records:
        return False
    historical_records = [
        record
        for record in jurisdiction_records
        if record.status == "actual"
        and record.end_date is not None
        and record.end_date < date.today()
    ]
    if len(historical_records) != len(jurisdiction_records):
        return True
    grant_dates = [
        parsed
        for observation in trusted_legal_status_observations(detail)
        if isinstance(observation.artifact_payload, list)
        for event in observation.artifact_payload
        if str(event.get("event_code") or "").upper() in {"GRANT", "B1", "B2"}
        if (parsed := _parse_iso_date(event.get("event_date"))) is not None
    ]
    if not grant_dates:
        return False
    earliest_grant_date = min(grant_dates)
    expiry_date = getattr(detail, "expiry_date", None)
    return any(
        record.end_date is not None
        and record.end_date >= earliest_grant_date
        and (expiry_date is None or record.start_date <= expiry_date)
        for record in historical_records
    )


def _parse_iso_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _claimed_use_current_claim_context(
    detail,
    *,
    claim_number: int,
    receipt_verification_keys: ReceiptVerificationKeys,
) -> tuple[str, str, list[str]]:
    """Resolve one claim against the attested current claim-set artifact."""
    if detail is None or claim_number < 1:
        return "", "", []
    provenance = trusted_claim_text_provenance(detail)
    claims_text = str(getattr(detail, "claims_text", "") or "")
    if provenance is None or not claims_text:
        return "", "", []
    controlling_claim = next(
        (
            parsed_claim
            for parsed_claim in split_claims(claims_text)
            if parsed_claim.claim_number == claim_number
        ),
        None,
    )
    if controlling_claim is None or not controlling_claim.raw_text.strip():
        return "", "", []
    current_receipts = _primary_status_receipts(
        detail,
        receipt_verification_keys=receipt_verification_keys,
        now=datetime.now(UTC),
    )
    if current_receipts is None:
        return "", "", []
    current_claim_receipt = current_receipts.get("current_claim_set")
    if (
        current_claim_receipt is None
        or current_claim_receipt.current_claim_text_sha256
        != hashlib.sha256(claims_text.encode("utf-8")).hexdigest()
        or str(claim_number) not in current_claim_receipt.effective_claim_ids
        or not current_claim_receipt.controlling_claim_document_ids
    ):
        return "", "", []
    return (
        controlling_claim.raw_text,
        current_claim_receipt.receipt_sha256,
        list(current_claim_receipt.controlling_claim_document_ids),
    )


def _accused_act_nexus_verified(
    claim,
    detail,
    *,
    patent_id: str,
    accused_acts: list[str],
    product_context: object,
    jurisdiction: str,
    analysis_context_verified: bool,
    compound_identity: object,
    receipt_verification_keys: ReceiptVerificationKeys,
) -> bool:
    if not accused_acts or not _past_act_temporal_nexus(
        detail,
        accused_acts=accused_acts,
        product_context=product_context,
        jurisdiction=jurisdiction,
    ):
        return False
    if not territory_supports_jurisdiction(product_context, jurisdiction):
        return False
    if not analysis_context_verified:
        return False
    records = governing_accused_act_records(
        product_context,
        jurisdiction=jurisdiction,
    )
    category = _claim_subject_category(claim) if claim is not None else "product"
    controlling_claim_text = ""
    current_claim_receipt_sha256 = ""
    controlling_claim_document_ids: list[str] = []
    if category == "method_of_use" and claim is not None:
        (
            controlling_claim_text,
            current_claim_receipt_sha256,
            controlling_claim_document_ids,
        ) = _claimed_use_current_claim_context(
            detail,
            claim_number=int(getattr(claim, "claim_number", 0) or 0),
            receipt_verification_keys=receipt_verification_keys,
        )
    return any(
        accused_act_supports_claim_category(
            record,
            claim_category=category,
            jurisdiction=jurisdiction,
            patent_id=patent_id,
            claim_number=int(getattr(claim, "claim_number", 0) or 0),
            controlling_claim_text=controlling_claim_text,
            current_claim_receipt_sha256=current_claim_receipt_sha256,
            controlling_claim_document_ids=controlling_claim_document_ids,
            compound=compound_identity,
            receipt_verification_keys=receipt_verification_keys,
        )
        for record in records
    )


def _decision_missing_components(
    *,
    base_missing_components: list[str],
    has_high_coverage: bool,
    prospective_enforceability: str,
    accused_acts: list[str],
    accused_acts_verified: bool,
    past_acts_in_scope: bool,
    exclusively_historical_acts: bool,
    territorial_nexus_verified: bool,
    regulatory_safe_harbor_review: bool,
    analysis_context_verified: bool,
) -> list[str]:
    missing = list(base_missing_components)
    if not has_high_coverage:
        return missing
    if prospective_enforceability in {"unresolved", "conflicting"}:
        missing.append("trusted_active_legal_status")
    if not analysis_context_verified:
        missing.append("analysis_context_binding")
    if not accused_acts:
        missing.append("accused_acts")
    elif not territorial_nexus_verified:
        missing.append("territorial_nexus")
    elif not accused_acts_verified:
        missing.append("accused_instrumentality_nexus")
    if exclusively_historical_acts or (
        prospective_enforceability == "inactive" and past_acts_in_scope
    ):
        missing.append("historical_exposure_review")
    if regulatory_safe_harbor_review:
        missing.append("regulatory_safe_harbor_review")
    return unique_strings(missing)


def prosecution_risk_level(flags: list[str]) -> str:
    flag_set = set(flags)
    if flag_set.intersection(_HIGH_PROSECUTION_RISK_FLAGS):
        return "high"
    if flag_set.intersection(_MEDIUM_PROSECUTION_RISK_FLAGS):
        return "medium"
    return "low" if flag_set else ""


def post_grant_risk_level(
    prosecution_risk_flags: list[str],
    future_risk_flags: list[str],
) -> str:
    flag_set = set(prosecution_risk_flags)
    future_set = set(future_risk_flags)
    if flag_set.intersection(_HIGH_POST_GRANT_FLAGS) or "ep_opposition" in future_set:
        return "high"
    if flag_set.intersection(_MEDIUM_POST_GRANT_FLAGS):
        return "medium"
    return "low" if flag_set.intersection(_HIGH_POST_GRANT_FLAGS | _MEDIUM_POST_GRANT_FLAGS) else ""


def scope_constrained(flags: list[str]) -> bool:
    return bool(set(flags).intersection(_SCOPE_CONSTRAINING_FLAGS))


def prosecution_rationale(flags: list[str], claim_number: int) -> list[str]:
    notes: list[str] = []
    if "rejected_during_prosecution" in flags:
        notes.append(f"Claim {claim_number} was rejected during prosecution.")
    if "narrowed_claim_scope" in flags:
        notes.append(f"Claim {claim_number} appears to have been narrowed during prosecution.")
    if "after_final_response_history" in flags:
        notes.append("After-final response history increases prosecution estoppel risk.")
    if "ep_opposition_history" in flags:
        notes.append("EP opposition history keeps the claim under active post-grant pressure.")
    return notes


def _base_prosecution_flags(finding: ProsecutionFinding) -> list[str]:
    flags: list[str] = []
    if getattr(finding, "narrowing_signal", False):
        flags.append("narrowing_signal")
    if getattr(finding, "terminal_disclaimer", False):
        flags.append("terminal_disclaimer")
    if getattr(finding, "pending_family_signal", False):
        flags.append("pending_family_signal")
    if getattr(finding, "ptab_challenged", False):
        flags.append("ptab_challenged")
    if getattr(finding, "ep_opposition_event_count", 0):
        flags.append("ep_opposition_history")
    if getattr(finding, "ep_limitation_event_count", 0):
        flags.append("ep_limitation_history")
    if getattr(finding, "ep_revocation_event_count", 0):
        flags.append("ep_revocation_history")
    if getattr(finding, "ep_lapse_event_count", 0):
        flags.append("ep_lapse_history")
    if "pending" in str(getattr(finding, "ep_register_status", "") or "").lower():
        flags.append("ep_register_pending")
    return flags


def _extend_estoppel_flags(
    builder: _ProsecutionStateBuilder,
    finding: ProsecutionFinding,
    *,
    patent_id: str,
) -> None:
    touched_claim_numbers = _claim_touch_numbers(finding)
    for flag in list(getattr(finding, "estoppel_risk_flags", []) or []):
        if flag in _PATENT_WIDE_ESTOPPEL_FLAGS or not touched_claim_numbers:
            builder.patent_flags_by_patent[patent_id].append(flag)
            continue
        if flag in _CLAIM_SCOPED_ESTOPPEL_FLAGS:
            for claim_number in touched_claim_numbers:
                builder.claim_scoped_flags[(patent_id, claim_number)].append(flag)
            continue
        builder.patent_flags_by_patent[patent_id].append(flag)


def _extend_rejection_basis_flags(
    builder: _ProsecutionStateBuilder,
    finding: ProsecutionFinding,
    *,
    patent_id: str,
) -> None:
    for basis in list(getattr(finding, "rejection_bases", []) or []):
        if not basis:
            continue
        rejection_flag = f"rejection_{basis}"
        if builder.rejected_claim_numbers_by_patent.get(patent_id):
            for claim_number in builder.rejected_claim_numbers_by_patent[patent_id]:
                builder.claim_scoped_flags[(patent_id, claim_number)].append(rejection_flag)
        else:
            builder.patent_flags_by_patent[patent_id].append(rejection_flag)


def _ingest_prosecution_finding(
    builder: _ProsecutionStateBuilder,
    finding: ProsecutionFinding,
) -> None:
    patent_id = finding.patent_id
    base_flags = _base_prosecution_flags(finding)
    if base_flags:
        builder.patent_flags_by_patent[patent_id].extend(base_flags)
    builder.record_basis_by_patent[patent_id].extend(
        list(getattr(finding, "record_basis", []) or [])
    )
    builder.rejected_claim_numbers_by_patent[patent_id].update(
        _coerce_claim_numbers(finding, "rejected_claim_numbers")
    )
    builder.narrowing_claim_numbers_by_patent[patent_id].update(
        _coerce_claim_numbers(finding, "narrowing_claim_numbers")
    )
    _extend_estoppel_flags(builder, finding, patent_id=patent_id)
    _extend_rejection_basis_flags(builder, finding, patent_id=patent_id)


def _all_prosecution_flags(
    builder: _ProsecutionStateBuilder,
) -> dict[str, list[str]]:
    all_flags_by_patent: dict[str, list[str]] = {}
    patent_ids = set(builder.patent_flags_by_patent) | {
        patent_id for patent_id, _ in builder.claim_scoped_flags
    }
    for patent_id in patent_ids:
        all_flags_by_patent[patent_id] = unique_strings(
            builder.patent_flags_by_patent.get(patent_id, [])
            + [
                flag
                for (
                    candidate_patent_id,
                    _claim_number,
                ), flags in builder.claim_scoped_flags.items()
                if candidate_patent_id == patent_id
                for flag in flags
            ]
        )
    return all_flags_by_patent


def build_prosecution_claim_state(
    prosecution_findings: list[ProsecutionFinding],
) -> ProsecutionClaimState:
    builder = _ProsecutionStateBuilder()
    for finding in prosecution_findings:
        _ingest_prosecution_finding(builder, finding)

    return ProsecutionClaimState(
        patent_flags_by_patent={
            patent_id: unique_strings(flags)
            for patent_id, flags in builder.patent_flags_by_patent.items()
        },
        claim_scoped_flags={
            key: unique_strings(flags) for key, flags in builder.claim_scoped_flags.items()
        },
        all_flags_by_patent=_all_prosecution_flags(builder),
        rejected_claim_numbers_by_patent=dict(builder.rejected_claim_numbers_by_patent),
        narrowing_claim_numbers_by_patent=dict(builder.narrowing_claim_numbers_by_patent),
        record_basis_by_patent={
            patent_id: unique_strings(flags)
            for patent_id, flags in builder.record_basis_by_patent.items()
        },
    )


def prosecution_flags_for_patent(
    patent_id: str,
    prosecution_state: ProsecutionClaimState,
) -> list[str]:
    return list(prosecution_state.all_flags_by_patent.get(patent_id, []))


def prosecution_flags_for_claim(
    patent_id: str,
    claim_number: int,
    prosecution_state: ProsecutionClaimState,
) -> list[str]:
    return unique_strings(
        prosecution_state.patent_flags_by_patent.get(patent_id, [])
        + prosecution_state.claim_scoped_flags.get((patent_id, claim_number), [])
        + (
            ["rejected_during_prosecution"]
            if claim_number
            in prosecution_state.rejected_claim_numbers_by_patent.get(patent_id, set())
            else []
        )
        + (
            ["narrowed_claim_scope"]
            if claim_number
            in prosecution_state.narrowing_claim_numbers_by_patent.get(patent_id, set())
            else []
        )
    )


def build_future_risk_maps(
    future_risk_findings: list[FutureRiskFinding],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    future_risk_by_patent: dict[str, list[str]] = defaultdict(list)
    future_risk_record_basis_by_patent: dict[str, list[str]] = defaultdict(list)
    for finding in future_risk_findings:
        future_risk_by_patent[finding.patent_id].append(finding.risk_type)
        future_risk_record_basis_by_patent[finding.patent_id].extend(
            list(getattr(finding, "record_basis", []) or [])
        )
    return (
        {patent_id: unique_strings(flags) for patent_id, flags in future_risk_by_patent.items()},
        {
            patent_id: unique_strings(record_basis)
            for patent_id, record_basis in future_risk_record_basis_by_patent.items()
        },
    )


def missing_components_for_patent(
    *,
    patent_id: str,
    coverage_summary,
    required_components: set[str],
) -> list[str]:
    patent_missing_components: list[str] = []
    if (
        "claims_text" in required_components
        and patent_id in coverage_summary.patents_missing_claims
    ):
        patent_missing_components.append("claims_text")
    if (
        "claim_level_analysis" in required_components
        and patent_id in coverage_summary.patents_missing_claim_level_analysis
    ):
        patent_missing_components.append("claim_level_analysis")
    if (
        "authoritative_records" in required_components
        and patent_id in coverage_summary.patents_missing_authoritative_records
    ):
        patent_missing_components.append("authoritative_records")
    if (
        "family_context" in required_components
        and patent_id in coverage_summary.patents_missing_family_context
    ):
        patent_missing_components.append("family_context")
    if (
        "us_prosecution_context" in required_components
        and patent_id in coverage_summary.us_patents_missing_prosecution_context
    ):
        patent_missing_components.append("us_prosecution_context")
    if (
        "us_file_wrapper_dossier" in required_components
        and patent_id in coverage_summary.us_patents_missing_file_wrapper_dossier
    ):
        patent_missing_components.append("us_file_wrapper_dossier")
    if (
        "ep_register_context" in required_components
        and patent_id in coverage_summary.ep_patents_missing_register_context
    ):
        patent_missing_components.append("ep_register_context")
    if "verification" in required_components and coverage_summary.verification_gaps:
        patent_missing_components.append("verification")
    return unique_strings(patent_missing_components)


def _claim_touch_numbers(finding) -> set[int]:
    claim_numbers: set[int] = set()
    claim_numbers.update(_coerce_claim_numbers(finding, "rejected_claim_numbers"))
    claim_numbers.update(_coerce_claim_numbers(finding, "narrowing_claim_numbers"))
    return claim_numbers


def _coerce_claim_numbers(finding, field_name: str) -> set[int]:
    claim_numbers: set[int] = set()
    for claim_number in list(getattr(finding, field_name, []) or []):
        if isinstance(claim_number, int):
            claim_numbers.add(claim_number)
        elif str(claim_number).isdigit():
            claim_numbers.add(int(claim_number))
    return claim_numbers


def _doe_assessments_by_claim(
    report: FTOReport,
) -> dict[tuple[str, int], list[DoEAssessment]]:
    assessments_by_claim: dict[tuple[str, int], list[DoEAssessment]] = defaultdict(list)
    for assessment in report.doe_assessments:
        assessments_by_claim[(assessment.patent_id, assessment.claim_number)].append(assessment)
    return assessments_by_claim


def _invalidity_assessments_by_claim(
    report: FTOReport,
) -> dict[tuple[str, int], InvalidityAssessment]:
    assessments_by_claim: dict[tuple[str, int], InvalidityAssessment] = {}
    for assessment in report.invalidity_assessments:
        exact_claim_numbers = {
            chart.claim_number for chart in getattr(assessment, "claim_charts", []) or []
        }.union(getattr(getattr(assessment, "ptab", None), "all_claims_cancelled", []) or [])
        for claim_number in exact_claim_numbers:
            assessments_by_claim[(assessment.patent_id, claim_number)] = assessment
    return assessments_by_claim


def _patent_decision_context(
    analysis: PatentAnalysis,
    *,
    report: FTOReport,
    detail: object | None,
    coverage_context: DecisionCoverageContext,
    required_components: set[str],
    prosecution_state: ProsecutionClaimState,
    future_risk_by_patent: dict[str, list[str]],
    future_risk_record_basis_by_patent: dict[str, list[str]],
    intended_actions: list[str] | None,
    product_context: object,
    target_jurisdictions: list[str] | None,
    development_stage: object,
    receipt_verification_keys: ReceiptVerificationKeys,
) -> _PatentDecisionContext:
    jurisdiction = derive_jurisdiction(analysis.patent_id, detail)
    accused_acts = normalize_accused_acts(
        intended_actions,
        product_context,
        jurisdiction=jurisdiction,
    )
    historical_acts_in_scope = past_acts_in_scope(accused_acts)
    exclusively_historical_acts = bool(accused_acts) and all(
        action.startswith("past_") for action in accused_acts
    )
    regulatory_safe_harbor_review = regulatory_safe_harbor_review_required(
        accused_acts=accused_acts,
        product_context=product_context,
        development_stage=development_stage,
        jurisdiction=jurisdiction,
    )
    territorial_nexus_verified = territory_supports_jurisdiction(
        product_context,
        jurisdiction,
    )
    analysis_context_verified = getattr(
        analysis, "analysis_context_sha256", ""
    ) == analysis_context_sha256(
        patent_id=analysis.patent_id,
        compound_identity=report.compound,
        product_context=product_context,
        intended_actions=intended_actions,
        target_jurisdictions=target_jurisdictions,
        development_stage=development_stage,
    )
    missing_components = missing_components_for_patent(
        patent_id=analysis.patent_id,
        coverage_summary=coverage_context.coverage_summary,
        required_components=required_components,
    )
    prosecution_flags = prosecution_flags_for_patent(
        analysis.patent_id,
        prosecution_state,
    )
    future_risk_flags = unique_strings(future_risk_by_patent.get(analysis.patent_id, []))
    legal_status, legal_status_provenance_verified, prospective_enforceability = (
        legal_status_decision_state(
            detail,
            receipt_verification_keys=receipt_verification_keys,
        )
    )
    record_basis = unique_strings(
        prosecution_state.record_basis_by_patent.get(analysis.patent_id, [])
        + future_risk_record_basis_by_patent.get(analysis.patent_id, [])
        + (
            ["trusted_legal_status"]
            if legal_status_provenance_verified and prospective_enforceability != "conflicting"
            else []
        )
        + [f"accused_act:{action}" for action in accused_acts]
    )
    return _PatentDecisionContext(
        detail=detail,
        jurisdiction=jurisdiction,
        accused_acts=accused_acts,
        historical_acts_in_scope=historical_acts_in_scope,
        exclusively_historical_acts=exclusively_historical_acts,
        regulatory_safe_harbor_review=regulatory_safe_harbor_review,
        territorial_nexus_verified=territorial_nexus_verified,
        analysis_context_verified=analysis_context_verified,
        missing_components=missing_components,
        prosecution_flags=prosecution_flags,
        future_risk_flags=future_risk_flags,
        legal_status=legal_status,
        legal_status_provenance_verified=legal_status_provenance_verified,
        prospective_enforceability=prospective_enforceability,
        record_basis=record_basis,
    )


def _analysis_level_decision(
    analysis: PatentAnalysis,
    context: _PatentDecisionContext,
    *,
    report: FTOReport,
    product_context: object,
    prosecution_state: ProsecutionClaimState,
    receipt_verification_keys: ReceiptVerificationKeys,
) -> ClaimProgramDecision:
    literal_risk = getattr(analysis.risk_level, "value", "") if analysis.risk_level else ""
    accused_acts_verified = _accused_act_nexus_verified(
        None,
        context.detail,
        patent_id=analysis.patent_id,
        accused_acts=context.accused_acts,
        product_context=product_context,
        jurisdiction=context.jurisdiction,
        analysis_context_verified=context.analysis_context_verified,
        compound_identity=report.compound,
        receipt_verification_keys=receipt_verification_keys,
    )
    decision_missing_components = _decision_missing_components(
        base_missing_components=context.missing_components,
        has_high_coverage=literal_risk == "high",
        prospective_enforceability=context.prospective_enforceability,
        accused_acts=context.accused_acts,
        accused_acts_verified=accused_acts_verified,
        past_acts_in_scope=context.historical_acts_in_scope,
        exclusively_historical_acts=context.exclusively_historical_acts,
        territorial_nexus_verified=context.territorial_nexus_verified,
        regulatory_safe_harbor_review=context.regulatory_safe_harbor_review,
        analysis_context_verified=context.analysis_context_verified,
    )
    return ClaimProgramDecision(
        patent_id=analysis.patent_id,
        claim_number=0,
        jurisdiction=context.jurisdiction,
        literal_outcome="unknown",
        literal_risk=literal_risk,
        doe_risk="not_assessed",
        invalidity_strength="",
        prosecution_risk_flags=context.prosecution_flags,
        prosecution_risk_level=prosecution_risk_level(context.prosecution_flags),
        post_grant_risk_level=post_grant_risk_level(
            prosecution_state.patent_flags_by_patent.get(analysis.patent_id, []),
            context.future_risk_flags,
        ),
        scope_constrained=scope_constrained(context.prosecution_flags),
        future_risk_flags=context.future_risk_flags,
        legal_status=context.legal_status,
        legal_status_provenance_verified=context.legal_status_provenance_verified,
        prospective_enforceability=context.prospective_enforceability,
        accused_acts=context.accused_acts,
        accused_acts_verified=accused_acts_verified,
        past_acts_in_scope=context.historical_acts_in_scope,
        commercial_severity=analysis.risk_level.value,
        evidence_sufficient=not decision_missing_components,
        missing_components=decision_missing_components,
        record_basis=context.record_basis,
        rationale=[analysis.risk_summary] if analysis.risk_summary else [],
    )


def _claim_number_index(
    claim_rows: list[ClaimAnalysis],
) -> tuple[dict[int, ClaimAnalysis], set[int]]:
    claim_number_counts: dict[int, int] = defaultdict(int)
    for claim in claim_rows:
        claim_number_counts[claim.claim_number] += 1
    duplicate_claim_numbers = {
        claim_number for claim_number, count in claim_number_counts.items() if count > 1
    }
    return (
        {claim.claim_number: claim for claim in claim_rows},
        duplicate_claim_numbers,
    )


def _claim_level_decisions(
    analysis: PatentAnalysis,
    claim_rows: list[ClaimAnalysis],
    context: _PatentDecisionContext,
    *,
    report: FTOReport,
    doe_by_claim: dict[tuple[str, int], list[DoEAssessment]],
    invalidity_by_claim: dict[tuple[str, int], InvalidityAssessment],
    prosecution_state: ProsecutionClaimState,
    product_context: object,
    receipt_verification_keys: ReceiptVerificationKeys,
) -> list[ClaimProgramDecision]:
    claims_by_number, duplicate_claim_numbers = _claim_number_index(claim_rows)
    claim_literal_state_cache: dict[int, tuple[str, bool]] = {}
    claim_inventory_aligned = _claim_inventory_alignment(context.detail, claim_rows)
    decisions: list[ClaimProgramDecision] = []
    for claim in claim_rows:
        invalidity = invalidity_by_claim.get((analysis.patent_id, claim.claim_number))
        prosecution_risk_flags = prosecution_flags_for_claim(
            analysis.patent_id,
            claim.claim_number,
            prosecution_state,
        )
        literal_outcome, claim_element_record_consistent = _claim_literal_state(
            claim,
            claims_by_number=claims_by_number,
            duplicate_claim_numbers=duplicate_claim_numbers,
            cache=claim_literal_state_cache,
        )
        literal_risk = literal_risk_from_status(literal_outcome)
        doe_risk, doe_record_complete = _claim_doe_state(
            claim,
            claims_by_number=claims_by_number,
            doe_by_claim=doe_by_claim,
            patent_id=analysis.patent_id,
            jurisdiction=context.jurisdiction,
        )
        accused_acts_verified = _accused_act_nexus_verified(
            claim,
            context.detail,
            patent_id=analysis.patent_id,
            accused_acts=context.accused_acts,
            product_context=product_context,
            jurisdiction=context.jurisdiction,
            analysis_context_verified=context.analysis_context_verified,
            compound_identity=report.compound,
            receipt_verification_keys=receipt_verification_keys,
        )
        decision_missing_components = _decision_missing_components(
            base_missing_components=(
                context.missing_components
                + ([] if claim_element_record_consistent else ["claim_element_analysis"])
                + ([] if claim_inventory_aligned else ["claim_inventory_alignment"])
                + ([] if doe_record_complete else ["doe_all_limitations"])
            ),
            has_high_coverage=literal_risk == "high" or doe_risk == "high",
            prospective_enforceability=context.prospective_enforceability,
            accused_acts=context.accused_acts,
            accused_acts_verified=accused_acts_verified,
            past_acts_in_scope=context.historical_acts_in_scope,
            exclusively_historical_acts=context.exclusively_historical_acts,
            territorial_nexus_verified=context.territorial_nexus_verified,
            regulatory_safe_harbor_review=context.regulatory_safe_harbor_review,
            analysis_context_verified=context.analysis_context_verified,
        )
        decisions.append(
            ClaimProgramDecision(
                patent_id=analysis.patent_id,
                claim_number=claim.claim_number,
                jurisdiction=context.jurisdiction,
                literal_outcome=literal_outcome,
                literal_risk=literal_risk,
                doe_risk=doe_risk,
                invalidity_strength=_claim_invalidity_strength(
                    invalidity,
                    claim.claim_number,
                ),
                prosecution_risk_flags=prosecution_risk_flags,
                prosecution_risk_level=prosecution_risk_level(prosecution_risk_flags),
                post_grant_risk_level=post_grant_risk_level(
                    prosecution_risk_flags,
                    context.future_risk_flags,
                ),
                scope_constrained=scope_constrained(prosecution_risk_flags),
                future_risk_flags=context.future_risk_flags,
                legal_status=context.legal_status,
                legal_status_provenance_verified=context.legal_status_provenance_verified,
                prospective_enforceability=context.prospective_enforceability,
                accused_acts=context.accused_acts,
                accused_acts_verified=accused_acts_verified,
                past_acts_in_scope=context.historical_acts_in_scope,
                commercial_severity=getattr(analysis.risk_level, "value", "") or "medium",
                evidence_sufficient=not decision_missing_components,
                missing_components=decision_missing_components,
                record_basis=context.record_basis,
                rationale=unique_strings(
                    [claim.reasoning, analysis.risk_summary]
                    + prosecution_rationale(
                        prosecution_risk_flags,
                        claim.claim_number,
                    )
                    + (
                        ["Claim remains only screening-grade because the record is incomplete."]
                        if decision_missing_components
                        else []
                    )
                ),
            )
        )
    return decisions


def build_claim_program_decisions(
    *,
    report: object,
    detail_map: dict[str, object],
    coverage_context: object,
    intended_actions: list[str] | None = None,
    product_context: object = None,
    target_jurisdictions: list[str] | None = None,
    development_stage: object = None,
    receipt_verification_keys: ReceiptVerificationKeys = None,
) -> list[ClaimProgramDecision]:
    """Build claim-scoped decision objects from current patent analyses."""
    typed_report = cast("FTOReport", report)
    typed_coverage_context = cast("DecisionCoverageContext", coverage_context)
    required_components = set(
        getattr(typed_coverage_context, "required_record_components", []) or []
    )
    prosecution_state = build_prosecution_claim_state(typed_coverage_context.prosecution_findings)
    future_risk_by_patent, future_risk_record_basis_by_patent = build_future_risk_maps(
        typed_coverage_context.future_risk
    )
    doe_by_claim = _doe_assessments_by_claim(typed_report)
    invalidity_by_claim = _invalidity_assessments_by_claim(typed_report)

    decisions: list[ClaimProgramDecision] = []
    for analysis in typed_report.patent_analyses:
        detail = detail_map.get(analysis.patent_id)
        context = _patent_decision_context(
            analysis,
            report=typed_report,
            detail=detail,
            coverage_context=typed_coverage_context,
            required_components=required_components,
            prosecution_state=prosecution_state,
            future_risk_by_patent=future_risk_by_patent,
            future_risk_record_basis_by_patent=future_risk_record_basis_by_patent,
            intended_actions=intended_actions,
            product_context=product_context,
            target_jurisdictions=target_jurisdictions,
            development_stage=development_stage,
            receipt_verification_keys=receipt_verification_keys,
        )
        claim_rows = getattr(analysis, "claims_analyzed", []) or []
        if not claim_rows:
            decisions.append(
                _analysis_level_decision(
                    analysis,
                    context,
                    report=typed_report,
                    product_context=product_context,
                    prosecution_state=prosecution_state,
                    receipt_verification_keys=receipt_verification_keys,
                )
            )
            continue
        decisions.extend(
            _claim_level_decisions(
                analysis,
                claim_rows,
                context,
                report=typed_report,
                doe_by_claim=doe_by_claim,
                invalidity_by_claim=invalidity_by_claim,
                prosecution_state=prosecution_state,
                product_context=product_context,
                receipt_verification_keys=receipt_verification_keys,
            )
        )

    return decisions
