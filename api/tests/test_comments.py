"""Tests for /api/v1/comments endpoints."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from conftest import (
    _build_app,
    make_analysis_mock,
    make_comment_mock,
    make_mock_db,
    make_user,
    mock_org_check_pass,
)
from httpx import ASGITransport

from api.db.models import Notification, NotificationType, UserRole
from api.db.models_collaboration import CommentAssignmentEvent
from api.ratelimit import limiter
from api.services.comments_crud import (
    list_comments_for_analysis,
    list_org_review_queue_rows,
)


@asynccontextmanager
async def _make_client_for_user(user, db=None):
    if db is None:
        db = make_mock_db()
    app = _build_app(user, db)
    mock_engine = AsyncMock()
    mock_startup_session = AsyncMock()
    mock_startup_session.__aenter__ = AsyncMock(return_value=mock_startup_session)
    mock_startup_session.__aexit__ = AsyncMock(return_value=False)
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock()
    mock_redis.aclose = AsyncMock()

    async def _no_cache(*_args, **_kwargs):
        return None

    prev_enabled = limiter.enabled
    limiter.enabled = False
    with (
        patch("api.main.engine", mock_engine),
        patch("api.db.session.async_session_factory", return_value=mock_startup_session),
        patch("redis.asyncio.from_url", return_value=mock_redis),
        patch("api.cache.get_cached_report", side_effect=_no_cache),
        patch("api.cache.set_cached_report", side_effect=_no_cache),
    ):
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c, db
    limiter.enabled = prev_enabled


# ---------------------------------------------------------------------------
# POST /api/v1/comments
# ---------------------------------------------------------------------------


class TestCreateComment:
    @pytest.mark.asyncio
    async def test_create_comment_as_scientist(self, scientist_client):
        c, db = scientist_client
        analysis_id = uuid.uuid4()
        mock_org_check_pass(db)

        resp = await c.post(
            "/api/v1/comments",
            json={
                "analysis_id": str(analysis_id),
                "body": "Flagging patent US93000001A1 for review.",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert "created_at" in data
        db.add.assert_called_once()
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_create_comment_as_attorney(self, attorney_client):
        c, db = attorney_client
        mock_org_check_pass(db)
        resp = await c.post(
            "/api/v1/comments",
            json={
                "analysis_id": str(uuid.uuid4()),
                "body": "Attorney review complete.",
            },
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_comment_with_parent(self, scientist_client):
        c, db = scientist_client
        analysis_id = uuid.uuid4()
        parent_id = uuid.uuid4()
        org_check_result = MagicMock()
        org_check_result.scalar_one_or_none.return_value = analysis_id
        parent_result = MagicMock()
        parent_result.scalar_one_or_none.return_value = make_comment_mock(
            id=parent_id,
            analysis_id=analysis_id,
        )
        db.execute = AsyncMock(side_effect=[org_check_result, parent_result])

        resp = await c.post(
            "/api/v1/comments",
            json={
                "analysis_id": str(analysis_id),
                "body": "Replying to the above comment.",
                "parent_id": str(parent_id),
            },
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_comment_rejects_parent_from_different_analysis(self, scientist_client):
        c, db = scientist_client
        analysis_id = uuid.uuid4()
        parent_id = uuid.uuid4()
        org_check_result = MagicMock()
        org_check_result.scalar_one_or_none.return_value = analysis_id
        parent_result = MagicMock()
        parent_result.scalar_one_or_none.return_value = make_comment_mock(
            id=parent_id,
            analysis_id=uuid.uuid4(),
        )
        db.execute = AsyncMock(side_effect=[org_check_result, parent_result])

        resp = await c.post(
            "/api/v1/comments",
            json={
                "analysis_id": str(analysis_id),
                "body": "Replying to the wrong analysis.",
                "parent_id": str(parent_id),
            },
        )
        assert resp.status_code == 422
        assert "same analysis" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_comment_with_mentions(self, scientist_client):
        c, db = scientist_client
        mock_org_check_pass(db)
        resp = await c.post(
            "/api/v1/comments",
            json={
                "analysis_id": str(uuid.uuid4()),
                "body": "Hey @attorney, please check this.",
                "mentions": ["user_clerk_id_1"],
            },
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_comment_with_target(self, scientist_client):
        c, db = scientist_client
        mock_org_check_pass(db)
        resp = await c.post(
            "/api/v1/comments",
            json={
                "analysis_id": str(uuid.uuid4()),
                "body": "Specific comment on claim 1.",
                "target_type": "claim",
                "target_id": "US93000001A1-claim-1",
            },
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_comment_cross_org_rejected(self, scientist_client):
        """Attempting to comment on an analysis from another org returns 404."""
        c, db = scientist_client
        # Default mock returns None for scalar_one_or_none (no matching analysis)
        resp = await c.post(
            "/api/v1/comments",
            json={
                "analysis_id": str(uuid.uuid4()),
                "body": "Cross-org comment attempt.",
            },
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_comment_forbidden_for_client(self, client_role_client):
        c, _db = client_role_client
        resp = await c.post(
            "/api/v1/comments",
            json={
                "analysis_id": str(uuid.uuid4()),
                "body": "A client comment.",
            },
        )
        assert resp.status_code == 403
        assert "Cannot comment" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_comment_empty_body_rejected(self, scientist_client):
        c, _db = scientist_client
        resp = await c.post(
            "/api/v1/comments",
            json={
                "analysis_id": str(uuid.uuid4()),
                "body": "",
            },
        )
        assert resp.status_code == 422  # Pydantic min_length=1


# ---------------------------------------------------------------------------
# GET /api/v1/comments
# ---------------------------------------------------------------------------


class TestListComments:
    @pytest.mark.asyncio
    async def test_list_comments(self, scientist_client):
        c, db = scientist_client
        analysis_id = uuid.uuid4()
        comments = [
            make_comment_mock(analysis_id=analysis_id, body="First comment"),
            make_comment_mock(analysis_id=analysis_id, body="Second comment"),
        ]
        # First execute: org isolation check returns the analysis ID
        org_check_result = MagicMock()
        org_check_result.scalar_one_or_none.return_value = analysis_id

        # Second execute: returns the comment list
        comments_result = MagicMock()
        comments_result.scalars.return_value.all.return_value = comments
        assignment_events_result = MagicMock()
        assignment_events_result.scalars.return_value.all.return_value = []
        escalations_result = MagicMock()
        escalations_result.scalars.return_value.all.return_value = []

        db.execute = AsyncMock(
            side_effect=[
                org_check_result,
                comments_result,
                assignment_events_result,
                escalations_result,
            ]
        )

        resp = await c.get(
            "/api/v1/comments",
            params={"analysis_id": str(analysis_id)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["body"] == "First comment"
        assert data[1]["body"] == "Second comment"
        assert data[0]["resolved_by"] is None
        assert data[0]["resolved_at"] is None
        assert data[0]["assigned_reviewer_name"] is None
        assert data[0]["assigned_reviewer_email"] is None
        assert data[0]["assignment_event_count"] == 0
        assert data[0]["last_assignment_at"] is None
        assert data[0]["queue_age_hours"] == 0
        assert data[0]["is_overdue"] is False
        # Verify org isolation, comments, assignment-event, and escalation lookups ran.
        assert db.execute.call_count == 4

    @pytest.mark.asyncio
    async def test_list_comments_empty(self, scientist_client):
        c, db = scientist_client
        org_check_result = MagicMock()
        org_check_result.scalar_one_or_none.return_value = uuid.uuid4()
        comments_result = MagicMock()
        comments_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(side_effect=[org_check_result, comments_result])

        resp = await c.get(
            "/api/v1/comments",
            params={"analysis_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_comments_includes_all_fields(self, scientist_client):
        c, db = scientist_client
        parent_id = uuid.uuid4()
        reviewer = make_user(
            role=UserRole.ATTORNEY,
            email="reviewer@praviar.io",
            full_name="Reviewer User",
        )
        comment = make_comment_mock(
            parent_id=parent_id,
            target_type="patent_claim",
            target_id="US93000001A1",
            resolved=True,
            assigned_to=reviewer.id,
        )
        comment.resolved_by = uuid.uuid4()
        comment.resolved_at = datetime.now(UTC)
        org_check_result = MagicMock()
        org_check_result.scalar_one_or_none.return_value = uuid.uuid4()
        comments_result = MagicMock()
        comments_result.scalars.return_value.all.return_value = [comment]
        reviewer_result = MagicMock()
        reviewer_result.scalars.return_value.all.return_value = [reviewer]
        assignment_events_result = MagicMock()
        assignment_events_result.scalars.return_value.all.return_value = []
        escalations_result = MagicMock()
        escalations_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(
            side_effect=[
                org_check_result,
                comments_result,
                assignment_events_result,
                escalations_result,
                reviewer_result,
            ]
        )

        resp = await c.get(
            "/api/v1/comments",
            params={"analysis_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 200
        item = resp.json()[0]
        assert item["parent_id"] == str(parent_id)
        assert item["target_type"] == "patent_claim"
        assert item["target_id"] == "US93000001A1"
        assert item["resolved"] is True
        assert item["resolved_by"] == str(comment.resolved_by)
        assert item["resolved_at"] == comment.resolved_at.isoformat().replace("+00:00", "Z")
        assert item["assigned_to"] == str(reviewer.id)
        assert item["assigned_by"] is None
        assert item["assigned_at"] is None
        assert item["assigned_reviewer_name"] == "Reviewer User"
        assert item["assigned_reviewer_email"] == "reviewer@praviar.io"
        assert item["assignment_event_count"] == 1
        assert item["last_assignment_at"] == comment.created_at.isoformat().replace("+00:00", "Z")
        assert item["queue_age_hours"] is None
        assert item["is_overdue"] is False

    @pytest.mark.asyncio
    async def test_list_comments_includes_assignment_queue_metadata(self, scientist_client):
        c, db = scientist_client
        reviewer = make_user(
            role=UserRole.ATTORNEY,
            email="reviewer@praviar.io",
            full_name="Reviewer User",
        )
        comment = make_comment_mock(
            resolved=False,
            assigned_to=reviewer.id,
            assigned_by=uuid.uuid4(),
            assigned_at=datetime.now(UTC) - timedelta(hours=79),
            created_at=datetime.now(UTC) - timedelta(hours=80),
        )
        assignment_events = [
            MagicMock(
                comment_id=comment.id,
                analysis_id=comment.analysis_id,
                org_id=uuid.uuid4(),
                assigned_to=reviewer.id,
                assigned_by=uuid.uuid4(),
                event_type="assigned",
                created_at=datetime.now(UTC) - timedelta(hours=79),
            ),
            MagicMock(
                comment_id=comment.id,
                analysis_id=comment.analysis_id,
                org_id=uuid.uuid4(),
                assigned_to=reviewer.id,
                assigned_by=uuid.uuid4(),
                event_type="reassigned",
                created_at=datetime.now(UTC) - timedelta(hours=12),
            ),
        ]
        org_check_result = MagicMock()
        org_check_result.scalar_one_or_none.return_value = uuid.uuid4()
        comments_result = MagicMock()
        comments_result.scalars.return_value.all.return_value = [comment]
        events_result = MagicMock()
        events_result.scalars.return_value.all.return_value = assignment_events
        reviewer_result = MagicMock()
        reviewer_result.scalars.return_value.all.return_value = [reviewer]
        escalations_result = MagicMock()
        escalations_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(
            side_effect=[
                org_check_result,
                comments_result,
                events_result,
                escalations_result,
                reviewer_result,
            ]
        )

        resp = await c.get(
            "/api/v1/comments",
            params={"analysis_id": str(comment.analysis_id)},
        )

        assert resp.status_code == 200
        item = resp.json()[0]
        assert item["assignment_event_count"] == 2
        assert item["last_assignment_at"] == assignment_events[1].created_at.isoformat().replace(
            "+00:00", "Z"
        )
        assert item["queue_age_hours"] >= 80
        assert item["is_overdue"] is True
        assert item["escalation_status"] == "overdue"

    @pytest.mark.asyncio
    async def test_list_comments_sets_watch_escalation_for_aging_unresolved_item(
        self, scientist_client
    ):
        c, db = scientist_client
        comment = make_comment_mock(
            resolved=False,
            assigned_to=uuid.uuid4(),
            created_at=datetime.now(UTC) - timedelta(hours=30),
        )
        org_check_result = MagicMock()
        org_check_result.scalar_one_or_none.return_value = uuid.uuid4()
        comments_result = MagicMock()
        comments_result.scalars.return_value.all.return_value = [comment]
        events_result = MagicMock()
        events_result.scalars.return_value.all.return_value = []
        reviewer_result = MagicMock()
        reviewer_result.scalars.return_value.all.return_value = []
        escalations_result = MagicMock()
        escalations_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(
            side_effect=[
                org_check_result,
                comments_result,
                events_result,
                escalations_result,
                reviewer_result,
            ]
        )

        resp = await c.get(
            "/api/v1/comments",
            params={"analysis_id": str(comment.analysis_id)},
        )

        assert resp.status_code == 200
        item = resp.json()[0]
        assert item["queue_age_hours"] >= 30
        assert item["is_overdue"] is False
        assert item["escalation_status"] == "watch"

    @pytest.mark.asyncio
    async def test_list_comments_includes_thread_escalation_metadata(self, scientist_client):
        c, db = scientist_client
        comment = make_comment_mock(body="Escalated root")
        escalated_by = make_user(
            role=UserRole.ATTORNEY,
            email="counsel@praviar.io",
            full_name="Counsel User",
        )
        org_check_result = MagicMock()
        org_check_result.scalar_one_or_none.return_value = uuid.uuid4()
        comments_result = MagicMock()
        comments_result.scalars.return_value.all.return_value = [comment]
        assignment_events_result = MagicMock()
        assignment_events_result.scalars.return_value.all.return_value = []
        escalations_result = MagicMock()
        escalation = MagicMock()
        escalation.comment_id = comment.id
        escalation.analysis_id = comment.analysis_id
        escalation.org_id = uuid.uuid4()
        escalation.escalated_by = escalated_by.id
        escalation.escalated_at = datetime.now(UTC) - timedelta(minutes=5)
        escalation.escalation_status = "escalated"
        escalation.escalated_to_review = True
        escalation.review_handoff_comment_id = uuid.uuid4()
        escalations_result.scalars.return_value.all.return_value = [escalation]
        users_result = MagicMock()
        users_result.scalars.return_value.all.return_value = [escalated_by]
        reviewers_result = MagicMock()
        reviewers_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(
            side_effect=[
                org_check_result,
                comments_result,
                assignment_events_result,
                escalations_result,
                users_result,
                reviewers_result,
            ]
        )

        resp = await c.get(
            "/api/v1/comments",
            params={"analysis_id": str(comment.analysis_id)},
        )

        assert resp.status_code == 200
        item = resp.json()[0]
        assert item["escalation_status"] == "escalated"
        assert item["escalated_by"] == str(escalated_by.id)
        assert item["escalated_by_name"] == "Counsel User"
        assert item["escalated_by_email"] == "counsel@praviar.io"
        assert item["escalation_event_count"] == 1
        assert item["last_escalation_at"] == escalation.escalated_at.isoformat().replace(
            "+00:00", "Z"
        )
        assert item["escalated_to_review"] is True
        assert item["review_handoff_comment_id"] == str(escalation.review_handoff_comment_id)
        assert item["queue_age_hours"] == 0
        assert item["is_overdue"] is False

    @pytest.mark.asyncio
    async def test_list_comments_ignores_legacy_comment_level_escalation_fields(
        self, scientist_client
    ):
        c, db = scientist_client
        comment = make_comment_mock(body="Legacy escalated root")
        comment.escalated_by = uuid.uuid4()
        comment.escalated_at = datetime.now(UTC) - timedelta(minutes=5)

        org_check_result = MagicMock()
        org_check_result.scalar_one_or_none.return_value = uuid.uuid4()
        comments_result = MagicMock()
        comments_result.scalars.return_value.all.return_value = [comment]
        assignment_events_result = MagicMock()
        assignment_events_result.scalars.return_value.all.return_value = []
        escalations_result = MagicMock()
        escalations_result.scalars.return_value.all.return_value = []

        db.execute = AsyncMock(
            side_effect=[
                org_check_result,
                comments_result,
                assignment_events_result,
                escalations_result,
            ]
        )

        resp = await c.get(
            "/api/v1/comments",
            params={"analysis_id": str(comment.analysis_id)},
        )

        assert resp.status_code == 200
        item = resp.json()[0]
        assert item["escalation_status"] in {"none", "watch", "overdue"}
        assert item["escalated_by"] is None
        assert item["escalated_at"] is None
        assert item["escalation_event_count"] == 0
        assert item["last_escalation_at"] is None
        assert item["review_handoff_comment_id"] is None

    @pytest.mark.asyncio
    async def test_list_comments_filters_by_assignee_and_keeps_thread_replies(
        self, scientist_client
    ):
        c, db = scientist_client
        analysis_id = uuid.uuid4()
        reviewer = make_user(
            role=UserRole.ATTORNEY,
            email="reviewer@praviar.io",
            full_name="Reviewer User",
        )
        other_root = make_comment_mock(analysis_id=analysis_id, body="Other root")
        target_root = make_comment_mock(
            analysis_id=analysis_id,
            body="Target root",
            assigned_to=reviewer.id,
            assigned_by=uuid.uuid4(),
            assigned_at=datetime.now(UTC),
        )
        target_reply = make_comment_mock(
            analysis_id=analysis_id,
            parent_id=target_root.id,
            body="Target reply",
        )
        events_result = MagicMock()
        events_result.scalars.return_value.all.return_value = [
            MagicMock(
                comment_id=target_root.id,
                analysis_id=analysis_id,
                org_id=uuid.uuid4(),
                assigned_to=reviewer.id,
                assigned_by=uuid.uuid4(),
                event_type="assigned",
                created_at=datetime.now(UTC),
            )
        ]
        org_check_result = MagicMock()
        org_check_result.scalar_one_or_none.return_value = analysis_id
        comments_result = MagicMock()
        comments_result.scalars.return_value.all.return_value = [
            other_root,
            target_root,
            target_reply,
        ]
        escalations_result = MagicMock()
        escalations_result.scalars.return_value.all.return_value = []
        reviewer_result = MagicMock()
        reviewer_result.scalars.return_value.all.return_value = [reviewer]
        db.execute = AsyncMock(
            side_effect=[
                org_check_result,
                comments_result,
                events_result,
                escalations_result,
                reviewer_result,
            ]
        )

        resp = await c.get(
            "/api/v1/comments",
            params={
                "analysis_id": str(analysis_id),
                "assigned_to": str(reviewer.id),
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert [item["body"] for item in data] == ["Target root", "Target reply"]
        assert all(item["assigned_to"] == str(reviewer.id) for item in data)

    @pytest.mark.asyncio
    async def test_list_comments_mine_preserves_thread_replies(self):
        current_user = make_user(role=UserRole.ATTORNEY)
        other_user = make_user(role=UserRole.ATTORNEY)
        analysis_id = uuid.uuid4()
        mine_root = make_comment_mock(
            analysis_id=analysis_id,
            body="Mine root",
            assigned_to=current_user.id,
            assigned_by=other_user.id,
            assigned_at=datetime.now(UTC),
        )
        mine_reply = make_comment_mock(
            analysis_id=analysis_id,
            parent_id=mine_root.id,
            body="Mine reply",
        )
        other_root = make_comment_mock(
            analysis_id=analysis_id,
            body="Other root",
            assigned_to=other_user.id,
            assigned_by=current_user.id,
            assigned_at=datetime.now(UTC),
        )
        org_check_result = MagicMock()
        org_check_result.scalar_one_or_none.return_value = analysis_id
        comments_result = MagicMock()
        comments_result.scalars.return_value.all.return_value = [other_root, mine_root, mine_reply]
        events_result = MagicMock()
        events_result.scalars.return_value.all.return_value = []
        reviewer_result = MagicMock()
        reviewer_result.scalars.return_value.all.return_value = [current_user, other_user]
        escalations_result = MagicMock()
        escalations_result.scalars.return_value.all.return_value = []

        async with _make_client_for_user(current_user) as (c, db):
            db.execute = AsyncMock(
                side_effect=[
                    org_check_result,
                    comments_result,
                    events_result,
                    escalations_result,
                    reviewer_result,
                ]
            )
            resp = await c.get(
                "/api/v1/comments",
                params={
                    "analysis_id": str(analysis_id),
                    "assignment_state": "mine",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert [item["body"] for item in data] == ["Mine root", "Mine reply"]
        assert all(item["assigned_to"] == str(current_user.id) for item in data)
        assert data[0]["assignment_event_count"] == 1
        assert data[1]["assignment_event_count"] == 1


# ---------------------------------------------------------------------------
# GET /api/v1/comments/review-queue
# ---------------------------------------------------------------------------


class TestReviewQueue:
    @pytest.mark.asyncio
    async def test_analysis_comment_loader_hides_deleted_analysis_without_silent_cap(self):
        db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        db.execute.return_value = result

        comments = await list_comments_for_analysis(
            db,
            analysis_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
        )

        assert comments == []
        sql = str(db.execute.await_args.args[0])
        assert "analyses.status !=" in sql
        assert "LIMIT" not in sql

    @pytest.mark.asyncio
    async def test_review_queue_row_loader_does_not_truncate_before_counts_or_sorting(self):
        db = AsyncMock()
        result = MagicMock()
        result.tuples.return_value.all.return_value = []
        db.execute.return_value = result
        org_id = uuid.uuid4()

        rows = await list_org_review_queue_rows(db, org_id=org_id)

        assert rows == []
        statement = db.execute.await_args.args[0]
        sql = str(statement)
        assert "analyses.org_id" in sql
        assert "analyses.status !=" in sql
        assert "comments.parent_id IS NULL" in sql
        assert "comments.resolved IS false" in sql
        assert "LIMIT" not in sql
        assert "comments.created_at" in sql
        assert "comments.id" in sql

    @pytest.mark.asyncio
    async def test_review_queue_returns_counts_and_items(self):
        current_user = make_user(
            role=UserRole.ATTORNEY,
            email="queue@praviar.io",
            full_name="Queue User",
        )
        reviewer = make_user(
            role=UserRole.ATTORNEY,
            email="reviewer@praviar.io",
            full_name="Reviewer User",
        )
        assigner = make_user(
            role=UserRole.SCIENTIST,
            email="assigner@praviar.io",
            full_name="Assigner User",
        )
        mine_comment = make_comment_mock(
            body="Mine item",
            resolved=False,
            assigned_to=current_user.id,
            assigned_by=assigner.id,
            assigned_at=datetime.now(UTC) - timedelta(hours=6),
            created_at=datetime.now(UTC) - timedelta(hours=80),
        )
        unassigned_comment = make_comment_mock(
            body="Unassigned item",
            resolved=False,
            created_at=datetime.now(UTC) - timedelta(hours=60),
        )
        escalated_comment = make_comment_mock(
            body="Escalated item",
            resolved=False,
            assigned_to=reviewer.id,
            assigned_by=assigner.id,
            assigned_at=datetime.now(UTC) - timedelta(hours=2),
            created_at=datetime.now(UTC) - timedelta(hours=2),
        )
        mine_analysis = make_analysis_mock(
            id=mine_comment.analysis_id,
            org_id=current_user.org_id,
            compound_name="Mine Compound",
            status="completed",
            overall_risk="high",
        )
        unassigned_analysis = make_analysis_mock(
            id=unassigned_comment.analysis_id,
            org_id=current_user.org_id,
            compound_name="Unassigned Compound",
            status="running",
            overall_risk=None,
        )
        escalated_analysis = make_analysis_mock(
            id=escalated_comment.analysis_id,
            org_id=current_user.org_id,
            compound_name="Escalated Compound",
            status="completed",
            overall_risk="medium",
        )
        queue_result = MagicMock()
        queue_result.tuples.return_value.all.return_value = [
            (mine_comment, mine_analysis),
            (unassigned_comment, unassigned_analysis),
            (escalated_comment, escalated_analysis),
        ]
        assignment_events = [
            MagicMock(
                comment_id=mine_comment.id,
                analysis_id=mine_comment.analysis_id,
                org_id=current_user.org_id,
                assigned_to=current_user.id,
                assigned_by=assigner.id,
                event_type="assigned",
                created_at=datetime.now(UTC) - timedelta(hours=79),
            ),
            MagicMock(
                comment_id=escalated_comment.id,
                analysis_id=escalated_comment.analysis_id,
                org_id=current_user.org_id,
                assigned_to=reviewer.id,
                assigned_by=assigner.id,
                event_type="assigned",
                created_at=datetime.now(UTC) - timedelta(hours=2),
            ),
        ]
        assignment_events_result = MagicMock()
        assignment_events_result.scalars.return_value.all.return_value = assignment_events
        escalations_result = MagicMock()
        escalated_thread = MagicMock()
        escalated_thread.comment_id = escalated_comment.id
        escalated_thread.analysis_id = escalated_comment.analysis_id
        escalated_thread.org_id = current_user.org_id
        escalated_thread.escalated_by = assigner.id
        escalated_thread.escalated_at = datetime.now(UTC) - timedelta(hours=1)
        escalated_thread.escalation_status = "escalated"
        escalated_thread.escalated_to_review = True
        escalated_thread.review_handoff_comment_id = uuid.uuid4()
        escalations_result.scalars.return_value.all.return_value = [escalated_thread]
        users_result = MagicMock()
        users_result.scalars.return_value.all.return_value = [current_user, reviewer, assigner]

        reply_counts_result = MagicMock()
        reply_counts_result.scalars.return_value = []
        async with _make_client_for_user(current_user) as (c, db):
            db.execute = AsyncMock(
                side_effect=[
                    queue_result,
                    assignment_events_result,
                    escalations_result,
                    users_result,
                    reply_counts_result,
                ]
            )

            resp = await c.get("/api/v1/comments/review-queue")

        assert resp.status_code == 200
        data = resp.json()
        assert data["counts"] == {
            "open_total": 3,
            "mine": 1,
            "assigned": 2,
            "unassigned": 1,
            "overdue": 2,
            "escalated": 1,
        }
        assert [item["body"] for item in data["items"]] == [
            "Mine item",
            "Unassigned item",
            "Escalated item",
        ]
        first_item = data["items"][0]
        assert first_item["analysis_id"] == str(mine_analysis.id)
        assert first_item["compound_name"] == "Mine Compound"
        assert first_item["analysis_status"] == "completed"
        assert first_item["overall_risk"] == "high"
        assert first_item["assigned_reviewer_name"] == "Queue User"
        assert first_item["queue_age_hours"] >= 79
        assert first_item["is_overdue"] is True
        assert first_item["escalation_status"] == "overdue"
        third_item = data["items"][2]
        assert third_item["compound_name"] == "Escalated Compound"
        assert third_item["analysis_status"] == "completed"
        assert third_item["escalation_status"] == "escalated"
        assert third_item["escalated_to_review"] is True
        assert third_item["review_handoff_comment_id"] == str(
            escalated_thread.review_handoff_comment_id
        )

    @pytest.mark.asyncio
    async def test_review_queue_applies_requested_filter(self):
        current_user = make_user(
            role=UserRole.ATTORNEY,
            email="queue@praviar.io",
            full_name="Queue User",
        )
        mine_comment = make_comment_mock(
            body="Mine item",
            resolved=False,
            assigned_to=current_user.id,
            created_at=datetime.now(UTC) - timedelta(hours=6),
        )
        unassigned_comment = make_comment_mock(
            body="Unassigned item",
            resolved=False,
            created_at=datetime.now(UTC) - timedelta(hours=5),
        )
        mine_analysis = make_analysis_mock(
            id=mine_comment.analysis_id,
            org_id=current_user.org_id,
            compound_name="Mine Compound",
            status="completed",
            overall_risk="high",
        )
        unassigned_analysis = make_analysis_mock(
            id=unassigned_comment.analysis_id,
            org_id=current_user.org_id,
            compound_name="Unassigned Compound",
            status="running",
            overall_risk=None,
        )
        queue_result = MagicMock()
        queue_result.tuples.return_value.all.return_value = [
            (mine_comment, mine_analysis),
            (unassigned_comment, unassigned_analysis),
        ]
        assignment_events_result = MagicMock()
        assignment_events_result.scalars.return_value.all.return_value = []
        escalations_result = MagicMock()
        escalations_result.scalars.return_value.all.return_value = []
        users_result = MagicMock()
        users_result.scalars.return_value.all.return_value = [current_user]

        reply_counts_result2 = MagicMock()
        reply_counts_result2.scalars.return_value = []
        async with _make_client_for_user(current_user) as (c, db):
            db.execute = AsyncMock(
                side_effect=[
                    queue_result,
                    assignment_events_result,
                    escalations_result,
                    users_result,
                    reply_counts_result2,
                ]
            )

            resp = await c.get("/api/v1/comments/review-queue", params={"filter": "unassigned"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["counts"]["open_total"] == 2
        assert [item["body"] for item in data["items"]] == ["Unassigned item"]

    @pytest.mark.asyncio
    async def test_review_queue_forbidden_for_client(self, client_role_client):
        c, db = client_role_client

        resp = await c.get("/api/v1/comments/review-queue")

        assert resp.status_code == 403
        assert (
            "Only attorneys, admins, or scientists can view the review queue"
            in resp.json()["detail"]
        )
        db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# GET /api/v1/comments/{comment_id}/assignment-history
# ---------------------------------------------------------------------------


class TestCommentAssignmentHistory:
    @pytest.mark.asyncio
    async def test_thread_assignment_history_returns_root_thread_events(self, scientist_client):
        c, db = scientist_client
        root_comment = make_comment_mock(body="Root comment")
        reply_comment = make_comment_mock(parent_id=root_comment.id, body="Reply comment")
        reviewer = make_user(
            role=UserRole.ATTORNEY,
            email="reviewer@praviar.io",
            full_name="Reviewer User",
        )
        assigner = make_user(
            role=UserRole.SCIENTIST,
            email="assigner@praviar.io",
            full_name="Assigner User",
        )
        org_check_result = MagicMock()
        org_check_result.scalar_one_or_none.return_value = root_comment
        comments_result = MagicMock()
        comments_result.scalars.return_value.all.return_value = [root_comment, reply_comment]
        events_result = MagicMock()
        event = MagicMock()
        event.id = uuid.uuid4()
        event.comment_id = root_comment.id
        event.analysis_id = root_comment.analysis_id
        event.event_type = "assigned"
        event.assigned_to = reviewer.id
        event.assigned_by = assigner.id
        event.created_at = datetime.now(UTC)
        events_result.scalars.return_value.all.return_value = [event]
        users_result = MagicMock()
        users_result.scalars.return_value.all.return_value = [reviewer, assigner]
        db.execute = AsyncMock(
            side_effect=[org_check_result, comments_result, events_result, users_result]
        )

        resp = await c.get(f"/api/v1/comments/{reply_comment.id}/assignment-history")

        assert resp.status_code == 200
        data = resp.json()
        assert data["comment_id"] == str(reply_comment.id)
        assert data["thread_root_comment_id"] == str(root_comment.id)
        assert data["assignment_event_count"] == 1
        assert data["last_assignment_at"] == event.created_at.isoformat().replace("+00:00", "Z")
        assert len(data["events"]) == 1
        assert data["events"][0]["event_type"] == "assigned"
        assert data["events"][0]["assigned_to"] == str(reviewer.id)
        assert data["events"][0]["assigned_to_name"] == "Reviewer User"
        assert data["events"][0]["assigned_by"] == str(assigner.id)
        assert data["events"][0]["assigned_by_name"] == "Assigner User"

    @pytest.mark.asyncio
    async def test_thread_assignment_history_backfills_legacy_assigned_threads(
        self, scientist_client
    ):
        c, db = scientist_client
        reviewer = make_user(
            role=UserRole.ATTORNEY,
            email="reviewer@praviar.io",
            full_name="Reviewer User",
        )
        assigner = make_user(
            role=UserRole.SCIENTIST,
            email="assigner@praviar.io",
            full_name="Assigner User",
        )
        root_comment = make_comment_mock(
            body="Legacy root comment",
            assigned_to=reviewer.id,
            assigned_by=assigner.id,
            assigned_at=datetime.now(UTC) - timedelta(hours=4),
        )
        org_check_result = MagicMock()
        org_check_result.scalar_one_or_none.return_value = root_comment
        comments_result = MagicMock()
        comments_result.scalars.return_value.all.return_value = [root_comment]
        events_result = MagicMock()
        events_result.scalars.return_value.all.return_value = []
        users_result = MagicMock()
        users_result.scalars.return_value.all.return_value = [reviewer, assigner]
        db.execute = AsyncMock(
            side_effect=[org_check_result, comments_result, events_result, users_result]
        )

        resp = await c.get(f"/api/v1/comments/{root_comment.id}/assignment-history")

        assert resp.status_code == 200
        data = resp.json()
        assert data["assignment_event_count"] == 1
        assert data["last_assignment_at"] == root_comment.assigned_at.isoformat().replace(
            "+00:00", "Z"
        )
        assert len(data["events"]) == 1
        assert data["events"][0]["event_type"] == "assigned"
        assert data["events"][0]["assigned_to"] == str(reviewer.id)
        assert data["events"][0]["assigned_to_name"] == "Reviewer User"
        assert data["events"][0]["assigned_by"] == str(assigner.id)
        assert data["events"][0]["assigned_by_name"] == "Assigner User"

    @pytest.mark.asyncio
    async def test_thread_assignment_history_forbidden_for_client(self, client_role_client):
        c, db = client_role_client
        resp = await c.get(f"/api/v1/comments/{uuid.uuid4()}/assignment-history")

        assert resp.status_code == 403
        assert (
            "Only attorneys, admins, or scientists can view assignment history"
            in resp.json()["detail"]
        )
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_requires_analysis_id(self, scientist_client):
        c, _db = scientist_client
        resp = await c.get("/api/v1/comments")
        assert resp.status_code == 422  # missing required query param

    @pytest.mark.asyncio
    async def test_list_accessible_to_client(self, client_role_client):
        """Clients CAN read comments (no role restriction on GET)."""
        c, db = client_role_client
        org_check_result = MagicMock()
        org_check_result.scalar_one_or_none.return_value = uuid.uuid4()
        comments_result = MagicMock()
        comments_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(side_effect=[org_check_result, comments_result])

        resp = await c.get(
            "/api/v1/comments",
            params={"analysis_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/v1/comments/{comment_id}/escalation
# ---------------------------------------------------------------------------


class TestEscalateCommentThread:
    @pytest.mark.asyncio
    async def test_escalate_thread_creates_review_handoff_and_persists_thread_state(
        self, scientist_client
    ):
        current_user = make_user(role=UserRole.SCIENTIST, email="scientist@praviar.io")
        comment = make_comment_mock(body="Root comment for escalation")
        analysis = make_analysis_mock(id=comment.analysis_id, org_id=current_user.org_id)

        comment_result = MagicMock()
        comment_result.scalar_one_or_none.return_value = comment
        thread_comments_result = MagicMock()
        thread_comments_result.scalars.return_value.all.return_value = [comment]
        existing_escalation_result = MagicMock()
        existing_escalation_result.scalar_one_or_none.return_value = None
        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = None
        decisions_result = MagicMock()
        decisions_result.scalars.return_value.all.return_value = []
        assignment_events_result = MagicMock()
        assignment_events_result.scalars.return_value.all.return_value = []
        escalated_user_result = MagicMock()
        escalated_user_result.scalars.return_value.all.return_value = [current_user]

        async with _make_client_for_user(current_user) as (c, db):
            db.execute = AsyncMock(
                side_effect=[
                    comment_result,
                    thread_comments_result,
                    existing_escalation_result,
                    analysis_result,
                    review_status_result,
                    decisions_result,
                    assignment_events_result,
                    escalated_user_result,
                ]
            )

            response = await c.post(
                f"/api/v1/comments/{comment.id}/escalation",
                json={
                    "review_note": "Escalate this thread for legal review.",
                    "promote_to_under_review": True,
                },
            )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["id"] == str(comment.id)
        assert data["escalation_status"] == "escalated"
        assert data["escalated_by"] == str(current_user.id)
        assert data["escalated_by_name"] == current_user.full_name
        assert data["escalated_by_email"] == current_user.email
        assert data["escalation_event_count"] == 1
        assert data["last_escalation_at"] is not None
        assert data["escalated_to_review"] is True
        assert data["review_handoff_comment_id"] is not None
        assert data["assignment_event_count"] == 0
        assert data["last_assignment_at"] is None
        assert data["queue_age_hours"] == 0
        assert data["is_overdue"] is False

        added_types = {type(call.args[0]).__name__ for call in db.add.call_args_list}
        assert "CommentThreadEscalation" in added_types
        assert "Comment" in added_types
        assert "AnalysisReviewStatus" in added_types
        assert any(type(call.args[0]).__name__ == "AuditLog" for call in db.add.call_args_list)
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_escalation_rolls_back_when_audit_fails(self, scientist_client):
        current_user = make_user(role=UserRole.SCIENTIST, email="scientist@praviar.io")
        comment = make_comment_mock(body="Root comment for escalation")
        analysis = make_analysis_mock(id=comment.analysis_id, org_id=current_user.org_id)

        comment_result = MagicMock()
        comment_result.scalar_one_or_none.return_value = comment
        thread_comments_result = MagicMock()
        thread_comments_result.scalars.return_value.all.return_value = [comment]
        existing_escalation_result = MagicMock()
        existing_escalation_result.scalar_one_or_none.return_value = None
        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = None
        decisions_result = MagicMock()
        decisions_result.scalars.return_value.all.return_value = []
        assignment_events_result = MagicMock()
        assignment_events_result.scalars.return_value.all.return_value = []
        escalated_user_result = MagicMock()
        escalated_user_result.scalars.return_value.all.return_value = [current_user]

        async with _make_client_for_user(current_user) as (c, db):
            db.execute = AsyncMock(
                side_effect=[
                    comment_result,
                    thread_comments_result,
                    existing_escalation_result,
                    analysis_result,
                    review_status_result,
                    decisions_result,
                    assignment_events_result,
                    escalated_user_result,
                ]
            )
            with (
                patch(
                    "api.routes.comments.write_audit_log",
                    new=AsyncMock(side_effect=RuntimeError("audit unavailable")),
                ) as audit_log,
                pytest.raises(RuntimeError, match="audit unavailable"),
            ):
                await c.post(
                    f"/api/v1/comments/{comment.id}/escalation",
                    json={
                        "review_note": "Escalate this thread for legal review.",
                        "promote_to_under_review": True,
                    },
                )

        assert audit_log.await_args is not None
        assert audit_log.await_args.kwargs["fail_closed"] is True
        db.commit.assert_not_awaited()
        db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_escalate_thread_returns_existing_state_without_creating_duplicate_handoff(
        self, scientist_client
    ):
        current_user = make_user(role=UserRole.SCIENTIST, email="scientist@praviar.io")
        comment = make_comment_mock(body="Already escalated root")
        existing_escalation = MagicMock()
        existing_escalation.comment_id = comment.id
        existing_escalation.analysis_id = comment.analysis_id
        existing_escalation.org_id = current_user.org_id
        existing_escalation.escalated_by = current_user.id
        existing_escalation.escalated_at = datetime.now(UTC) - timedelta(minutes=2)
        existing_escalation.escalation_status = "escalated"
        existing_escalation.escalated_to_review = True
        existing_escalation.review_handoff_comment_id = uuid.uuid4()

        comment_result = MagicMock()
        comment_result.scalar_one_or_none.return_value = comment
        thread_comments_result = MagicMock()
        thread_comments_result.scalars.return_value.all.return_value = [comment]
        existing_escalation_result = MagicMock()
        existing_escalation_result.scalar_one_or_none.return_value = existing_escalation
        escalated_user_result = MagicMock()
        escalated_user_result.scalars.return_value.all.return_value = [current_user]
        assignment_events_result = MagicMock()
        assignment_events_result.scalars.return_value.all.return_value = []

        async with _make_client_for_user(current_user) as (c, db):
            db.execute = AsyncMock(
                side_effect=[
                    comment_result,
                    thread_comments_result,
                    existing_escalation_result,
                    escalated_user_result,
                    assignment_events_result,
                ]
            )

            response = await c.post(
                f"/api/v1/comments/{comment.id}/escalation",
                json={"review_note": "Escalate again."},
            )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["id"] == str(comment.id)
        assert data["escalation_status"] == "escalated"
        assert data["escalation_event_count"] == 1
        assert data["escalated_to_review"] is True
        assert data["review_handoff_comment_id"] == str(
            existing_escalation.review_handoff_comment_id
        )
        db.add.assert_not_called()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_escalate_reply_targets_root_thread_and_returns_root_comment(
        self, scientist_client
    ):
        current_user = make_user(role=UserRole.SCIENTIST, email="scientist@praviar.io")
        root_comment = make_comment_mock(body="Root thread comment")
        reply_comment = make_comment_mock(
            analysis_id=root_comment.analysis_id,
            parent_id=root_comment.id,
            body="Reply that triggered escalation",
        )
        analysis = make_analysis_mock(id=root_comment.analysis_id, org_id=current_user.org_id)

        comment_result = MagicMock()
        comment_result.scalar_one_or_none.return_value = reply_comment
        thread_comments_result = MagicMock()
        thread_comments_result.scalars.return_value.all.return_value = [
            root_comment,
            reply_comment,
        ]
        existing_escalation_result = MagicMock()
        existing_escalation_result.scalar_one_or_none.return_value = None
        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = None
        decisions_result = MagicMock()
        decisions_result.scalars.return_value.all.return_value = []
        assignment_events_result = MagicMock()
        assignment_events_result.scalars.return_value.all.return_value = []
        escalated_user_result = MagicMock()
        escalated_user_result.scalars.return_value.all.return_value = [current_user]

        async with _make_client_for_user(current_user) as (c, db):
            db.execute = AsyncMock(
                side_effect=[
                    comment_result,
                    thread_comments_result,
                    existing_escalation_result,
                    analysis_result,
                    review_status_result,
                    decisions_result,
                    assignment_events_result,
                    escalated_user_result,
                ]
            )

            response = await c.post(
                f"/api/v1/comments/{reply_comment.id}/escalation",
                json={
                    "review_note": "Escalate from reply context.",
                    "promote_to_under_review": True,
                },
            )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["id"] == str(root_comment.id)
        assert data["body"] == root_comment.body
        assert data["parent_id"] is None
        assert data["review_handoff_comment_id"] is not None

    @pytest.mark.asyncio
    async def test_escalate_thread_forbidden_for_client(self, client_role_client):
        c, db = client_role_client
        resp = await c.post(
            f"/api/v1/comments/{uuid.uuid4()}/escalation",
            json={"review_note": "Client escalation attempt."},
        )

        assert resp.status_code == 403
        assert (
            "Only attorneys, admins, or scientists can escalate comments" in resp.json()["detail"]
        )
        db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# GET /api/v1/comments/reviewers
# ---------------------------------------------------------------------------


class TestListCommentReviewers:
    @pytest.mark.asyncio
    async def test_list_comment_reviewers_as_attorney(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        reviewers = [
            make_user(role=UserRole.ADMIN, email="admin@praviar.io", full_name="Admin User"),
            make_user(
                role=UserRole.ATTORNEY,
                email="attorney@praviar.io",
                full_name="Attorney User",
            ),
        ]
        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis_id
        result = MagicMock()
        result.scalars.return_value.all.return_value = reviewers
        db.execute = AsyncMock(side_effect=[analysis_result, result])

        resp = await c.get("/api/v1/comments/reviewers", params={"analysis_id": str(analysis_id)})

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert {item["role"] for item in data} == {"admin", "attorney"}
        assert {item["email"] for item in data} == {
            "admin@praviar.io",
            "attorney@praviar.io",
        }
        assert db.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_list_comment_reviewers_as_scientist(self, scientist_client):
        c, db = scientist_client
        analysis_id = uuid.uuid4()
        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis_id
        reviewers_result = MagicMock()
        reviewers_result.scalars.return_value.all.return_value = [
            make_user(
                role=UserRole.ATTORNEY,
                email="attorney@praviar.io",
                full_name="Attorney User",
            )
        ]
        db.execute = AsyncMock(side_effect=[analysis_result, reviewers_result])

        resp = await c.get("/api/v1/comments/reviewers", params={"analysis_id": str(analysis_id)})

        assert resp.status_code == 200
        assert resp.json()[0]["email"] == "attorney@praviar.io"
        assert db.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_list_comment_reviewers_forbidden_for_client(self, client_role_client):
        c, db = client_role_client

        resp = await c.get("/api/v1/comments/reviewers", params={"analysis_id": str(uuid.uuid4())})

        assert resp.status_code == 403
        assert "Only attorneys, admins, or scientists can view reviewers" in resp.json()["detail"]
        db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# PATCH /api/v1/comments/{comment_id}/resolution
# ---------------------------------------------------------------------------


class TestUpdateCommentResolution:
    @pytest.mark.asyncio
    async def test_resolve_comment_as_attorney(self, attorney_client):
        c, db = attorney_client
        comment = make_comment_mock(resolved=False)
        resolve_result = MagicMock()
        resolve_result.scalar_one_or_none.return_value = comment
        thread_comment_result = MagicMock()
        thread_comment_result.scalar_one_or_none.return_value = comment
        thread_comments_result = MagicMock()
        thread_comments_result.scalars.return_value.all.return_value = [comment]
        assignment_events_result = MagicMock()
        assignment_events_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(
            side_effect=[
                resolve_result,
                thread_comment_result,
                thread_comments_result,
                assignment_events_result,
            ]
        )
        comment_id = comment.id

        resp = await c.patch(
            f"/api/v1/comments/{comment_id}/resolution",
            json={"resolved": True},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(comment_id)
        assert data["resolved"] is True
        assert data["resolved_by"] is not None
        assert data["resolved_at"] is not None
        assert comment.resolved is True
        assert comment.resolved_by is not None
        assert comment.resolved_at is not None
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_resolution_rolls_back_when_audit_fails(self, attorney_client):
        c, db = attorney_client
        comment = make_comment_mock(resolved=False)
        resolve_result = MagicMock()
        resolve_result.scalar_one_or_none.return_value = comment
        db.execute = AsyncMock(return_value=resolve_result)

        with (
            patch(
                "api.routes.comments.write_audit_log",
                new=AsyncMock(side_effect=RuntimeError("audit unavailable")),
            ) as audit_log,
            pytest.raises(RuntimeError, match="audit unavailable"),
        ):
            await c.patch(
                f"/api/v1/comments/{comment.id}/resolution",
                json={"resolved": True},
            )

        assert audit_log.await_args is not None
        assert audit_log.await_args.kwargs["fail_closed"] is True
        db.commit.assert_not_awaited()
        db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_resolve_comment_as_admin(self, admin_client):
        c, db = admin_client
        comment = make_comment_mock(resolved=False)
        resolve_result = MagicMock()
        resolve_result.scalar_one_or_none.return_value = comment
        thread_comment_result = MagicMock()
        thread_comment_result.scalar_one_or_none.return_value = comment
        thread_comments_result = MagicMock()
        thread_comments_result.scalars.return_value.all.return_value = [comment]
        assignment_events_result = MagicMock()
        assignment_events_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(
            side_effect=[
                resolve_result,
                thread_comment_result,
                thread_comments_result,
                assignment_events_result,
            ]
        )

        resp = await c.patch(
            f"/api/v1/comments/{comment.id}/resolution",
            json={"resolved": True},
        )

        assert resp.status_code == 200
        assert resp.json()["resolved"] is True
        assert comment.resolved is True
        assert comment.resolved_by is not None
        assert comment.resolved_at is not None
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unresolve_comment_clears_resolver(self, attorney_client):
        c, db = attorney_client
        comment = make_comment_mock(resolved=True)
        comment.resolved_by = uuid.uuid4()
        comment.resolved_at = datetime.now(UTC)
        resolve_result = MagicMock()
        resolve_result.scalar_one_or_none.return_value = comment
        thread_comment_result = MagicMock()
        thread_comment_result.scalar_one_or_none.return_value = comment
        thread_comments_result = MagicMock()
        thread_comments_result.scalars.return_value.all.return_value = [comment]
        assignment_events_result = MagicMock()
        assignment_events_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(
            side_effect=[
                resolve_result,
                thread_comment_result,
                thread_comments_result,
                assignment_events_result,
            ]
        )

        resp = await c.patch(
            f"/api/v1/comments/{comment.id}/resolution",
            json={"resolved": False},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["resolved"] is False
        assert data["resolved_by"] is None
        assert data["resolved_at"] is None
        assert comment.resolved is False
        assert comment.resolved_by is None
        assert comment.resolved_at is None
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_resolution_response_preserves_thread_assignment_metadata(self, attorney_client):
        c, db = attorney_client
        reviewer = make_user(
            role=UserRole.ATTORNEY,
            email="reviewer@praviar.io",
            full_name="Reviewer User",
        )
        comment = make_comment_mock(
            resolved=False,
            assigned_to=reviewer.id,
            assigned_at=datetime.now(UTC) - timedelta(hours=3),
        )
        resolve_result = MagicMock()
        resolve_result.scalar_one_or_none.return_value = comment
        thread_comment_result = MagicMock()
        thread_comment_result.scalar_one_or_none.return_value = comment
        thread_comments_result = MagicMock()
        thread_comments_result.scalars.return_value.all.return_value = [comment]
        assignment_events_result = MagicMock()
        assignment_event = MagicMock()
        assignment_event.comment_id = comment.id
        assignment_event.analysis_id = comment.analysis_id
        assignment_event.org_id = uuid.uuid4()
        assignment_event.assigned_to = reviewer.id
        assignment_event.assigned_by = None
        assignment_event.event_type = "assigned"
        assignment_event.created_at = datetime.now(UTC) - timedelta(hours=2)
        assignment_events_result.scalars.return_value.all.return_value = [assignment_event]
        reviewers_result = MagicMock()
        reviewers_result.scalars.return_value.all.return_value = [reviewer]
        db.execute = AsyncMock(
            side_effect=[
                resolve_result,
                thread_comment_result,
                thread_comments_result,
                assignment_events_result,
                reviewers_result,
            ]
        )

        resp = await c.patch(
            f"/api/v1/comments/{comment.id}/resolution",
            json={"resolved": True},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["resolved"] is True
        assert data["assigned_to"] == str(reviewer.id)
        assert data["assigned_reviewer_name"] == "Reviewer User"
        assert data["assignment_event_count"] == 1
        assert data["last_assignment_at"] == assignment_event.created_at.isoformat().replace(
            "+00:00", "Z"
        )
        assert data["queue_age_hours"] is None
        assert data["is_overdue"] is False
        assert data["escalation_status"] == "none"

    @pytest.mark.asyncio
    async def test_resolve_comment_forbidden_for_scientist(self, scientist_client):
        c, db = scientist_client
        comment_id = uuid.uuid4()

        resp = await c.patch(
            f"/api/v1/comments/{comment_id}/resolution",
            json={"resolved": True},
        )

        assert resp.status_code == 403
        assert "Only attorneys or admins can resolve comments" in resp.json()["detail"]
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_comment_cross_org_rejected(self, attorney_client):
        c, db = attorney_client
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result)

        resp = await c.patch(
            f"/api/v1/comments/{uuid.uuid4()}/resolution",
            json={"resolved": True},
        )

        assert resp.status_code == 404
        assert "Comment not found" in resp.json()["detail"]
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolution_requires_boolean(self, attorney_client):
        c, _db = attorney_client
        resp = await c.patch(
            f"/api/v1/comments/{uuid.uuid4()}/resolution",
            json={},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /api/v1/comments/{comment_id}/assignment
# ---------------------------------------------------------------------------


class TestUpdateCommentAssignment:
    @pytest.mark.asyncio
    async def test_assign_comment_as_scientist_notifies_reviewer(self, scientist_client):
        c, db = scientist_client
        comment = make_comment_mock(assigned_to=None, assigned_by=None, assigned_at=None)
        reviewer = make_user(
            role=UserRole.ATTORNEY,
            email="reviewer@praviar.io",
            full_name="Reviewer User",
        )

        comment_result = MagicMock()
        comment_result.scalar_one_or_none.return_value = comment
        reviewer_result = MagicMock()
        reviewer_result.scalar_one_or_none.return_value = reviewer
        events_result = MagicMock()
        assignment_event = MagicMock()
        assignment_event.created_at = datetime.now(UTC)
        events_result.scalars.return_value.all.return_value = [assignment_event]
        db.execute = AsyncMock(side_effect=[comment_result, reviewer_result, events_result])

        resp = await c.patch(
            f"/api/v1/comments/{comment.id}/assignment",
            json={"assigned_to": str(reviewer.id)},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["assigned_to"] == str(reviewer.id)
        assert data["assigned_by"] is not None
        assert data["assigned_at"] is not None
        assert data["assignment_event_count"] == 1
        assert data["last_assignment_at"] is not None
        assert data["queue_age_hours"] == 0
        assert data["is_overdue"] is False
        assert comment.assigned_to == reviewer.id
        assert comment.assigned_by is not None
        assert comment.assigned_at is not None

        notifications = [
            call.args[0] for call in db.add.call_args_list if isinstance(call.args[0], Notification)
        ]
        assert len(notifications) == 1
        assignment_events = [
            call.args[0]
            for call in db.add.call_args_list
            if isinstance(call.args[0], CommentAssignmentEvent)
        ]
        assert len(assignment_events) == 1
        assert assignment_events[0].event_type == "assigned"
        assert assignment_events[0].comment_id == comment.id
        assert assignment_events[0].analysis_id == comment.analysis_id
        assert assignment_events[0].assigned_to == reviewer.id
        notification = notifications[0]
        assert notification.user_id == reviewer.id
        assert notification.type == NotificationType.SYSTEM
        assert notification.title == "Comment assigned for review"
        assert notification.data["comment_id"] == str(comment.id)
        assert notification.data["assigned_to"] == str(reviewer.id)
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_assignment_rolls_back_when_audit_fails(self, scientist_client):
        c, db = scientist_client
        comment = make_comment_mock(assigned_to=None, assigned_by=None, assigned_at=None)
        reviewer = make_user(
            role=UserRole.ATTORNEY,
            email="reviewer@praviar.io",
            full_name="Reviewer User",
        )

        comment_result = MagicMock()
        comment_result.scalar_one_or_none.return_value = comment
        reviewer_result = MagicMock()
        reviewer_result.scalar_one_or_none.return_value = reviewer
        db.execute = AsyncMock(side_effect=[comment_result, reviewer_result])

        with (
            patch(
                "api.routes.comments.write_audit_log",
                new=AsyncMock(side_effect=RuntimeError("audit unavailable")),
            ) as audit_log,
            pytest.raises(RuntimeError, match="audit unavailable"),
        ):
            await c.patch(
                f"/api/v1/comments/{comment.id}/assignment",
                json={"assigned_to": str(reviewer.id)},
            )

        assert audit_log.await_args is not None
        assert audit_log.await_args.kwargs["fail_closed"] is True
        db.commit.assert_not_awaited()
        db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_assign_comment_rejects_reply_comment(self, scientist_client):
        c, db = scientist_client
        comment = make_comment_mock(parent_id=uuid.uuid4())
        comment_result = MagicMock()
        comment_result.scalar_one_or_none.return_value = comment
        db.execute = AsyncMock(return_value=comment_result)

        resp = await c.patch(
            f"/api/v1/comments/{comment.id}/assignment",
            json={"assigned_to": str(uuid.uuid4())},
        )

        assert resp.status_code == 400
        assert "Only top-level comments can be assigned" in resp.json()["detail"]
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_unassign_comment_clears_assignment(self, attorney_client):
        c, db = attorney_client
        comment = make_comment_mock(
            assigned_to=uuid.uuid4(),
            assigned_by=uuid.uuid4(),
            assigned_at=datetime.now(UTC),
        )
        result = MagicMock()
        result.scalar_one_or_none.return_value = comment
        events_result = MagicMock()
        assignment_event = MagicMock()
        assignment_event.created_at = datetime.now(UTC)
        events_result.scalars.return_value.all.return_value = [assignment_event]
        db.execute = AsyncMock(side_effect=[result, events_result])

        resp = await c.patch(
            f"/api/v1/comments/{comment.id}/assignment",
            json={"assigned_to": None},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["assigned_to"] is None
        assert data["assigned_by"] is None
        assert data["assigned_at"] is None
        assert data["assignment_event_count"] == 1
        assert data["last_assignment_at"] is not None
        assert data["queue_age_hours"] == 0
        assert data["is_overdue"] is False
        assert comment.assigned_to is None
        assert comment.assigned_by is None
        assert comment.assigned_at is None
        assignment_events = [
            call.args[0]
            for call in db.add.call_args_list
            if isinstance(call.args[0], CommentAssignmentEvent)
        ]
        assert len(assignment_events) == 1
        assert assignment_events[0].event_type == "unassigned"
        assert assignment_events[0].comment_id == comment.id
        assert assignment_events[0].analysis_id == comment.analysis_id
        assert not any(isinstance(call.args[0], Notification) for call in db.add.call_args_list)
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_assignment_rejects_non_reviewer_target(self, scientist_client):
        c, db = scientist_client
        comment = make_comment_mock(assigned_to=None)
        scientist_reviewer = make_user(role=UserRole.SCIENTIST, email="scientist@praviar.io")

        comment_result = MagicMock()
        comment_result.scalar_one_or_none.return_value = comment
        reviewer_result = MagicMock()
        reviewer_result.scalar_one_or_none.return_value = scientist_reviewer
        db.execute = AsyncMock(side_effect=[comment_result, reviewer_result])

        resp = await c.patch(
            f"/api/v1/comments/{comment.id}/assignment",
            json={"assigned_to": str(scientist_reviewer.id)},
        )

        assert resp.status_code == 403
        assert "attorneys or admins" in resp.json()["detail"]
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_assignment_forbidden_for_client(self, client_role_client):
        c, db = client_role_client
        resp = await c.patch(
            f"/api/v1/comments/{uuid.uuid4()}/assignment",
            json={"assigned_to": None},
        )

        assert resp.status_code == 403
        assert "Only attorneys, admins, or scientists can assign comments" in resp.json()["detail"]
        db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Service-layer unit tests for ``api.services.comments``
# ---------------------------------------------------------------------------


class TestCommentsService:
    def test_coerce_uuid_returns_value_when_uuid(self):
        from api.services.comments import coerce_uuid

        u = uuid.uuid4()
        assert coerce_uuid(u) is u
        assert coerce_uuid("not-a-uuid") is None
        assert coerce_uuid(None) is None

    def test_derive_assignment_event_type(self):
        from api.services.comments import derive_assignment_event_type

        assert derive_assignment_event_type(reviewer=None, current_assigned_to=None) == "unassigned"
        assert (
            derive_assignment_event_type(reviewer=MagicMock(), current_assigned_to=None)
            == "assigned"
        )
        assert (
            derive_assignment_event_type(reviewer=MagicMock(), current_assigned_to=uuid.uuid4())
            == "reassigned"
        )

    def test_is_explicitly_escalated_detects_escalation_signals(self):
        from api.services.comments import is_explicitly_escalated

        assert is_explicitly_escalated({"escalation_status": "escalated"}) is True
        assert is_explicitly_escalated({"escalated_to_review": True}) is True
        assert is_explicitly_escalated({"review_handoff_comment_id": uuid.uuid4()}) is True
        assert is_explicitly_escalated({"escalation_event_count": 1}) is True
        assert (
            is_explicitly_escalated(
                {
                    "escalation_status": "watch",
                    "escalated_to_review": False,
                    "review_handoff_comment_id": None,
                    "escalation_event_count": 0,
                }
            )
            is False
        )

    def test_build_resolution_audit_details_includes_user_when_resolved(self):
        from api.services.comments import build_resolution_audit_details

        comment = MagicMock()
        comment.id = uuid.uuid4()
        comment.resolved_at = None
        comment.target_type = "analysis"
        comment.target_id = ""
        user_id = uuid.uuid4()

        details = build_resolution_audit_details(comment, body_resolved=True, user_id=user_id)
        assert details["resolved"] is True
        assert details["resolved_by"] == str(user_id)
        assert details["target_type"] == "analysis"

        details_unresolved = build_resolution_audit_details(
            comment, body_resolved=False, user_id=user_id
        )
        assert details_unresolved["resolved_by"] is None

    @pytest.mark.asyncio
    async def test_assert_analysis_in_org_404_when_missing(self):
        from api.errors import APIError
        from api.services.comments import assert_analysis_in_org

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(APIError) as exc:
            await assert_analysis_in_org(db, analysis_id=uuid.uuid4(), org_id=uuid.uuid4())
        assert exc.value.status == 404

    @pytest.mark.asyncio
    async def test_list_comments_for_analysis_scopes_by_org(self):
        from api.services.comments import list_comments_for_analysis

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)

        await list_comments_for_analysis(
            db,
            analysis_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
        )

        statement = db.execute.await_args.args[0]
        rendered = str(statement)
        assert "JOIN analyses" in rendered
        assert "analyses.org_id" in rendered

    def test_apply_resolution_change_sets_fields_when_resolved(self):
        from api.services.comments import apply_resolution_change

        comment = MagicMock()
        comment.resolved_at = None
        user_id = uuid.uuid4()
        apply_resolution_change(comment, resolved=True, user_id=user_id)

        assert comment.resolved is True
        assert comment.resolved_by == user_id
        assert comment.resolved_at is not None

    def test_apply_resolution_change_clears_fields_when_unresolved(self):
        from api.services.comments import apply_resolution_change

        comment = MagicMock()
        apply_resolution_change(comment, resolved=False, user_id=uuid.uuid4())

        assert comment.resolved is False
        assert comment.resolved_by is None
        assert comment.resolved_at is None
