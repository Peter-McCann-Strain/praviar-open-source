from __future__ import annotations

from praviar_pipeline.models.analysis_validation import (
    coerce_enum_value,
    warn_missing_claim_evidence,
)


def test_coerce_enum_value_normalizes_and_falls_back() -> None:
    value = coerce_enum_value(
        " Patent Attorney ",
        valid_values={"patent_attorney", "business_analyst"},
        default="patent_attorney",
        log_event="perspective_coerced",
        replace_spaces=True,
    )

    assert value == "patent_attorney"


def test_coerce_enum_value_preserves_none() -> None:
    assert (
        coerce_enum_value(
            None,
            valid_values={"high", "medium"},
            default="medium",
            log_event="risk_level_coerced",
        )
        is None
    )


def test_warn_missing_claim_evidence_allows_unclear_and_present_evidence() -> None:
    warn_missing_claim_evidence("unclear", "")
    warn_missing_claim_evidence("met", "quoted support")
