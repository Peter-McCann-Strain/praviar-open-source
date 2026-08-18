"""Prosecution history estoppel helpers for doctrine of equivalents."""

from __future__ import annotations

from praviar_pipeline.models.equivalents import ClaimAmendment, EstoppelResult
from praviar_pipeline.utils.prosecution_history import fetch_prosecution_history


def _build_surrendered_scope(narrowing_amendments: list[ClaimAmendment]) -> str:
    if not narrowing_amendments:
        return ""
    amendments_desc = [
        (
            f"Amendment on {amendment.amendment_date.isoformat()}"
            if amendment.amendment_date
            else "unknown date"
        )
        for amendment in narrowing_amendments[:5]
    ]
    scopes = [
        amendment.surrendered_scope.strip()
        for amendment in narrowing_amendments
        if amendment.surrendered_scope.strip()
    ]
    return (
        f"Found {len(narrowing_amendments)} candidate amendment(s): "
        f"{'; '.join(amendments_desc)}. "
        + (
            "Recorded surrendered territory: " + "; ".join(scopes[:5])
            if scopes
            else "The exact surrendered territory is unresolved."
        )
    )


def _format_amendments_found(narrowing_amendments: list[ClaimAmendment]) -> list[str]:
    return [
        f"{amendment.amendment_type} (claim {amendment.claim_number}, "
        f"{amendment.amendment_date.isoformat() if amendment.amendment_date else 'undated'})"
        for amendment in narrowing_amendments[:10]
    ]


async def check_estoppel(patent_id: str) -> EstoppelResult:
    """Check prosecution history for narrowing amendments that bar DoE."""
    history = await fetch_prosecution_history(patent_id)

    file_wrapper_available = bool(history.application_number)
    if not history.amendments and not history.rejections:
        return EstoppelResult(
            file_wrapper_available=file_wrapper_available,
            estoppel_applies=False
            if file_wrapper_available and history.prosecution_complete
            else None,
        )

    narrowing_amendments = [
        amendment
        for amendment in history.amendments
        if amendment.narrowing and amendment.response_to_rejection
    ]
    rejections_found = [str(value) for value in {r.rejection_type for r in history.rejections}]
    complete_candidates = [
        amendment
        for amendment in narrowing_amendments
        if amendment.patentability_related is True and bool(amendment.surrendered_scope.strip())
    ]
    unrebutted = [
        amendment
        for amendment in complete_candidates
        if amendment.festo_rebuttal == "not_established"
    ]
    successfully_rebutted = [
        amendment
        for amendment in complete_candidates
        if amendment.festo_rebuttal in {"unforeseeable", "tangential", "other_reason"}
    ]

    if unrebutted:
        estoppel_applies: bool | None = True
    elif (
        history.prosecution_complete
        and complete_candidates
        and len(successfully_rebutted) == len(complete_candidates)
        and len(complete_candidates) == len(narrowing_amendments)
    ) or (history.prosecution_complete and not narrowing_amendments):
        estoppel_applies = False
    else:
        estoppel_applies = None

    return EstoppelResult(
        amendments_found=_format_amendments_found(narrowing_amendments),
        estoppel_applies=estoppel_applies,
        surrendered_scope=_build_surrendered_scope(narrowing_amendments),
        file_wrapper_available=file_wrapper_available,
        rejections_found=rejections_found,
        prosecution_narrowing_count=len(narrowing_amendments),
    )
