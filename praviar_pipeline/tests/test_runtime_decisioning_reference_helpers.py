from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.models.patent import LegalStatus
from praviar_pipeline.pipeline.runtime.decisioning_references import (
    inactive_ep_register_status,
    normalized_legal_status,
    primary_reference_source,
)


def test_primary_reference_source_uses_priority_order() -> None:
    assert primary_reference_source(["family_members", "patent_term_info"]) == "patent_term_info"


def test_normalized_legal_status_handles_enum_and_plain_values() -> None:
    assert normalized_legal_status(SimpleNamespace(legal_status=LegalStatus.REVOKED)) == "revoked"
    assert normalized_legal_status(SimpleNamespace(legal_status="expired")) == "expired"


def test_inactive_ep_register_status_filters_active_statuses() -> None:
    assert inactive_ep_register_status(
        SimpleNamespace(ep_register_status="Application refused")
    ) == ("Application refused")
    assert inactive_ep_register_status(SimpleNamespace(ep_register_status="Granted")) == ""
