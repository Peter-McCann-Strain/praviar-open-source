"""Pure prosecution-history helpers.

The public facade stays in ``prosecution_history.py`` so existing imports and
patch points keep working. This module holds the deterministic parsing and data
shaping logic that can be exercised directly in focused tests.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from praviar_pipeline.models.equivalents import ClaimAmendment, RejectionRecord

# Document code classification for USPTO file wrapper documents
REJECTION_CODES = {"CTNF", "CTFR", "OA"}  # Non-final OA, Final OA, Office Action
RESPONSE_CODES = {"RES", "A.."}  # Response, Amendment
NOTICE_CODES = {"NOA"}  # Notice of Allowance
TD_CODES = {"DIST"}  # Terminal Disclaimer
RejectionType = Literal["102", "103", "112_a", "112_b", "101", "other"]


def classify_document(doc: dict) -> str:
    """Classify a file wrapper document by its document code."""
    code = doc.get("documentCode", "").upper().strip()
    desc = doc.get("documentDescription", "").lower()

    if code in REJECTION_CODES or "office action" in desc:
        return "rejection"
    if code in RESPONSE_CODES or "response" in desc or "amendment" in desc:
        return "response"
    if code in NOTICE_CODES or "notice of allowance" in desc:
        return "notice_of_allowance"
    if code in TD_CODES or "terminal disclaimer" in desc:
        return "terminal_disclaimer"
    return "other"


def extract_rejection_type(doc: dict) -> RejectionType:
    """Infer the rejection type from document description."""
    desc = doc.get("documentDescription", "").lower()
    code = doc.get("documentCode", "").upper()

    if "102" in desc:
        return "102"
    if "103" in desc:
        return "103"
    if "112(a)" in desc or "112 first" in desc or "written description" in desc:
        return "112_a"
    if "112(b)" in desc or "112 second" in desc or "indefiniteness" in desc:
        return "112_b"
    if "101" in desc:
        return "101"
    if code in ("CTNF", "CTFR"):
        return "other"
    return "other"


def parse_optional_date(value: str) -> date | None:
    """Parse a date prefix when present, returning ``None`` for empty values."""
    if not value:
        return None
    return date.fromisoformat(value[:10])


def extract_application_number(app_data: dict, meta: dict) -> str:
    """Return the best available application number from ODP payloads."""
    return str(
        app_data.get("applicationNumberText", "")
        or meta.get("applicationNumber", "")
        or app_data.get("applicationNumber", "")
        or ""
    )


def extract_filing_date(meta: dict) -> date | None:
    """Return the filing date when it can be parsed safely."""
    filing_str = meta.get("filingDate", "")
    if not filing_str:
        return None
    try:
        return parse_optional_date(filing_str)
    except ValueError:
        return None


def extract_grant_date(meta: dict, app_data: dict) -> date | None:
    """Return the grant date when it can be parsed safely."""
    grant_str = meta.get("grantDate", "")
    if not grant_str:
        grant_str = app_data.get("grantDocumentMetaData", {}).get("grantDate", "")
    if not grant_str:
        return None
    try:
        return parse_optional_date(grant_str)
    except ValueError:
        return None


def extract_inventor_names(meta: dict, patent_id: str) -> list[str]:
    """Return inventor names while filtering ODP patent-number noise."""
    inventors: list[str] = []
    for inv in meta.get("inventorBag", []):
        name = inv.get("inventorNameText", "")
        if name and name != patent_id:
            inventors.append(name)
    return inventors


def extract_examiner_name(meta: dict) -> str:
    """Return the examiner name from application metadata."""
    return str(meta.get("examinerNameText", "") or "")


def extract_attorney_name(app_data: dict) -> str:
    """Return the attorney registration number when available."""
    attorney = ""
    attorney_data = app_data.get("recordAttorney", {})
    if isinstance(attorney_data, dict):
        attorney = attorney_data.get("registrationNumber", "")
    return attorney


def extract_current_assignee(app_data: dict) -> str:
    """Return the current owner from the most recent assignment."""
    current_assignee = ""
    assignments = app_data.get("assignmentBag", [])
    if assignments:
        latest = assignments[0]
        current_assignee = latest.get("conveyanceText", "")
    return current_assignee


def build_rejections_from_office_actions(oa_data: list[dict]) -> list[RejectionRecord]:
    """Normalize structured office-action records into rejection models."""
    rejections: list[RejectionRecord] = []
    for oa in oa_data:
        rej_type: RejectionType = "other"
        basis = oa.get("rejectionBasis", "")
        if "102" in basis:
            rej_type = "102"
        elif "103" in basis:
            rej_type = "103"
        elif "112" in basis:
            rej_type = "112_a" if "first" in basis.lower() else "112_b"
        elif "101" in basis:
            rej_type = "101"

        claims = oa.get("claimsRejected", [])
        if isinstance(claims, list):
            claims = [int(c) for c in claims if str(c).isdigit()]

        prior_art = oa.get("citedReferences", [])
        if isinstance(prior_art, list):
            prior_art = [str(r) for r in prior_art]

        rejections.append(
            RejectionRecord(
                rejection_type=rej_type,
                claims_rejected=claims,
                prior_art_cited=prior_art,
                rejection_basis=basis,
            )
        )
    return rejections


def build_rejections_from_documents(documents: list[dict]) -> list[RejectionRecord]:
    """Fallback rejection records derived from file-wrapper metadata."""
    rejections: list[RejectionRecord] = []
    for doc in documents:
        if classify_document(doc) == "rejection":
            rejections.append(
                RejectionRecord(
                    rejection_type=extract_rejection_type(doc),
                    rejection_basis=doc.get("documentDescription", ""),
                )
            )
    return rejections


def identify_narrowing_amendments(documents: list[dict]) -> list[ClaimAmendment]:
    """Identify response documents that likely narrow claims."""
    amendments: list[ClaimAmendment] = []
    responses = [doc for doc in documents if classify_document(doc) == "response"]
    rejections = [doc for doc in documents if classify_document(doc) == "rejection"]

    for resp in responses:
        resp_date = parse_optional_date(resp.get("documentDate", ""))

        is_response_to_rejection = False
        for rej in rejections:
            rej_date = parse_optional_date(rej.get("documentDate", ""))
            if resp_date and rej_date and rej_date < resp_date:
                is_response_to_rejection = True
                break

        desc = resp.get("documentDescription", "")
        if "amendment" in desc.lower() or is_response_to_rejection:
            amendments.append(
                ClaimAmendment(
                    claim_number=0,
                    amendment_date=resp_date,
                    amendment_type="amended",
                    narrowing=is_response_to_rejection,
                    response_to_rejection=is_response_to_rejection,
                )
            )

    return amendments


def extract_applicant_arguments(documents: list[dict]) -> list[str]:
    """Extract applicant arguments from response descriptions."""
    return [
        doc.get("documentDescription", "")
        for doc in documents
        if classify_document(doc) == "response" and doc.get("documentDescription")
    ]


def count_documents_of_type(documents: list[dict], doc_type: str) -> int:
    """Count documents that match a classified document type."""
    return sum(1 for document in documents if classify_document(document) == doc_type)
