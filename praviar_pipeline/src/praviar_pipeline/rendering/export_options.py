"""Shared export scope and audience contract for report renderers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from praviar_pipeline.rendering.audience_projection import (
    AUDIENCE_PROJECTION_SCHEMA_VERSION,
    AudienceField,
    AudienceProjectionPolicy,
    audience_projection_policy,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

EXPORT_SECTION_IDS: tuple[str, ...] = (
    "executive_summary",
    "patent_analysis",
    "claim_charts",
    "invalidity_assessment",
    "audit_trail",
    "pipeline_metadata",
)
DEFAULT_EXPORT_SECTION_IDS: tuple[str, ...] = EXPORT_SECTION_IDS
EXPORT_AUDIENCE_IDS: tuple[str, ...] = (
    "full",
    "executive",
    "attorney",
    "scientist",
    "investor",
)

EXPORT_SECTION_LABELS: dict[str, str] = {
    "executive_summary": "Executive Summary",
    "patent_analysis": "Patent Analysis",
    "claim_charts": "Claim Charts",
    "invalidity_assessment": "Invalidity Assessment",
    "audit_trail": "Audit Trail",
    "pipeline_metadata": "Pipeline Metadata",
}

EXPORT_AUDIENCE_LABELS: dict[str, str] = {
    "full": "Full Report",
    "executive": "Executive Brief",
    "attorney": "Patent Counsel",
    "scientist": "R&D Brief",
    "investor": "Investor Pack",
}

EXPORT_FORMAT_LABELS: dict[str, str] = {
    "pdf": "PDF Report",
    "docx": "Word Review Memo",
    "pptx": "Board Deck",
    "csv": "CSV Data",
    "xlsx": "Excel Spreadsheet",
    "json": "JSON Data",
}

_SECTION_SET = frozenset(EXPORT_SECTION_IDS)
_AUDIENCE_SET = frozenset(EXPORT_AUDIENCE_IDS)


@dataclass(frozen=True)
class ExportRenderOptions:
    """Normalized export scope passed from API jobs into artifact renderers.

    Empty/omitted sections preserve the historical full-report behavior for
    direct renderer calls and older queued jobs. Interactive export UI sends an
    explicit non-empty section list, which is enforced as the scoped contract.
    """

    sections: tuple[str, ...] = DEFAULT_EXPORT_SECTION_IDS
    audience: str = "full"

    @classmethod
    def from_values(
        cls,
        sections: Iterable[str] | None = None,
        *,
        audience: str | None = "full",
    ) -> ExportRenderOptions:
        normalized_sections = _normalize_sections(sections)
        normalized_audience = _normalize_audience(audience)
        return cls(sections=normalized_sections, audience=normalized_audience)

    def includes(self, *section_ids: str) -> bool:
        """Return true when audience policy and caller scope both admit a section."""
        return self.projection_policy.includes_section(self.sections, *section_ids)

    def allows(self, field: AudienceField) -> bool:
        """Return true when the versioned audience field allowlist admits a group."""
        return self.projection_policy.allows(field)

    @property
    def projection_policy(self) -> AudienceProjectionPolicy:
        return audience_projection_policy(self.audience)

    @property
    def section_labels(self) -> tuple[str, ...]:
        return tuple(EXPORT_SECTION_LABELS[section_id] for section_id in self.effective_sections)

    @property
    def effective_sections(self) -> tuple[str, ...]:
        """Caller scope intersected with the immutable audience allowlist."""
        allowed = self.projection_policy.allowed_sections
        return tuple(section_id for section_id in self.sections if section_id in allowed)

    @property
    def audience_label(self) -> str:
        return EXPORT_AUDIENCE_LABELS[self.audience]

    def model_dump(self) -> dict[str, object]:
        return {
            "sections": list(self.effective_sections),
            "section_labels": list(self.section_labels),
            "audience": self.audience,
            "audience_label": self.audience_label,
            "audience_schema_version": AUDIENCE_PROJECTION_SCHEMA_VERSION,
        }


def _normalize_sections(sections: Iterable[str] | None) -> tuple[str, ...]:
    if sections is None:
        return DEFAULT_EXPORT_SECTION_IDS

    selected = tuple(dict.fromkeys(str(section) for section in sections if str(section)))
    if not selected:
        return DEFAULT_EXPORT_SECTION_IDS

    unknown = sorted(set(selected) - _SECTION_SET)
    if unknown:
        raise ValueError(f"Unknown export section ids: {', '.join(unknown)}")

    return tuple(section_id for section_id in EXPORT_SECTION_IDS if section_id in selected)


def _normalize_audience(audience: str | None) -> str:
    normalized = str(audience or "full")
    if normalized not in _AUDIENCE_SET:
        raise ValueError(f"Unknown export audience: {normalized}")
    return normalized


def default_export_options() -> ExportRenderOptions:
    return ExportRenderOptions()


def export_audience_label(audience: str | None) -> str:
    """Return the human label for an export audience id."""
    normalized = str(audience or "full")
    return EXPORT_AUDIENCE_LABELS.get(normalized, normalized)


def export_format_label(export_format: str | None) -> str:
    """Return the human label for an export format id."""
    normalized = str(export_format or "").lower()
    return EXPORT_FORMAT_LABELS.get(normalized, str(export_format or ""))


def export_artifact_title(audience: str | None, export_format: str | None) -> str:
    """Return the display title used in receipts and export previews."""
    audience_label = export_audience_label(audience)
    format_label = export_format_label(export_format)
    if not format_label:
        return audience_label
    return f"{audience_label} · {format_label}"
