"""Tests for /api/v1/analyses/{analysis_id}/decisions endpoints.

Covers the reviewer accept / reject / edit workflow (WS-3). The endpoints
record per-finding decisions authored by an identified reviewer, scoped to
the caller's org.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import make_analysis_mock, make_user, valid_report_data_for_patents

from api.db.models import (
    AnalysisReviewerDecision,
    AnalysisReviewStatus,
    AnalysisStatus,
    ReviewStatus,
    UserRole,
)
from api.services.report_access import report_payload_fingerprint


def _make_decision_mock(**kw) -> MagicMock:
    """Create a mock ``AnalysisReviewerDecision`` ORM object."""
    d = MagicMock(spec=AnalysisReviewerDecision)
    d.id = kw.get("id", uuid.uuid4())
    d.analysis_id = kw.get("analysis_id", uuid.uuid4())
    d.org_id = kw.get("org_id", uuid.uuid4())
    d.finding_type = kw.get("finding_type", "patent")
    d.finding_ref = kw.get("finding_ref", "US12345B2")
    d.report_fingerprint = kw.get("report_fingerprint", "")
    d.decision = kw.get("decision", "accept")
    d.note = kw.get("note", "")
    d.edited_text = kw.get("edited_text", "")
    d.reviewer_user_id = kw.get("reviewer_user_id", "clerk_test_user")
    d.reviewer_name = kw.get("reviewer_name", "Test User")
    d.reviewer_email = kw.get("reviewer_email", "test@praviar.io")
    d.created_at = kw.get("created_at", datetime.now(UTC))
    d.updated_at = kw.get("updated_at", datetime.now(UTC))
    return d


def _make_review_status_mock(**kw) -> MagicMock:
    """Create a mock ``AnalysisReviewStatus`` ORM object."""
    row = MagicMock(spec=AnalysisReviewStatus)
    row.analysis_id = kw.get("analysis_id", uuid.uuid4())
    row.org_id = kw.get("org_id", uuid.uuid4())
    row.status = kw.get("status", ReviewStatus.UNDER_REVIEW)
    row.note = kw.get("note", "Review in progress.")
    row.reviewer_user_id = kw.get("reviewer_user_id", "clerk_test_user")
    row.reviewer_name = kw.get("reviewer_name", "Test User")
    row.reviewer_email = kw.get("reviewer_email", "test@praviar.io")
    row.reviewed_at = kw.get("reviewed_at", datetime.now(UTC))
    row.updated_at = kw.get("updated_at", datetime.now(UTC))
    return row


def _reviewable_report_data() -> dict:
    report_data = valid_report_data_for_patents([{"patent_id": "US12345B2", "risk_level": "high"}])
    report_data["claim_source_span_map"]["entries"].append(
        {
            "assertion_id": "US93000002A1-claim-1-elem-a",
            "patent_id": "US12345B2",
            "claim_number": 1,
            "element_number": 2,
            "report_section": "claim_element_analysis",
            "assertion_text": "Claim 1 element 2 needs reviewer decision.",
            "source_span_ids": [],
            "support_status": "needs_review",
            "customer_visible": True,
            "review_required": True,
        }
    )
    report_data["claim_source_span_map"]["needs_review_count"] = 1
    return report_data


def _passing_org_check(db) -> None:
    """Configure db so the org-scoped analysis lookup succeeds and no existing decision."""
    analysis_check = MagicMock()
    analysis_check.scalar_one_or_none.return_value = make_analysis_mock(
        report_data=_reviewable_report_data()
    )

    existing_check = MagicMock()
    existing_check.scalar_one_or_none.return_value = None

    analysis_for_review = MagicMock()
    analysis_for_review.scalar_one_or_none.return_value = make_analysis_mock(
        report_data=_reviewable_report_data()
    )

    review_status_check = MagicMock()
    review_status_check.scalar_one_or_none.return_value = None

    db.execute = AsyncMock(
        side_effect=[analysis_check, existing_check, analysis_for_review, review_status_check]
    )


# ---------------------------------------------------------------------------
# POST /api/v1/analyses/{id}/decisions — create
# ---------------------------------------------------------------------------


class TestCreateDecision:
    @pytest.mark.asyncio
    async def test_accept_creates_decision(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        _passing_org_check(db)

        resp = await c.post(
            f"/api/v1/analyses/{analysis_id}/decisions",
            json={
                "finding_type": "patent",
                "finding_ref": "US12345B2",
                "decision": "accept",
                "note": "Attorney confirms blocking.",
            },
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["decision"] == "accept"
        assert data["finding_type"] == "patent"
        assert data["finding_ref"] == "US12345B2"
        assert data["note"] == "Attorney confirms blocking."
        # One add for the decision itself; route also adds an AuditLog row,
        # so call_count >= 1 (exactly 2 in v1 with audit wired up).
        assert db.add.call_count >= 1
        added_types = {type(call.args[0]).__name__ for call in db.add.call_args_list}
        assert "AnalysisReviewerDecision" in added_types
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_edit_requires_edited_text(self, attorney_client):
        """decision=edit with empty edited_text is a 422."""
        c, db = attorney_client
        _passing_org_check(db)

        resp = await c.post(
            f"/api/v1/analyses/{uuid.uuid4()}/decisions",
            json={
                "finding_type": "claim_element",
                "finding_ref": "US93000002A1-claim-1-elem-a",
                "decision": "edit",
                "edited_text": "",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_edit_with_text_creates_decision(self, attorney_client):
        c, db = attorney_client
        _passing_org_check(db)

        resp = await c.post(
            f"/api/v1/analyses/{uuid.uuid4()}/decisions",
            json={
                "finding_type": "claim_element",
                "finding_ref": "US93000002A1-claim-1-elem-a",
                "decision": "edit",
                "edited_text": "Revised element mapping: explicitly discloses R1=H.",
                "note": "The cited claim text requires this corrected mapping.",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["edited_text"].startswith("Revised element mapping")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("decision", ["reject", "edit"])
    async def test_reject_and_edit_require_rationale(self, attorney_client, decision):
        c, db = attorney_client
        _passing_org_check(db)

        resp = await c.post(
            f"/api/v1/analyses/{uuid.uuid4()}/decisions",
            json={
                "finding_type": "claim_element",
                "finding_ref": "US93000002A1-claim-1-elem-a",
                "decision": decision,
                "edited_text": "Corrected finding." if decision == "edit" else "",
                "note": "   ",
            },
        )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_high_risk_accept_requires_rationale(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        analysis_check = MagicMock()
        analysis_check.scalar_one_or_none.return_value = make_analysis_mock(
            id=analysis_id,
            report_data=_reviewable_report_data(),
        )
        db.execute = AsyncMock(return_value=analysis_check)

        resp = await c.post(
            f"/api/v1/analyses/{analysis_id}/decisions",
            json={
                "finding_type": "patent",
                "finding_ref": "US12345B2",
                "decision": "accept",
                "note": "",
            },
        )

        assert resp.status_code == 422
        assert "rationale note" in resp.json()["detail"]
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_rejects_unknown_current_report_finding_ref(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        analysis_check = MagicMock()
        analysis_check.scalar_one_or_none.return_value = make_analysis_mock(
            id=analysis_id,
            report_data=_reviewable_report_data(),
        )
        db.execute = AsyncMock(return_value=analysis_check)

        resp = await c.post(
            f"/api/v1/analyses/{analysis_id}/decisions",
            json={
                "finding_type": "patent",
                "finding_ref": "US91000006A1",
                "decision": "accept",
            },
        )

        assert resp.status_code == 422, resp.text
        assert "current report findings" in resp.json()["detail"]
        db.add.assert_not_called()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_rejects_stale_claim_element_ref(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        analysis_check = MagicMock()
        analysis_check.scalar_one_or_none.return_value = make_analysis_mock(
            id=analysis_id,
            report_data=_reviewable_report_data(),
        )
        db.execute = AsyncMock(return_value=analysis_check)

        resp = await c.post(
            f"/api/v1/analyses/{analysis_id}/decisions",
            json={
                "finding_type": "claim_element",
                "finding_ref": "old-claim-element-ref",
                "decision": "accept",
            },
        )

        assert resp.status_code == 422, resp.text
        assert "current report findings" in resp.json()["detail"]
        db.add.assert_not_called()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_rejects_unpublishable_report_payload(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        analysis_check = MagicMock()
        analysis_check.scalar_one_or_none.return_value = make_analysis_mock(
            id=analysis_id,
            report_data={},
        )
        db.execute = AsyncMock(return_value=analysis_check)

        resp = await c.post(
            f"/api/v1/analyses/{analysis_id}/decisions",
            json={
                "finding_type": "patent",
                "finding_ref": "US12345B2",
                "decision": "accept",
            },
        )

        assert resp.status_code == 409, resp.text
        assert "completed publishable report payload" in resp.json()["detail"]
        db.add.assert_not_called()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_upsert_replaces_existing(self, attorney_client):
        """POST twice on the same (analysis, type, ref) from same reviewer upserts."""
        c, db = attorney_client
        analysis_id = uuid.uuid4()

        # Analysis belongs to this org
        analysis_check = MagicMock()
        analysis_check.scalar_one_or_none.return_value = make_analysis_mock(
            id=analysis_id,
            report_data=_reviewable_report_data(),
        )

        # Existing decision found for (analysis, type, ref, reviewer)
        existing = _make_decision_mock(
            analysis_id=analysis_id,
            finding_type="patent",
            finding_ref="US12345B2",
            decision="accept",
            note="original",
            reviewer_user_id="clerk_test_user",
        )
        existing_check = MagicMock()
        existing_check.scalar_one_or_none.return_value = existing

        analysis_for_review = MagicMock()
        analysis_for_review.scalar_one_or_none.return_value = make_analysis_mock(
            id=analysis_id,
            report_data=_reviewable_report_data(),
        )
        review_status_check = MagicMock()
        review_status_check.scalar_one_or_none.return_value = None

        db.execute = AsyncMock(
            side_effect=[
                analysis_check,
                existing_check,
                analysis_for_review,
                review_status_check,
            ]
        )

        resp = await c.post(
            f"/api/v1/analyses/{analysis_id}/decisions",
            json={
                "finding_type": "patent",
                "finding_ref": "US12345B2",
                "decision": "reject",
                "note": "updated — not actually blocking",
            },
        )
        assert resp.status_code == 201
        # The existing row was mutated; no new decision row was added
        # (the only db.add is the AuditLog for the upsert event).
        assert existing.decision == "reject"
        assert existing.note == "updated — not actually blocking"
        added_types = [type(call.args[0]).__name__ for call in db.add.call_args_list]
        assert "AnalysisReviewerDecision" not in added_types
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_upsert_after_approval_invalidates_approved_status(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()

        analysis_check = MagicMock()
        analysis_check.scalar_one_or_none.return_value = make_analysis_mock(
            id=analysis_id,
            report_data=_reviewable_report_data(),
        )

        existing = _make_decision_mock(
            analysis_id=analysis_id,
            finding_type="patent",
            finding_ref="US12345B2",
            decision="accept",
            reviewer_user_id="clerk_test_user",
        )
        existing_check = MagicMock()
        existing_check.scalar_one_or_none.return_value = existing

        analysis = make_analysis_mock(
            id=analysis_id,
            flagged_for_review=False,
            report_data=_reviewable_report_data(),
        )
        analysis_for_review = MagicMock()
        analysis_for_review.scalar_one_or_none.return_value = analysis

        approved_status = _make_review_status_mock(
            analysis_id=analysis_id,
            status=ReviewStatus.APPROVED,
            note="Ready for export.",
        )
        review_status_check = MagicMock()
        review_status_check.scalar_one_or_none.return_value = approved_status

        db.execute = AsyncMock(
            side_effect=[
                analysis_check,
                existing_check,
                analysis_for_review,
                review_status_check,
            ]
        )

        with patch(
            "api.routes.reviewer_decisions.write_audit_log",
            new=AsyncMock(),
        ) as audit_log:
            resp = await c.post(
                f"/api/v1/analyses/{analysis_id}/decisions",
                json={
                    "finding_type": "patent",
                    "finding_ref": "US12345B2",
                    "decision": "reject",
                    "note": "Updated after approval.",
                },
            )

        assert resp.status_code == 201, resp.text
        assert existing.decision == "reject"
        assert approved_status.status == ReviewStatus.CHANGES_REQUESTED
        assert approved_status.note == (
            "Approval reverted because reviewer decisions changed after approval."
        )
        assert analysis.flagged_for_review is True
        assert audit_log.await_args is not None
        assert audit_log.await_args.kwargs["details"]["approval_invalidated"] is True
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_create_rolls_back_when_audit_fails(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        _passing_org_check(db)

        with (
            patch(
                "api.routes.reviewer_decisions.write_audit_log",
                new=AsyncMock(side_effect=RuntimeError("audit unavailable")),
            ) as audit_log,
            pytest.raises(RuntimeError, match="audit unavailable"),
        ):
            await c.post(
                f"/api/v1/analyses/{analysis_id}/decisions",
                json={
                    "finding_type": "patent",
                    "finding_ref": "US12345B2",
                    "decision": "accept",
                    "note": "Attorney confirms blocking.",
                },
            )

        assert audit_log.await_args is not None
        assert audit_log.await_args.kwargs["fail_closed"] is True
        db.commit.assert_not_awaited()
        db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unknown_finding_type_is_422(self, attorney_client):
        c, _db = attorney_client
        resp = await c.post(
            f"/api/v1/analyses/{uuid.uuid4()}/decisions",
            json={
                "finding_type": "definitely-not-a-real-type",
                "finding_ref": "X",
                "decision": "accept",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_cross_org_analysis_returns_404(self, attorney_client):
        """Posting to another org's analysis returns 404 (never 403 — don't leak)."""
        c, db = attorney_client
        # Default mock db yields scalar_one_or_none -> None
        resp = await c.post(
            f"/api/v1/analyses/{uuid.uuid4()}/decisions",
            json={
                "finding_type": "patent",
                "finding_ref": "US93000006A1",
                "decision": "accept",
            },
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_client_role_forbidden(self, client_role_client):
        """Client-role users cannot create decisions (no comment.create perm)."""
        c, _db = client_role_client
        resp = await c.post(
            f"/api/v1/analyses/{uuid.uuid4()}/decisions",
            json={
                "finding_type": "patent",
                "finding_ref": "US93000006A1",
                "decision": "accept",
            },
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_scientist_role_forbidden(self, scientist_client):
        """Only attorney/admin reviewers can create export-counted decisions."""
        c, _db = scientist_client
        resp = await c.post(
            f"/api/v1/analyses/{uuid.uuid4()}/decisions",
            json={
                "finding_type": "patent",
                "finding_ref": "US93000006A1",
                "decision": "accept",
            },
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/v1/analyses/{id}/decisions — list
# ---------------------------------------------------------------------------


class TestListDecisions:
    @pytest.mark.asyncio
    async def test_list_conceals_first_high_risk_disposition_from_second_reviewer(
        self,
        attorney_client,
    ):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        report_data = _reviewable_report_data()
        analysis_check = MagicMock()
        analysis_check.scalar_one_or_none.return_value = make_analysis_mock(
            id=analysis_id,
            report_data=report_data,
        )
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [
            _make_decision_mock(
                analysis_id=analysis_id,
                finding_ref="US12345B2",
                decision="accept",
                reviewer_user_id="other_reviewer",
                report_fingerprint=report_payload_fingerprint(report_data),
            ),
        ]
        db.execute = AsyncMock(side_effect=[analysis_check, list_result])

        resp = await c.get(f"/api/v1/analyses/{analysis_id}/decisions")

        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "items": [],
            "counts": {"accept": 0, "reject": 0, "edit": 0},
        }

    @pytest.mark.asyncio
    async def test_list_returns_all_with_counts(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        report_data = _reviewable_report_data()

        analysis_check = MagicMock()
        analysis = make_analysis_mock(
            id=analysis_id,
            report_data=report_data,
        )
        analysis_check.scalar_one_or_none.return_value = analysis
        report_fingerprint = report_payload_fingerprint(analysis.report_data)

        decisions = [
            _make_decision_mock(
                analysis_id=analysis_id,
                decision="accept",
                report_fingerprint=report_fingerprint,
            ),
            _make_decision_mock(
                analysis_id=analysis_id,
                decision="accept",
                report_fingerprint=report_fingerprint,
            ),
            _make_decision_mock(
                analysis_id=analysis_id,
                decision="edit",
                report_fingerprint=report_fingerprint,
            ),
            _make_decision_mock(
                analysis_id=analysis_id,
                decision="reject",
                report_fingerprint=report_fingerprint,
            ),
        ]
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = decisions

        db.execute = AsyncMock(side_effect=[analysis_check, list_result])

        resp = await c.get(f"/api/v1/analyses/{analysis_id}/decisions")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data["items"]) == 4
        assert data["counts"] == {"accept": 2, "reject": 1, "edit": 1}
        stmt_sql = str(db.execute.call_args_list[1].args[0]).lower()
        assert "join" in stmt_sql
        assert "users" in stmt_sql
        assert "role" in stmt_sql
        assert "users.membership_active is true" in stmt_sql
        assert "users.membership_deleted_at is null" in stmt_sql
        assert "users.membership_permission_denied_at is null" in stmt_sql

    @pytest.mark.asyncio
    async def test_list_filters_decisions_for_stale_findings(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        report_data = _reviewable_report_data()

        analysis_check = MagicMock()
        analysis_check.scalar_one_or_none.return_value = make_analysis_mock(
            id=analysis_id,
            report_data=report_data,
        )

        decisions = [
            _make_decision_mock(
                analysis_id=analysis_id,
                decision="accept",
                report_fingerprint=report_payload_fingerprint(report_data),
            ),
            _make_decision_mock(
                analysis_id=analysis_id,
                finding_ref="US91000007A1",
                decision="reject",
                report_fingerprint="old-report-fingerprint",
            ),
        ]
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = decisions

        db.execute = AsyncMock(side_effect=[analysis_check, list_result])

        resp = await c.get(f"/api/v1/analyses/{analysis_id}/decisions")

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert [item["finding_ref"] for item in data["items"]] == ["US12345B2"]
        assert data["counts"] == {"accept": 1, "reject": 0, "edit": 0}

    @pytest.mark.asyncio
    async def test_list_cross_org_returns_404(self, attorney_client):
        c, _db = attorney_client
        # Default mock: scalar_one_or_none returns None => 404
        resp = await c.get(f"/api/v1/analyses/{uuid.uuid4()}/decisions")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_client_role_cannot_list_internal_decisions(self, client_role_client):
        """Client users can view reports, not raw attorney decision ledger rows."""
        c, db = client_role_client
        resp = await c.get(f"/api/v1/analyses/{uuid.uuid4()}/decisions")

        assert resp.status_code == 403
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_scientist_role_cannot_list_internal_decisions(self, scientist_client):
        """Scientist users cannot list attorney notes, edits, and reviewer identity."""
        c, db = scientist_client
        resp = await c.get(f"/api/v1/analyses/{uuid.uuid4()}/decisions")

        assert resp.status_code == 403
        db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# DELETE /api/v1/analyses/{id}/decisions/{decision_id}
# ---------------------------------------------------------------------------


class TestDeleteDecision:
    @pytest.mark.asyncio
    async def test_demoted_author_cannot_delete(self, scientist_client):
        """Past authors lose legal-ledger mutation authority after role demotion."""
        c, db = scientist_client

        resp = await c.delete(f"/api/v1/analyses/{uuid.uuid4()}/decisions/{uuid.uuid4()}")

        assert resp.status_code == 403
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_author_can_delete(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        decision_id = uuid.uuid4()

        analysis_check = MagicMock()
        analysis_check.scalar_one_or_none.return_value = make_analysis_mock(
            id=analysis_id,
            report_data=_reviewable_report_data(),
        )

        decision = _make_decision_mock(
            id=decision_id,
            analysis_id=analysis_id,
            reviewer_user_id="clerk_test_user",  # matches default test user
        )
        decision_check = MagicMock()
        decision_check.scalar_one_or_none.return_value = decision
        analysis_for_review = MagicMock()
        analysis_for_review.scalar_one_or_none.return_value = make_analysis_mock(
            id=analysis_id,
            report_data={},
        )
        review_status_check = MagicMock()
        review_status_check.scalar_one_or_none.return_value = None

        db.execute = AsyncMock(
            side_effect=[
                analysis_check,
                decision_check,
                analysis_for_review,
                review_status_check,
            ]
        )

        resp = await c.delete(f"/api/v1/analyses/{analysis_id}/decisions/{decision_id}")
        assert resp.status_code == 204
        db.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_delete_rolls_back_when_audit_fails(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        decision_id = uuid.uuid4()

        analysis_check = MagicMock()
        analysis_check.scalar_one_or_none.return_value = make_analysis_mock(
            id=analysis_id,
            report_data=_reviewable_report_data(),
        )

        decision = _make_decision_mock(
            id=decision_id,
            analysis_id=analysis_id,
            reviewer_user_id="clerk_test_user",
        )
        decision_check = MagicMock()
        decision_check.scalar_one_or_none.return_value = decision
        analysis_for_review = MagicMock()
        analysis_for_review.scalar_one_or_none.return_value = make_analysis_mock(
            id=analysis_id,
            report_data={},
        )
        review_status_check = MagicMock()
        review_status_check.scalar_one_or_none.return_value = None

        db.execute = AsyncMock(
            side_effect=[
                analysis_check,
                decision_check,
                analysis_for_review,
                review_status_check,
            ]
        )

        with (
            patch(
                "api.routes.reviewer_decisions.write_audit_log",
                new=AsyncMock(side_effect=RuntimeError("audit unavailable")),
            ) as audit_log,
            pytest.raises(RuntimeError, match="audit unavailable"),
        ):
            await c.delete(f"/api/v1/analyses/{analysis_id}/decisions/{decision_id}")

        db.delete.assert_awaited_once_with(decision)
        assert audit_log.await_args is not None
        assert audit_log.await_args.kwargs["fail_closed"] is True
        db.commit.assert_not_awaited()
        db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_non_author_non_admin_forbidden(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        decision_id = uuid.uuid4()

        analysis_check = MagicMock()
        analysis_check.scalar_one_or_none.return_value = make_analysis_mock(
            id=analysis_id,
            report_data=_reviewable_report_data(),
        )

        decision = _make_decision_mock(
            id=decision_id,
            analysis_id=analysis_id,
            reviewer_user_id="clerk_some_other_user",  # NOT the caller
        )
        decision_check = MagicMock()
        decision_check.scalar_one_or_none.return_value = decision

        db.execute = AsyncMock(side_effect=[analysis_check, decision_check])

        resp = await c.delete(f"/api/v1/analyses/{analysis_id}/decisions/{decision_id}")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_delete_other_reviewers_decision(self, admin_client):
        c, db = admin_client
        analysis_id = uuid.uuid4()
        decision_id = uuid.uuid4()

        analysis_check = MagicMock()
        analysis_check.scalar_one_or_none.return_value = make_analysis_mock(
            id=analysis_id,
            report_data=_reviewable_report_data(),
        )

        decision = _make_decision_mock(
            id=decision_id,
            analysis_id=analysis_id,
            reviewer_user_id="clerk_some_other_user",
        )
        decision_check = MagicMock()
        decision_check.scalar_one_or_none.return_value = decision
        analysis_for_review = MagicMock()
        analysis_for_review.scalar_one_or_none.return_value = make_analysis_mock(
            id=analysis_id,
            report_data={},
        )
        review_status_check = MagicMock()
        review_status_check.scalar_one_or_none.return_value = None

        db.execute = AsyncMock(
            side_effect=[
                analysis_check,
                decision_check,
                analysis_for_review,
                review_status_check,
            ]
        )

        resp = await c.delete(f"/api/v1/analyses/{analysis_id}/decisions/{decision_id}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_invalidates_approved_status_when_review_coverage_drops(
        self,
        attorney_client,
    ):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        decision_id = uuid.uuid4()
        report_data = valid_report_data_for_patents(
            [
                {"patent_id": "US91000017A1", "risk_level": "high"},
            ],
            trust_mode="counsel",
            opinion_readiness={
                "export_ready": True,
                "jurisdictions_blocking_export": [],
            },
        )
        analysis_check = MagicMock()
        analysis = make_analysis_mock(
            id=analysis_id,
            report_data=report_data,
        )
        analysis_check.scalar_one_or_none.return_value = analysis
        report_fingerprint = report_payload_fingerprint(analysis.report_data)

        deleted_decision = _make_decision_mock(
            id=decision_id,
            analysis_id=analysis_id,
            finding_ref="US91000017A1",
            reviewer_user_id="clerk_test_user",
        )
        decision_check = MagicMock()
        decision_check.scalar_one_or_none.return_value = deleted_decision

        analysis = make_analysis_mock(
            id=analysis_id,
            flagged_for_review=False,
            report_data=report_data,
        )
        analysis_for_review = MagicMock()
        analysis_for_review.scalar_one_or_none.return_value = analysis

        approved_status = _make_review_status_mock(
            analysis_id=analysis_id,
            status=ReviewStatus.APPROVED,
            note="Ready for export.",
        )
        review_status_check = MagicMock()
        review_status_check.scalar_one_or_none.return_value = approved_status

        remaining_decisions = MagicMock()
        remaining_decisions.scalars.return_value.all.return_value = [
            _make_decision_mock(
                analysis_id=analysis_id,
                finding_ref="US91000017A1",
                reviewer_user_id="clerk_other_reviewer",
                report_fingerprint=report_fingerprint,
            )
        ]

        db.execute = AsyncMock(
            side_effect=[
                analysis_check,
                decision_check,
                analysis_for_review,
                review_status_check,
                remaining_decisions,
            ]
        )

        with patch(
            "api.routes.reviewer_decisions.write_audit_log",
            new=AsyncMock(),
        ) as audit_log:
            resp = await c.delete(f"/api/v1/analyses/{analysis_id}/decisions/{decision_id}")

        assert resp.status_code == 204
        assert approved_status.status == ReviewStatus.CHANGES_REQUESTED
        assert approved_status.note == (
            "Approval reverted because reviewer decision coverage changed after approval."
        )
        assert analysis.flagged_for_review is True
        assert audit_log.await_args is not None
        details = audit_log.await_args.kwargs["details"]
        assert details["approval_invalidated"] is True
        assert any("requires dual review" in blocker for blocker in details["approval_blockers"])

    @pytest.mark.asyncio
    async def test_delete_not_found(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()

        analysis_check = MagicMock()
        analysis_check.scalar_one_or_none.return_value = make_analysis_mock(
            id=analysis_id,
            report_data=_reviewable_report_data(),
        )

        missing = MagicMock()
        missing.scalar_one_or_none.return_value = None

        db.execute = AsyncMock(side_effect=[analysis_check, missing])

        resp = await c.delete(f"/api/v1/analyses/{analysis_id}/decisions/{uuid.uuid4()}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Service-layer unit tests for ``api.services.reviewer_decisions``
# ---------------------------------------------------------------------------


class TestReviewerDecisionsService:
    @pytest.mark.asyncio
    async def test_assert_analysis_in_org_can_lock_authoritative_analysis_row(self):
        from api.services.reviewer_decisions import assert_analysis_in_org

        analysis = make_analysis_mock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = analysis
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)

        resolved = await assert_analysis_in_org(
            db,
            analysis_id=analysis.id,
            org_id=analysis.org_id,
            for_update=True,
        )

        assert resolved is analysis
        statement = db.execute.await_args.args[0]
        assert "FOR UPDATE" in str(statement)
        assert "analyses.status !=" in str(statement)
        assert AnalysisStatus.DELETED in statement.compile().params.values()

    def test_demoted_author_fails_service_level_delete_guard(self):
        from api.errors import APIError
        from api.services.reviewer_decisions import assert_can_delete_decision

        decision = _make_decision_mock(reviewer_user_id="clerk_former_attorney")
        user = make_user(
            clerk_user_id="clerk_former_attorney",
            role=UserRole.SCIENTIST,
        )

        with pytest.raises(APIError) as exc_info:
            assert_can_delete_decision(decision, user=user)

        assert exc_info.value.status == 403

    @pytest.mark.asyncio
    async def test_assert_analysis_in_org_404_when_missing(self):
        from unittest.mock import AsyncMock, MagicMock

        from api.errors import APIError
        from api.services.reviewer_decisions import assert_analysis_in_org

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(APIError) as exc:
            await assert_analysis_in_org(
                db,
                analysis_id=uuid.uuid4(),
                org_id=uuid.uuid4(),
            )
        assert exc.value.status == 404

    @pytest.mark.asyncio
    async def test_find_existing_decision_scopes_by_org(self):
        from api.services.reviewer_decisions import find_existing_decision

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)

        await find_existing_decision(
            db,
            analysis_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            finding_type="patent",
            finding_ref="US12345B2",
            reviewer_user_id="clerk_test_user",
        )

        statement = db.execute.await_args.args[0]
        assert "analysis_reviewer_decisions.org_id" in str(statement)

    def test_assert_can_delete_decision_blocks_non_author_non_admin(self):
        from unittest.mock import MagicMock

        from api.db.models import UserRole
        from api.errors import APIError
        from api.services.reviewer_decisions import assert_can_delete_decision

        decision = MagicMock()
        decision.reviewer_user_id = "clerk_other_user"
        user = MagicMock()
        user.clerk_user_id = "clerk_self"
        user.role = UserRole.ATTORNEY  # not admin, not author

        with pytest.raises(APIError) as exc:
            assert_can_delete_decision(decision, user=user)
        assert exc.value.status == 403

    def test_assert_can_delete_decision_allows_author(self):
        from unittest.mock import MagicMock

        from api.db.models import UserRole
        from api.services.reviewer_decisions import assert_can_delete_decision

        decision = MagicMock()
        decision.reviewer_user_id = "clerk_self"
        user = MagicMock()
        user.clerk_user_id = "clerk_self"
        user.role = UserRole.ATTORNEY

        # Should not raise.
        assert_can_delete_decision(decision, user=user)

    def test_assert_can_delete_decision_allows_admin(self):
        from unittest.mock import MagicMock

        from api.db.models import UserRole
        from api.services.reviewer_decisions import assert_can_delete_decision

        decision = MagicMock()
        decision.reviewer_user_id = "clerk_other_user"
        user = MagicMock()
        user.clerk_user_id = "clerk_self"
        user.role = UserRole.ADMIN

        # Should not raise: admin can delete other reviewers' decisions.
        assert_can_delete_decision(decision, user=user)


# Keep ``make_user``/``UserRole`` importable so editors / formatters don't
# strip them if we need them later. They are currently used indirectly via
# the ``attorney_client`` / ``admin_client`` fixtures in ``conftest``.
__all__ = ["make_user", "UserRole"]
