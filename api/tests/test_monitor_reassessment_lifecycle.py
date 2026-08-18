"""Focused legal-lifecycle tests for monitoring-invalidated conclusions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from api.db.models import (
    AnalysisReviewStatus,
    ExportStatus,
    MonitorConclusionReassessment,
    ReviewStatus,
    UserRole,
)
from api.errors import APIError
from api.schemas.monitors import MonitorConclusionImpact, ResolveMonitorConclusionRequest
from api.services.monitor_reassessment_lifecycle import (
    ATTESTATION_VERSION,
    record_monitor_conclusion_invalidations,
    resolve_monitor_conclusion,
)
from api.services.monitors import delete_monitor
from api.services.reports import resolve_export_download

REASSESSMENT_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
ALERT_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
EVIDENCE_DIGEST = "b" * 64
EVIDENCE_VERSION = "2026-07-monitor-evidence-v1"
EVIDENCE_OBSERVED_AT = datetime(2026, 7, 26, 10, 0, tzinfo=UTC)


def _result(*, scalar=None, rows=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = list(rows or [])
    result.scalars.return_value.first.return_value = list(rows or [None])[0] if rows else None
    return result


def _impact() -> dict:
    now = datetime.now(UTC).isoformat()
    return {
        "conclusion_id": "clearance:US",
        "conclusion_type": "jurisdiction_clearance",
        "label": "US FTO clearance",
        "previous_outcome": "clear",
        "status": "review_required",
        "source_report_id": "report-1",
        "dependency_fingerprint": "a" * 64,
        "invalidated_at": now,
        "latest_observed_at": now,
        "reason_codes": ["new_patent_candidate"],
        "trigger_patent_ids": ["US20260123456A1"],
        "trigger_event_ids": [],
        "jurisdictions": ["US"],
        "reassessment_id": str(REASSESSMENT_ID),
        "alert_id": str(ALERT_ID),
        "evidence_digest": EVIDENCE_DIGEST,
        "evidence_version": EVIDENCE_VERSION,
        "evidence_observed_at": EVIDENCE_OBSERVED_AT.isoformat(),
    }


def _resolution_body(**overrides) -> ResolveMonitorConclusionRequest:
    values = {
        "resolution": "reaffirmed",
        "resolution_note": (
            "Reviewed the cited continuation and confirmed the prior outcome remains appropriate."
        ),
        "attestation_accepted": True,
        "reassessment_id": REASSESSMENT_ID,
        "alert_id": ALERT_ID,
        "dependency_fingerprint": "a" * 64,
        "evidence_digest": EVIDENCE_DIGEST,
        "evidence_version": EVIDENCE_VERSION,
        "evidence_observed_at": EVIDENCE_OBSERVED_AT,
    }
    values.update(overrides)
    return ResolveMonitorConclusionRequest(**values)


def _bind_record(record) -> None:
    record.id = REASSESSMENT_ID
    record.dependency_fingerprint = "a" * 64
    record.trigger_evidence = {
        "alert_id": str(ALERT_ID),
        "evidence_digest": EVIDENCE_DIGEST,
        "evidence_version": EVIDENCE_VERSION,
        "evidence_observed_at": EVIDENCE_OBSERVED_AT.isoformat(),
    }


def test_monitor_conclusion_impact_rejects_unbound_or_time_reversed_evidence() -> None:
    missing_fingerprint = _impact()
    missing_fingerprint["dependency_fingerprint"] = ""
    with pytest.raises(ValidationError):
        MonitorConclusionImpact.model_validate(missing_fingerprint)

    time_reversed = _impact()
    time_reversed["invalidated_at"] = "2026-07-26T12:00:00Z"
    time_reversed["latest_observed_at"] = "2026-07-26T11:59:59Z"
    with pytest.raises(ValidationError):
        MonitorConclusionImpact.model_validate(time_reversed)


@pytest.mark.asyncio
async def test_invalidation_atomically_revokes_approval_and_supersedes_exports() -> None:
    org_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    monitor = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=org_id,
        user_id=uuid.uuid4(),
        source_analysis_id=analysis_id,
        source_report_id="report-1",
    )
    analysis = SimpleNamespace(id=analysis_id, org_id=org_id, flagged_for_review=False)
    approval = MagicMock(spec=AnalysisReviewStatus)
    approval.status = ReviewStatus.APPROVED
    approval.reviewer_user_id = "counsel-1"
    approval.reviewer_name = "Ada Counsel"
    approval.reviewer_email = "ada@example.com"
    approval.reviewed_at = datetime.now(UTC)
    approval.note = "Approved after review"
    export = SimpleNamespace(
        id=uuid.uuid4(),
        superseded_at=None,
        superseded_reason="",
        superseded_conclusion_ids=[],
    )
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _result(scalar=analysis),
            _result(rows=[]),
            _result(scalar=approval),
            _result(rows=[export]),
        ]
    )
    db.add = MagicMock()
    db.flush = AsyncMock()

    with patch(
        "api.services.monitor_reassessment_lifecycle.write_audit_log",
        new=AsyncMock(),
    ) as audit:
        rows = await record_monitor_conclusion_invalidations(
            db,
            monitor=monitor,
            impacts=[_impact()],
        )

    assert len(rows) == 1
    assert isinstance(rows[0], MonitorConclusionReassessment)
    assert rows[0].status == "open"
    assert rows[0].trigger_evidence["review_approval_at_invalidation"]["reviewer_name"] == (
        "Ada Counsel"
    )
    assert approval.status == ReviewStatus.CHANGES_REQUESTED
    assert "must not be relied upon" in approval.note
    assert analysis.flagged_for_review is True
    assert isinstance(export.superseded_at, datetime)
    assert export.superseded_reason == "monitor_conclusion_invalidation"
    assert export.superseded_conclusion_ids == ["clearance:US"]
    assert audit.await_args.kwargs["fail_closed"] is True
    assert audit.await_args.kwargs["action"] == "monitor.conclusions.invalidated"


@pytest.mark.asyncio
async def test_attorney_attestation_resolves_one_conclusion_without_approving_report() -> None:
    org_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    monitor = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=org_id,
        source_analysis_id=analysis_id,
        stale_conclusions=[_impact()],
        conclusion_status="review_required",
        last_run_status="review_required",
    )
    record = SimpleNamespace(
        id=REASSESSMENT_ID,
        org_id=org_id,
        monitor_id=monitor.id,
        source_analysis_id=analysis_id,
        source_report_id="report-1",
        conclusion_id="clearance:US",
        status="open",
        resolution_note="",
        replacement_analysis_id=None,
        resolved_by_user_id=None,
        attestation_version="",
        attestation_accepted=False,
        dependency_fingerprint="a" * 64,
        trigger_evidence={
            "alert_id": str(ALERT_ID),
            "evidence_digest": EVIDENCE_DIGEST,
            "evidence_version": EVIDENCE_VERSION,
            "evidence_observed_at": EVIDENCE_OBSERVED_AT.isoformat(),
        },
    )
    user = SimpleNamespace(
        id=uuid.uuid4(),
        role=UserRole.ATTORNEY,
        full_name="Ada Counsel",
        email="ada@example.com",
    )
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _result(scalar=monitor),
            _result(scalar=record),
        ]
    )
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    body = _resolution_body()

    with patch(
        "api.services.monitor_reassessment_lifecycle.write_audit_log",
        new=AsyncMock(),
    ) as audit:
        resolved = await resolve_monitor_conclusion(
            db,
            monitor_id=monitor.id,
            conclusion_id="clearance:US",
            org_id=org_id,
            user=user,
            body=body,
        )

    assert resolved.status == "reaffirmed"
    assert resolved.attestation_version == ATTESTATION_VERSION
    assert resolved.attestation_accepted is True
    assert resolved.reviewer_role == "attorney"
    assert monitor.stale_conclusions == []
    assert monitor.conclusion_status == "reassessed"
    assert monitor.last_run_status == "reassessed"
    assert audit.await_args.kwargs["fail_closed"] is True
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body_override",
    [
        {"alert_id": uuid.UUID("99999999-9999-4999-8999-999999999999")},
        {"dependency_fingerprint": "c" * 64},
        {"evidence_digest": "d" * 64},
        {"evidence_version": "different-evidence-contract"},
        {
            "evidence_observed_at": datetime(
                2026,
                7,
                26,
                10,
                1,
                tzinfo=UTC,
            )
        },
    ],
)
async def test_reassessment_compare_and_swap_rejects_episode_drift(
    body_override: dict,
) -> None:
    org_id = uuid.uuid4()
    monitor = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=org_id,
        stale_conclusions=[_impact()],
    )
    record = SimpleNamespace(
        id=REASSESSMENT_ID,
        conclusion_id="clearance:US",
        status="open",
        dependency_fingerprint="a" * 64,
        trigger_evidence={
            "alert_id": str(ALERT_ID),
            "evidence_digest": EVIDENCE_DIGEST,
            "evidence_version": EVIDENCE_VERSION,
            "evidence_observed_at": EVIDENCE_OBSERVED_AT.isoformat(),
        },
    )
    user = SimpleNamespace(
        id=uuid.uuid4(),
        role=UserRole.ATTORNEY,
        full_name="Ada Counsel",
        email="ada@example.com",
    )
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _result(scalar=monitor),
            _result(scalar=record),
        ]
    )

    with pytest.raises(APIError) as exc_info:
        await resolve_monitor_conclusion(
            db,
            monitor_id=monitor.id,
            conclusion_id="clearance:US",
            org_id=org_id,
            user=user,
            body=_resolution_body(**body_override),
        )

    assert exc_info.value.status == 409
    assert "changed" in exc_info.value.detail
    db.flush.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_reassessment_id_must_select_the_exact_open_episode() -> None:
    org_id = uuid.uuid4()
    monitor = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=org_id,
        stale_conclusions=[_impact()],
    )
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _result(scalar=monitor),
            _result(scalar=None),
        ]
    )
    user = SimpleNamespace(
        id=uuid.uuid4(),
        role=UserRole.ATTORNEY,
        full_name="Ada Counsel",
        email="ada@example.com",
    )

    with pytest.raises(APIError) as exc_info:
        await resolve_monitor_conclusion(
            db,
            monitor_id=monitor.id,
            conclusion_id="clearance:US",
            org_id=org_id,
            user=user,
            body=_resolution_body(),
        )

    assert exc_info.value.status == 409
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_reassessment_rejects_non_attorney_before_reading_tenant_data() -> None:
    db = AsyncMock()
    with pytest.raises(APIError) as exc_info:
        await resolve_monitor_conclusion(
            db,
            monitor_id=uuid.uuid4(),
            conclusion_id="clearance:US",
            org_id=uuid.uuid4(),
            user=SimpleNamespace(role=UserRole.ADMIN),
            body=_resolution_body(
                resolution="withdrawn",
                resolution_note="The prior conclusion is withdrawn pending a new legal analysis.",
            ),
        )

    assert exc_info.value.status == 403
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_historical_reassessment_retry_is_read_only() -> None:
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    note = "Reviewed the new evidence and reaffirmed the prior conclusion as written."
    monitor = SimpleNamespace(id=uuid.uuid4(), org_id=org_id)
    record = SimpleNamespace(
        id=REASSESSMENT_ID,
        conclusion_id="clearance:US",
        status="reaffirmed",
        resolution_note=note,
        replacement_analysis_id=None,
        resolved_by_user_id=user_id,
        attestation_version=ATTESTATION_VERSION,
        attestation_accepted=True,
        dependency_fingerprint="a" * 64,
        trigger_evidence={
            "alert_id": str(ALERT_ID),
            "evidence_digest": EVIDENCE_DIGEST,
            "evidence_version": EVIDENCE_VERSION,
            "evidence_observed_at": EVIDENCE_OBSERVED_AT.isoformat(),
        },
    )
    user = SimpleNamespace(
        id=user_id,
        role=UserRole.ATTORNEY,
        full_name="Ada Counsel",
        email="ada@example.com",
    )
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _result(scalar=monitor),
            _result(scalar=record),
        ]
    )

    with pytest.raises(APIError) as exc_info:
        await resolve_monitor_conclusion(
            db,
            monitor_id=monitor.id,
            conclusion_id="clearance:US",
            org_id=org_id,
            user=user,
            body=_resolution_body(resolution_note=note),
        )

    assert exc_info.value.status == 409
    assert "read-only" in exc_info.value.detail
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_superseded_reassessment_rejects_source_analysis_as_replacement() -> None:
    org_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    monitor = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=org_id,
        stale_conclusions=[_impact()],
    )
    record = SimpleNamespace(
        id=REASSESSMENT_ID,
        conclusion_id="clearance:US",
        source_analysis_id=analysis_id,
        status="open",
        dependency_fingerprint="a" * 64,
        trigger_evidence={
            "alert_id": str(ALERT_ID),
            "evidence_digest": EVIDENCE_DIGEST,
            "evidence_version": EVIDENCE_VERSION,
            "evidence_observed_at": EVIDENCE_OBSERVED_AT.isoformat(),
        },
    )
    user = SimpleNamespace(
        id=uuid.uuid4(),
        role=UserRole.ATTORNEY,
        full_name="Ada Counsel",
        email="ada@example.com",
    )
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _result(scalar=monitor),
            _result(scalar=record),
        ]
    )

    with pytest.raises(APIError) as exc_info:
        await resolve_monitor_conclusion(
            db,
            monitor_id=monitor.id,
            conclusion_id="clearance:US",
            org_id=org_id,
            user=user,
            body=_resolution_body(
                resolution="superseded",
                resolution_note=(
                    "A new completed analysis replaces the prior conclusion after review."
                ),
                replacement_analysis_id=analysis_id,
            ),
        )

    assert exc_info.value.status == 422
    assert "different completed analysis" in exc_info.value.detail
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_reassessment_requires_durable_reviewer_identity_snapshot() -> None:
    db = AsyncMock()
    with pytest.raises(APIError) as exc_info:
        await resolve_monitor_conclusion(
            db,
            monitor_id=uuid.uuid4(),
            conclusion_id="clearance:US",
            org_id=uuid.uuid4(),
            user=SimpleNamespace(
                role=UserRole.ATTORNEY,
                full_name="",
                email="counsel@example.com",
            ),
            body=_resolution_body(
                resolution="withdrawn",
                resolution_note="The prior conclusion is withdrawn after reviewing the new evidence.",
            ),
        )

    assert exc_info.value.status == 409
    assert "profile name and email" in exc_info.value.detail
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_superseded_export_download_fails_closed() -> None:
    job = SimpleNamespace(
        id=uuid.uuid4(),
        status=ExportStatus.COMPLETED,
        file_url="gs://private-bucket/report.pdf",
        superseded_at=datetime.now(UTC),
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_result(scalar=job))

    with pytest.raises(APIError) as exc_info:
        await resolve_export_download(
            db,
            job_id=job.id,
            org_id=uuid.uuid4(),
        )

    assert exc_info.value.status == 409
    assert "superseded by monitoring evidence" in exc_info.value.detail


@pytest.mark.asyncio
async def test_monitor_delete_cannot_erase_an_unresolved_conclusion() -> None:
    org_id = uuid.uuid4()
    monitor = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=org_id,
        stale_conclusions=[_impact()],
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_result(scalar=monitor))
    db.delete = AsyncMock()

    with pytest.raises(APIError) as exc_info:
        await delete_monitor(
            db,
            monitor_id=monitor.id,
            org_id=org_id,
            user_id=uuid.uuid4(),
        )

    assert exc_info.value.status == 409
    assert "Acknowledging alerts is not a legal reassessment" in exc_info.value.detail
    db.delete.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_monitor_delete_checks_durable_open_episodes_when_cache_is_empty() -> None:
    org_id = uuid.uuid4()
    monitor = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=org_id,
        stale_conclusions=[],
    )
    durable_reassessment_id = uuid.uuid4()
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _result(scalar=monitor),
            _result(scalar=durable_reassessment_id),
        ]
    )
    db.delete = AsyncMock()

    with pytest.raises(APIError) as exc_info:
        await delete_monitor(
            db,
            monitor_id=monitor.id,
            org_id=org_id,
            user_id=uuid.uuid4(),
        )

    assert exc_info.value.status == 409
    assert "legal reassessment" in exc_info.value.detail
    first_statement = db.execute.await_args_list[0].args[0]
    assert first_statement._for_update_arg is not None
    db.delete.assert_not_awaited()
    db.commit.assert_not_awaited()
