"""Pure helpers for normalized prosecution-dossier coverage checks."""

from __future__ import annotations


def _get(dossier, field: str, default=None):
    if isinstance(dossier, dict):
        return dossier.get(field, default)
    return getattr(dossier, field, default)


def _unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result


def dossier_sections(dossier) -> list[str]:
    """Return normalized section names present on a prosecution dossier."""
    if dossier is None:
        return []

    sections = list(_get(dossier, "sections_available", []) or [])
    if _get(dossier, "office_actions_summary", ""):
        sections.append("office_actions")
    if _get(dossier, "continuity_summary", ""):
        sections.append("continuity")
    if _get(dossier, "amendments_summary", ""):
        sections.append("amendments")
    return _unique_strings(sections)


def has_file_wrapper_dossier(dossier) -> bool:
    """True when a dossier contains at least one substantive prosecution section."""
    return bool(dossier_sections(dossier))


def dossier_source_name(dossier) -> str:
    """Return the normalized dossier source name when present."""
    return str(_get(dossier, "source_name", "") or "")
