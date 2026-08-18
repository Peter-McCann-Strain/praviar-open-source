from praviar_pipeline.rendering.branding import BrandingConfig


def test_custom_disclaimer_can_only_append_to_mandatory_disclaimer() -> None:
    branding = BrandingConfig(disclaimer_text="Organization-specific notice.")

    assert branding.effective_disclaimer_text.startswith("IMPORTANT:")
    assert "does NOT constitute legal advice" in branding.effective_disclaimer_text
    assert branding.effective_disclaimer_text.endswith("Organization-specific notice.")


def test_untrusted_privilege_fields_fail_closed_to_neutral_marking() -> None:
    branding = BrandingConfig(
        privilege_header="PRIVILEGED AND CONFIDENTIAL — ATTORNEY WORK PRODUCT",
        report_classification="ATTORNEY-CLIENT PRIVILEGED",
    )

    assert branding.legal_marking == "CONFIDENTIAL DRAFT"
    assert "PRIVILEGED" not in branding.header_text
