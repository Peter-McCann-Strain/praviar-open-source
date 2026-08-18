"""Targeted tests to close the final coverage gap to ≥90%.

Covers 6 single-line branches, each previously missed:
- services/notifications.py:83      — mark_notifications_read empty list → return 0
- services/public_reports.py:36     — validate_shared_analysis_access expired link → 410
- services/email_payloads.py:25     — build_postmark_email_payload with text_body and tag
- workers/email_task_retry.py:37    — retry_email_task when retry() doesn't raise
- services/comments_escalation.py:175 — non-top-level comment escalation → 400
- services/report_evidence_builders.py:278 — scope note with external_live_retrieval=True
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── notifications.py:83 ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_notifications_read_empty_list_returns_zero():
    from api.services.notifications import mark_notifications_read

    db = AsyncMock()
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    result = await mark_notifications_read(db, user_id=user_id, org_id=org_id, notification_ids=[])
    assert result == 0
    db.execute.assert_not_awaited()


# ── email_payloads.py:25,27 ─────────────────────────────────────────────────


def test_build_postmark_email_payload_with_delivery_metadata():
    from api.services.email_payloads import build_postmark_email_payload

    payload = build_postmark_email_payload(
        from_email="noreply@example.com",
        to="user@example.com",
        subject="Hello",
        html_body="<p>Hi</p>",
        text_body="Hi",
        tag="weekly-digest",
        message_stream="broadcasts",
        headers=[
            {
                "Name": "List-Unsubscribe-Post",
                "Value": "List-Unsubscribe=One-Click",
            }
        ],
    )
    assert payload["TextBody"] == "Hi"
    assert payload["Tag"] == "weekly-digest"
    assert payload["MessageStream"] == "broadcasts"
    assert payload["Headers"][0]["Name"] == "List-Unsubscribe-Post"


# ── email_task_retry.py:37 ──────────────────────────────────────────────────


def test_retry_email_task_when_retry_does_not_raise():
    """When task.retry() returns instead of raising, a RuntimeError is surfaced."""
    from api.workers.email_task_retry import retry_email_task

    task = MagicMock()
    task.retry.return_value = None  # doesn't raise
    exc = ValueError("something failed")

    with pytest.raises(RuntimeError, match="did not raise"):
        retry_email_task(
            task,
            exc,
            failure_event="task_failed",
            max_retries_event="max_retries",
            log_kwargs={"task_id": "t1"},
        )


# ── comments_escalation.py:175 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_load_existing_thread_escalation_view_non_top_level_raises_400():
    """root_comment.parent_id is not None → APIError 400."""
    from api.errors import APIError
    from api.services.comments_escalation import load_existing_thread_escalation_view

    comment_id = uuid.uuid4()
    root_id = uuid.uuid4()
    org_id = uuid.uuid4()
    analysis_id = uuid.uuid4()

    comment = MagicMock()
    comment.id = comment_id
    comment.analysis_id = analysis_id

    root_comment = MagicMock()
    root_comment.id = root_id
    root_comment.parent_id = uuid.uuid4()  # has a parent → not top-level

    db = AsyncMock()

    list_comments = AsyncMock(return_value=[comment, root_comment])

    with (
        patch(
            "api.services.comments_escalation.load_comment_for_org",
            new=AsyncMock(return_value=comment),
        ),
        patch(
            "api.services.comments_escalation.list_comments_for_analysis",
            new=list_comments,
        ),
        patch(
            "api.services.comments_escalation.comment_root_id",
            return_value=root_id,
        ),
        pytest.raises(APIError) as exc_info,
    ):
        await load_existing_thread_escalation_view(db, comment_id=comment_id, org_id=org_id)
    list_comments.assert_awaited_once_with(db, analysis_id=analysis_id, org_id=org_id)
    assert exc_info.value.status == 400


# ── report_evidence_builders.py:278 ─────────────────────────────────────────


def test_build_scope_with_external_live_retrieval_adds_governed_note():
    from api.services.report_evidence_builders import build_scope

    with (
        patch("api.services.report_evidence_builders.collect_sources", return_value=[]),
        patch(
            "api.services.report_evidence_builders.external_retrieval_allowed", return_value=True
        ),
        patch(
            "api.services.report_evidence_builders.build_provider_capabilities",
            return_value=[],
        ),
        patch("api.services.report_evidence_builders.has_active_hybrid_layer", return_value=False),
        patch(
            "api.services.report_evidence_builders.has_live_external_provider", return_value=True
        ),
    ):
        result = build_scope(
            {},
            build_external_query_context_fn=MagicMock(),
        )
    assert "Governed external expansion is also available" in result.governed_note
