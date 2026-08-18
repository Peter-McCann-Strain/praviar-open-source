"""White-label branding configuration for report generation.

Supports custom logos, firm names, colors, disclaimers, and privilege markings
for law firm and enterprise customers.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from praviar_pipeline.models.report import REPORT_DISCLAIMER
from praviar_pipeline.rendering.design import BRAND_ACCENT, BRAND_INK

SUPPORTED_BRANDING_LOGO_EXTENSIONS = frozenset({".jpeg", ".jpg", ".png", ".svg"})
SUPPORTED_OFFICE_BRANDING_LOGO_EXTENSIONS = frozenset({".jpeg", ".jpg", ".png"})
NEUTRAL_LEGAL_MARKING = "CONFIDENTIAL DRAFT"


class BrandingConfig(BaseModel):
    """Per-organization branding for white-label reports."""

    model_config = ConfigDict(extra="forbid")

    # Identity
    logo_path: str | None = Field(
        default=None,
        description=(
            "Path to firm/company logo. PDF supports PNG, JPEG, and SVG; "
            "Office exports support PNG and JPEG."
        ),
    )
    firm_name: str | None = Field(
        default=None,
        description="Firm or company name. Replaces 'Praviar' in headers when set.",
    )

    # Colors (hex strings)
    primary_color: str = Field(
        default=BRAND_INK,
        description="Primary header/accent color in hex (e.g. '#0B1F24').",
    )
    accent_color: str = Field(
        default=BRAND_ACCENT,
        description="Secondary accent color in hex (e.g. '#0E6F68').",
    )

    # Legal markings
    disclaimer_text: str | None = Field(
        default=None,
        description="Custom disclaimer text. If None, uses Praviar default.",
    )
    privilege_header: str | None = Field(
        default=None,
        description=(
            "Legacy organization-supplied marking. It is never rendered as a "
            "privilege assertion without a server-owned authorization record."
        ),
    )
    confidentiality_footer: str | None = Field(
        default=None,
        description="Custom confidentiality footer text for every page.",
    )

    # Document metadata
    matter_number: str | None = Field(
        default=None,
        description="Client matter or reference number shown on cover page.",
    )
    prepared_by: str | None = Field(
        default=None,
        description="Attorney or analyst name shown on cover page.",
    )

    # Layout
    page_size: str = Field(
        default="us-letter",
        description="Page size: 'us-letter' (8.5x11) or 'a4'.",
    )

    # Law firm details
    client_name: str | None = Field(
        default=None,
        description="Client name for matter identification on cover page.",
    )
    attorney_name: str | None = Field(
        default=None,
        description="Reviewing attorney name shown on cover page and sign-off.",
    )
    attorney_email: str | None = Field(
        default=None,
        description="Reviewing attorney contact email.",
    )
    firm_address: str | None = Field(
        default=None,
        description="Firm address for cover page footer.",
    )
    report_classification: str | None = Field(
        default=None,
        description=(
            "Document classification level supplied by counsel or policy "
            "(for example, 'CONFIDENTIAL DRAFT' or 'CLIENT CONFIDENTIAL')."
        ),
    )

    # Branding controls
    hide_praviar_pipeline_branding: bool = Field(
        default=False,
        description="Remove all Praviar branding from output (full white-label mode).",
    )

    @field_validator("primary_color", "accent_color")
    @classmethod
    def _validate_hex_color(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("#") or len(v) != 7:
            raise ValueError(f"Color must be 7-char hex (e.g. '#0B1F24'), got '{v}'")
        try:
            int(v[1:], 16)
        except ValueError as e:
            raise ValueError(f"Invalid hex color: '{v}'") from e
        return v

    @field_validator("page_size")
    @classmethod
    def _validate_page_size(cls, v: str) -> str:
        if v not in ("us-letter", "a4"):
            raise ValueError(f"page_size must be 'us-letter' or 'a4', got '{v}'")
        return v

    @model_validator(mode="after")
    def _validate_logo_identity(self) -> BrandingConfig:
        has_firm_name = bool(self.firm_name and self.firm_name.strip())
        if self.logo_path and not has_firm_name and not self.hide_praviar_pipeline_branding:
            raise ValueError(
                "logo_path requires firm_name or hide_praviar_pipeline_branding=True "
                "so a custom logo is never paired with the Praviar name"
            )
        return self

    @property
    def display_name(self) -> str:
        """Name to show in headers - firm name or 'Praviar'."""
        if self.hide_praviar_pipeline_branding:
            return self.firm_name or "FTO Analysis"
        return self.firm_name or "Praviar"

    @property
    def has_logo(self) -> bool:
        """Whether a valid logo file exists."""
        if not self.logo_path:
            return False
        return Path(self.logo_path).is_file()

    @property
    def suppresses_praviar_branding(self) -> bool:
        """Whether visible default Praviar branding should be suppressed."""
        return self.hide_praviar_pipeline_branding or bool(self.logo_path)

    @property
    def header_text(self) -> str:
        """Neutral server-governed page header; never self-assert privilege."""
        display = self.display_name
        report_label = display if display.endswith("FTO Analysis") else f"{display} FTO Analysis"
        return f"{NEUTRAL_LEGAL_MARKING} | {report_label}"

    @property
    def legal_marking(self) -> str:
        """Return the fail-closed marking while no authorization model exists."""
        return NEUTRAL_LEGAL_MARKING

    @property
    def effective_disclaimer_text(self) -> str:
        """Keep the mandatory disclaimer and append any organization notice."""
        custom = str(self.disclaimer_text or "").strip()
        if not custom or custom == REPORT_DISCLAIMER.strip():
            return REPORT_DISCLAIMER
        return f"{REPORT_DISCLAIMER}\n\nAdditional organization notice:\n{custom}"

    @property
    def footer_text(self) -> str:
        """Text for page footers."""
        if self.confidentiality_footer:
            return self.confidentiality_footer
        if self.suppresses_praviar_branding:
            return "CONFIDENTIAL"
        return "CONFIDENTIAL -- Generated by Praviar"


def format_artifact_title(branding: BrandingConfig, artifact_label: str) -> str:
    """Return a visible artifact title without duplicated FTO wording."""
    display_name = " ".join((branding.display_name or "FTO Analysis").split())
    label = " ".join(str(artifact_label or "").split())
    if not label:
        return display_name

    display_casefold = display_name.casefold()
    label_casefold = label.casefold()
    if label_casefold.startswith(f"{display_casefold} "):
        return label
    if display_casefold == "fto analysis" and label_casefold.startswith("fto "):
        return f"FTO Analysis {label[4:].strip()}".strip()
    return f"{display_name} {label}"


def get_default_branding() -> BrandingConfig:
    """Return default Praviar branding."""
    return BrandingConfig()


def resolve_branding_logo_path(
    branding: BrandingConfig,
    *,
    renderer_name: str,
    supported_extensions: frozenset[str] = SUPPORTED_BRANDING_LOGO_EXTENSIONS,
) -> Path | None:
    """Return a fail-closed logo path suitable for the target renderer."""
    if not branding.logo_path:
        return None

    logo_path = Path(branding.logo_path).expanduser()
    if not logo_path.is_file():
        raise RuntimeError(f"Branding logo not found for {renderer_name}: {logo_path}")

    suffix = logo_path.suffix.lower()
    if suffix not in supported_extensions:
        supported = ", ".join(sorted(supported_extensions))
        raise RuntimeError(
            f"{renderer_name} does not support branding logo format "
            f"'{suffix}'. Supported: {supported}"
        )

    return logo_path
