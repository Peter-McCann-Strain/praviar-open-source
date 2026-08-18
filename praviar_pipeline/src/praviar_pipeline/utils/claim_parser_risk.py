"""Deterministic risk rules for parsed patent claims."""

from __future__ import annotations

_STATUS_ALIASES = {
    "met": "met",
    "partially_met": "partially_met",
    "unclear": "unclear",
    "not_met": "not_met",
}

_CLAIM_TYPE_ALIASES = {
    "dependent": "dependent",
    "dependent_claim": "dependent",
    "independent": "independent",
    "independent_claim": "independent",
}


def _normalise_claim_type(value: object) -> str:
    claim_type = "" if value is None else str(value).strip().lower()
    claim_type = claim_type.replace("-", "_").replace(" ", "_")
    if claim_type not in _CLAIM_TYPE_ALIASES:
        raise ValueError(f"Unsupported claim type: {value!r}")
    return _CLAIM_TYPE_ALIASES[claim_type]


def _normalise_element_status(value: object) -> str:
    if value is None:
        return "unclear"
    status = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if not status:
        return "unclear"
    if status not in _STATUS_ALIASES:
        raise ValueError(f"Unsupported claim element status: {value!r}")
    return _STATUS_ALIASES[status]


def _element_statuses(claim: dict) -> list[str]:
    return [
        _normalise_element_status(element.get("status", "unclear"))
        for element in claim.get("elements", [])
    ]


def compute_risk_from_claims(claims: list[dict]) -> str:
    """Compute risk level deterministically from claim analysis results."""
    claims_with_statuses = [
        (claim, _normalise_claim_type(claim.get("claim_type")), _element_statuses(claim))
        for claim in claims
    ]
    independent_claims = [
        (claim, statuses)
        for claim, claim_type, statuses in claims_with_statuses
        if claim_type == "independent"
    ]
    if not independent_claims:
        independent_claims = [
            (claim, statuses) for claim, _claim_type, statuses in claims_with_statuses
        ]
    if not independent_claims:
        return "medium"

    for _claim, statuses in independent_claims:
        if statuses and all(status == "met" for status in statuses):
            return "high"

    if any(not statuses for _claim, statuses in independent_claims):
        return "medium"

    for _claim, statuses in independent_claims:
        if statuses and set(statuses) == {"unclear"}:
            return "medium"

    for _claim, statuses in independent_claims:
        if "unclear" in statuses:
            return "medium"

    for _claim, statuses in independent_claims:
        if (
            statuses
            and all(status in ("met", "partially_met", "unclear") for status in statuses)
            and any(status == "met" for status in statuses)
        ):
            return "medium"

    for _claim, statuses in independent_claims:
        if any(status in ("met", "partially_met") for status in statuses):
            return "low"

    return "clear"
