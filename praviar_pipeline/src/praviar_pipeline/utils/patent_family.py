"""Deterministic patent-family member status helpers."""

from __future__ import annotations


def family_member_id(member: object) -> str:
    """Return a normalized publication identifier for a family member."""
    country = str(getattr(member, "country", "") or "").upper()
    doc_number = str(getattr(member, "doc_number", "") or "").upper()
    normalized_doc_number = (
        doc_number if doc_number.startswith(country) else f"{country}{doc_number}"
    )
    kind = str(getattr(member, "kind", "") or "").upper()
    return f"{normalized_doc_number}{kind}" if normalized_doc_number or kind else ""


def pending_family_member_ids(members: list[object]) -> list[str]:
    """Return verified A-publication applications without a same-application grant."""
    normalized_members = list(members or [])
    granted_keys = {
        application_key
        for member in normalized_members
        if str(getattr(member, "kind", "") or "").upper().startswith(("B", "C"))
        if (application_key := _member_application_key(member)) is not None
    }
    return [
        member_id
        for member in normalized_members
        if str(getattr(member, "kind", "") or "").upper().startswith("A")
        and (application_key := _member_application_key(member)) is not None
        and application_key not in granted_keys
        if (member_id := family_member_id(member))
    ]


def unresolved_family_member_ids(members: list[object]) -> list[str]:
    """Return A-publications whose application identity is not authoritative."""
    return [
        member_id
        for member in list(members or [])
        if str(getattr(member, "kind", "") or "").upper().startswith("A")
        and _member_application_key(member) is None
        if (member_id := family_member_id(member))
    ]


def _member_application_key(member: object) -> tuple[str, str] | None:
    country = str(getattr(member, "country", "") or "").upper()
    if not bool(getattr(member, "application_identity_verified", False)):
        return None
    application_number = "".join(
        character
        for character in str(getattr(member, "application_number", "") or "").upper()
        if character.isalnum()
    )
    if not country or not application_number:
        return None
    return country, application_number


__all__ = [
    "family_member_id",
    "pending_family_member_ids",
    "unresolved_family_member_ids",
]
