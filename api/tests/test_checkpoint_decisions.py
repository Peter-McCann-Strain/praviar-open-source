from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from praviar_pipeline.models.hitl import CheckpointType  # type: ignore[import-not-found]

from api.db.models import UserRole
from api.deps import PERMISSION_MATRIX
from api.errors import APIError
from api.schemas.checkpoint_decisions import (
    CheckpointDecisionIn,
    report_review_attestation_note,
)
from api.services.checkpoint_decisions import (
    _apply_existing_decision,
    _validate_checkpoint_binding,
)
from api.workers.tasks import _build_checkpoint_decision_provider


def test_checkpoint_reject_requires_note() -> None:
    with pytest.raises(ValueError, match="note is required"):
        CheckpointDecisionIn(
            checkpoint_type="analysis_review",
            decision="reject",
            note="",
        )


def test_checkpoint_decision_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError):
        CheckpointDecisionIn(
            checkpoint_type="analysis_review",
            decision="approve",
            pipeline_mode="advanced",  # type: ignore[call-arg]
        )


def test_identity_approval_requires_a_persisted_attestation_note() -> None:
    with pytest.raises(ValueError, match="resolved identity checkpoint"):
        CheckpointDecisionIn(
            checkpoint_type="identity_review",
            decision="approve",
            note="",
        )


@pytest.mark.parametrize(
    ("digest", "note"),
    [
        (None, ""),
        ("a" * 64, "Looks good"),
        ("a" * 64, report_review_attestation_note("b" * 64)),
    ],
)
def test_report_approval_requires_exact_full_digest_attestation(
    digest: str | None,
    note: str,
) -> None:
    with pytest.raises(ValueError, match="review_payload_sha256|exact review payload"):
        CheckpointDecisionIn(
            checkpoint_type="report_review",
            decision="approve",
            note=note,
            review_payload_sha256=digest,
        )


def test_report_checkpoint_id_must_match_full_attestation_digest() -> None:
    digest = "a" * 64
    body = CheckpointDecisionIn(
        checkpoint_type="report_review",
        decision="approve",
        note=report_review_attestation_note(digest),
        review_payload_sha256=digest,
    )

    _validate_checkpoint_binding(
        checkpoint_id=f"run-1:report_review:{digest[:16]}",
        body=body,
    )
    with pytest.raises(APIError, match="does not match"):
        _validate_checkpoint_binding(
            checkpoint_id=f"run-1:report_review:{'b' * 16}",
            body=body,
        )


def test_identity_decision_is_idempotent_but_immutable() -> None:
    reviewer_id = uuid.uuid4()
    existing = SimpleNamespace(
        checkpoint_type="identity_review",
        decision="approve",
        note="Reviewed exact identity envelope.",
        reviewer_id=reviewer_id,
        reviewed_at=datetime.now(UTC),
    )
    body = CheckpointDecisionIn(
        checkpoint_type="identity_review",
        decision="approve",
        note="Reviewed exact identity envelope.",
    )

    returned, action = _apply_existing_decision(
        existing,
        user=SimpleNamespace(id=reviewer_id),
        body=body,
    )

    assert returned is existing
    assert action == "checkpoint_decision.replay"

    with pytest.raises(APIError, match="immutable"):
        _apply_existing_decision(
            existing,
            user=SimpleNamespace(id=reviewer_id),
            body=CheckpointDecisionIn(
                checkpoint_type="identity_review",
                decision="reject",
                note="Changed after approval.",
            ),
        )


def test_digest_bound_report_approval_is_idempotent_but_immutable() -> None:
    digest = "c" * 64
    note = report_review_attestation_note(digest)
    reviewer_id = uuid.uuid4()
    existing = SimpleNamespace(
        checkpoint_type="report_review",
        decision="approve",
        note=note,
        reviewer_id=reviewer_id,
        reviewed_at=datetime.now(UTC),
    )
    body = CheckpointDecisionIn(
        checkpoint_type="report_review",
        decision="approve",
        note=note,
        review_payload_sha256=digest,
    )

    returned, action = _apply_existing_decision(
        existing,
        user=SimpleNamespace(id=reviewer_id),
        body=body,
    )
    assert returned is existing
    assert action == "checkpoint_decision.replay"

    with pytest.raises(APIError, match="immutable"):
        _apply_existing_decision(
            existing,
            user=SimpleNamespace(id=reviewer_id),
            body=CheckpointDecisionIn(
                checkpoint_type="report_review",
                decision="reject",
                note="The evidence ledger needs correction.",
            ),
        )


def test_checkpoint_decision_permission_includes_review_roles() -> None:
    assert PERMISSION_MATRIX["checkpoint_decision.create"] == {
        UserRole.ADMIN,
        UserRole.ATTORNEY,
        UserRole.SCIENTIST,
    }


def test_worker_checkpoint_decision_provider_reads_persisted_approval() -> None:
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    reviewer_id = uuid.uuid4()
    reviewed_at = datetime.now(UTC)

    decision_db = MagicMock()
    decision_db.__enter__.return_value = decision_db
    query = decision_db.query.return_value
    query.filter.return_value.one_or_none.return_value = SimpleNamespace(
        checkpoint_type="analysis_review",
        decision="approve",
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        note="Looks good",
    )

    with (
        patch("api.workers.tasks.Session", return_value=decision_db) as session_factory,
        patch("api.db.session.bind_org_to_sync_session") as bind_org,
    ):
        provider = _build_checkpoint_decision_provider(
            runtime=SimpleNamespace(engine=object()),
            analysis_id=str(analysis_id),
            org_id=str(org_id),
        )
        decision = provider(
            CheckpointType.ANALYSIS_REVIEW,
            {"checkpoint_id": "run-1:analysis_review"},
        )

    assert decision is not None
    assert decision.checkpoint_type == CheckpointType.ANALYSIS_REVIEW
    assert decision.action == "approve"
    assert decision.reviewer_id == str(reviewer_id)
    assert decision.reviewed_at == reviewed_at
    assert decision.notes == "Looks good"
    session_factory.assert_called_once()
    bind_org.assert_called_once_with(decision_db, str(org_id))


def test_worker_checkpoint_decision_provider_ignores_type_mismatch() -> None:
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    decision_db = MagicMock()
    decision_db.__enter__.return_value = decision_db
    query = decision_db.query.return_value
    query.filter.return_value.one_or_none.return_value = SimpleNamespace(
        checkpoint_type="report_review",
        decision="approve",
        reviewer_id=uuid.uuid4(),
        reviewed_at=datetime.now(UTC),
        note="Wrong checkpoint",
    )

    with (
        patch("api.workers.tasks.Session", return_value=decision_db),
        patch("api.db.session.bind_org_to_sync_session"),
    ):
        provider = _build_checkpoint_decision_provider(
            runtime=SimpleNamespace(engine=object()),
            analysis_id=str(analysis_id),
            org_id=str(org_id),
        )
        decision = provider(
            CheckpointType.ANALYSIS_REVIEW,
            {"checkpoint_id": "run-1:analysis_review"},
        )

    assert decision is None


@pytest.mark.parametrize(
    "stored_note", ["", "Looks good", report_review_attestation_note("b" * 64)]
)
def test_worker_provider_rejects_unbound_report_approval(stored_note: str) -> None:
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    digest = "a" * 64
    decision_db = MagicMock()
    decision_db.__enter__.return_value = decision_db
    decision_db.query.return_value.filter.return_value.one_or_none.return_value = SimpleNamespace(
        checkpoint_type="report_review",
        decision="approve",
        reviewer_id=uuid.uuid4(),
        reviewed_at=datetime.now(UTC),
        note=stored_note,
    )

    with (
        patch("api.workers.tasks.Session", return_value=decision_db),
        patch("api.db.session.bind_org_to_sync_session"),
    ):
        provider = _build_checkpoint_decision_provider(
            runtime=SimpleNamespace(engine=object()),
            analysis_id=str(analysis_id),
            org_id=str(org_id),
        )
        decision = provider(
            CheckpointType.REPORT_REVIEW,
            {
                "checkpoint_id": f"run-1:report_review:{digest[:16]}",
                "review_payload_sha256": digest,
            },
        )

    assert decision is None


def test_worker_provider_accepts_exact_digest_bound_report_approval() -> None:
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    digest = "d" * 64
    decision_db = MagicMock()
    decision_db.__enter__.return_value = decision_db
    decision_db.query.return_value.filter.return_value.one_or_none.return_value = SimpleNamespace(
        checkpoint_type="report_review",
        decision="approve",
        reviewer_id=uuid.uuid4(),
        reviewed_at=datetime.now(UTC),
        note=report_review_attestation_note(digest),
    )

    with (
        patch("api.workers.tasks.Session", return_value=decision_db),
        patch("api.db.session.bind_org_to_sync_session"),
    ):
        provider = _build_checkpoint_decision_provider(
            runtime=SimpleNamespace(engine=object()),
            analysis_id=str(analysis_id),
            org_id=str(org_id),
        )
        decision = provider(
            CheckpointType.REPORT_REVIEW,
            {
                "checkpoint_id": f"run-1:report_review:{digest[:16]}",
                "review_payload_sha256": digest,
            },
        )

    assert decision is not None
    assert decision.action == "approve"
    assert decision.notes == report_review_attestation_note(digest)
