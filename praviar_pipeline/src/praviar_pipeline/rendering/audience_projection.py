"""Versioned, policy-owned audience projections for report artifacts."""

from __future__ import annotations

import enum
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

AUDIENCE_PROJECTION_SCHEMA_VERSION: Final[Literal["audience-projection-v1"]] = (
    "audience-projection-v1"
)


class AudienceField(enum.StrEnum):
    """Report field groups admitted to a rendered audience contract."""

    EXECUTIVE_SUMMARY = "executive_summary"
    COMPOUND_PROFILE = "compound_profile"
    METHODOLOGY = "methodology"
    PATENT_LANDSCAPE = "patent_landscape"
    PATENT_IDENTIFIERS = "patent_identifiers"
    PATENT_DETAIL = "patent_detail"
    CLAIM_CHARTS = "claim_charts"
    INVALIDITY_DETAIL = "invalidity_detail"
    SOURCE_AUDIT = "source_audit"
    AUDIT_TRAIL = "audit_trail"
    PIPELINE_METADATA = "pipeline_metadata"
    RECOMMENDATIONS = "recommendations"


class AudienceProjectionPolicy(BaseModel):
    """Immutable allowlist for one audience projection schema version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["audience-projection-v1"] = AUDIENCE_PROJECTION_SCHEMA_VERSION
    audience: Literal["full", "executive", "attorney", "scientist", "investor"]
    allowed_sections: frozenset[str]
    allowed_fields: frozenset[AudienceField]

    def allows(self, field: AudienceField) -> bool:
        return field in self.allowed_fields

    def includes_section(self, requested_sections: tuple[str, ...], *section_ids: str) -> bool:
        return any(
            section_id in self.allowed_sections and section_id in requested_sections
            for section_id in section_ids
        )


_SUMMARY_FIELDS = frozenset(
    {
        AudienceField.EXECUTIVE_SUMMARY,
        AudienceField.SOURCE_AUDIT,
        AudienceField.RECOMMENDATIONS,
    }
)
_SCIENTIST_FIELDS = _SUMMARY_FIELDS | frozenset(
    {
        AudienceField.COMPOUND_PROFILE,
        AudienceField.METHODOLOGY,
        AudienceField.PATENT_LANDSCAPE,
        AudienceField.PATENT_IDENTIFIERS,
    }
)
_FULL_FIELDS = frozenset(AudienceField)

AUDIENCE_PROJECTION_POLICIES: dict[str, AudienceProjectionPolicy] = {
    "executive": AudienceProjectionPolicy(
        audience="executive",
        allowed_sections=frozenset({"executive_summary"}),
        allowed_fields=_SUMMARY_FIELDS,
    ),
    "investor": AudienceProjectionPolicy(
        audience="investor",
        allowed_sections=frozenset({"executive_summary"}),
        allowed_fields=_SUMMARY_FIELDS,
    ),
    "scientist": AudienceProjectionPolicy(
        audience="scientist",
        allowed_sections=frozenset({"executive_summary", "patent_analysis"}),
        allowed_fields=_SCIENTIST_FIELDS,
    ),
    "attorney": AudienceProjectionPolicy(
        audience="attorney",
        allowed_sections=frozenset(
            {
                "executive_summary",
                "patent_analysis",
                "claim_charts",
                "invalidity_assessment",
                "audit_trail",
                "pipeline_metadata",
            }
        ),
        allowed_fields=_FULL_FIELDS,
    ),
    "full": AudienceProjectionPolicy(
        audience="full",
        allowed_sections=frozenset(
            {
                "executive_summary",
                "patent_analysis",
                "claim_charts",
                "invalidity_assessment",
                "audit_trail",
                "pipeline_metadata",
            }
        ),
        allowed_fields=_FULL_FIELDS,
    ),
}


def audience_projection_policy(audience: str) -> AudienceProjectionPolicy:
    """Return the reviewed audience allowlist or fail closed for an unknown id."""
    try:
        return AUDIENCE_PROJECTION_POLICIES[audience]
    except KeyError as exc:
        raise ValueError(f"Unknown export audience projection: {audience}") from exc
