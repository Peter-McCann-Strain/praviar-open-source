from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from api.db.models import WeeklyDigestDelivery
from api.services.email_models import DeliveryLookupResult, DeliverySubmissionResult
from api.services.notification_unsubscribe import DigestUnsubscribeCapability
from api.services.weekly_digest_delivery import (
    WeeklyDigestDispatchClaim,
    claim_weekly_digest_dispatch,
    record_weekly_digest_reconciliation,
    record_weekly_digest_submission,
    weekly_digest_submission_id,
)
from api.workers import email_task_weekly


class _FakeSessionContext:
    def __init__(self, db):
        self._db = db

    def __enter__(self):
        return self._db

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeResult:
    def __init__(self, values):
        self._values = list(values)

    def scalars(self):
        return self

    def __iter__(self):
        return iter(self._values)

    def all(self):
        return list(self._values)

    def scalar_one(self):
        return self._values[0]

    def scalar_one_or_none(self):
        return self._values[0] if self._values else None


def _user(**overrides):
    values = {
        "id": uuid.uuid4(),
        "org_id": uuid.uuid4(),
        "email": "ada@example.com",
        "full_name": "Ada",
        "role": "attorney",
        "preferences": {"email_digest_frequency": "weekly"},
        "membership_active": True,
        "membership_deleted_at": None,
        "membership_permission_denied_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _delivery(*, user, state="prepared"):
    return WeeklyDigestDelivery(
        id=uuid.uuid4(),
        org_id=user.org_id,
        user_id=user.id,
        period_start=datetime(2026, 7, 6, 9, tzinfo=UTC),
        period_end=datetime(2026, 7, 13, 9, tzinfo=UTC),
        state=state,
        submission_id="d" * 64,
        reconciliation_attempt_count=0,
    )


def test_weekly_digest_submission_identity_is_stable_and_period_specific(monkeypatch):
    monkeypatch.setattr(
        "api.services.weekly_digest_delivery._operation_key",
        lambda: b"k" * 32,
    )
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    first_period = datetime(2026, 7, 6, 9, tzinfo=UTC)

    first = weekly_digest_submission_id(
        user_id=user_id,
        org_id=org_id,
        window_start=first_period,
    )
    replay = weekly_digest_submission_id(
        user_id=user_id,
        org_id=org_id,
        window_start=first_period,
    )
    next_period = weekly_digest_submission_id(
        user_id=user_id,
        org_id=org_id,
        window_start=first_period + timedelta(days=7),
    )

    assert first == replay
    assert first != next_period
    assert len(first) == 64


def test_claim_commits_only_token_digest_and_ambiguous_send_is_never_reopened(
    monkeypatch,
):
    user = _user()
    delivery = _delivery(user=user)
    capability = DigestUnsubscribeCapability(
        token="du1." + "t" * 86,
        token_digest="a" * 64,
        expires_at=datetime(2026, 10, 14, 12, tzinfo=UTC),
    )
    monkeypatch.setattr(
        "api.services.weekly_digest_delivery.create_digest_unsubscribe_capability",
        lambda now: capability,
    )
    now = datetime(2026, 7, 16, 12, tzinfo=UTC)

    claim = claim_weekly_digest_dispatch(
        delivery,
        recipient_email=user.email,
        now=now,
    )
    assert claim is not None
    assert claim.unsubscribe_token == capability.token
    assert delivery.unsubscribe_token_digest == capability.token_digest
    assert capability.token not in repr(delivery.__dict__)
    assert delivery.state == "dispatching"

    record_weekly_digest_submission(
        delivery,
        result=DeliverySubmissionResult(status="outcome_unknown"),
        now=now,
    )
    assert delivery.state == "outcome_unknown"

    # Not-found reconciliation remains ambiguous and cannot transition back to
    # prepared/dispatching, which would permit a duplicate provider POST.
    record_weekly_digest_reconciliation(
        delivery,
        result=DeliveryLookupResult(status="not_found"),
        now=now + timedelta(minutes=2),
    )
    assert delivery.state == "outcome_unknown"
    assert delivery.reconciliation_attempt_count == 1

    record_weekly_digest_reconciliation(
        delivery,
        result=DeliveryLookupResult(status="found", message_id="msg-recovered"),
        now=now + timedelta(minutes=7),
    )
    assert delivery.state == "provider_accepted"
    assert delivery.provider_message_id == "msg-recovered"
    assert delivery.recipient_email is None


def test_terminal_submission_states_remove_recipient_mailbox():
    user = _user()
    now = datetime(2026, 7, 16, 12, tzinfo=UTC)

    accepted = _delivery(user=user, state="dispatching")
    accepted.recipient_email = user.email
    accepted.unsubscribe_token_digest = "a" * 64
    accepted.unsubscribe_expires_at = now + timedelta(days=90)
    accepted.provider_attempt_started_at = now
    record_weekly_digest_submission(
        accepted,
        result=DeliverySubmissionResult(status="accepted", message_id="msg-accepted"),
        now=now,
    )

    rejected = _delivery(user=user, state="dispatching")
    rejected.recipient_email = user.email
    rejected.unsubscribe_token_digest = "b" * 64
    rejected.unsubscribe_expires_at = now + timedelta(days=90)
    rejected.provider_attempt_started_at = now
    record_weekly_digest_submission(
        rejected,
        result=DeliverySubmissionResult(status="rejected"),
        now=now,
    )

    assert accepted.state == "provider_accepted"
    assert accepted.recipient_email is None
    assert accepted.unsubscribe_token_digest == "a" * 64
    assert rejected.state == "rejected"
    assert rejected.recipient_email is None
    assert rejected.unsubscribe_token_digest is None


def test_aggregate_user_activity_uses_closed_open_completion_window(monkeypatch):
    statements = []
    results = iter([_FakeResult([2]), _FakeResult([1]), _FakeResult([])])
    fake_db = SimpleNamespace(
        execute=lambda statement: (statements.append(statement), next(results))[1],
        commit=lambda: None,
    )
    monkeypatch.setattr(email_task_weekly, "bind_org_to_sync_session", lambda *args: None)

    email_task_weekly._aggregate_user_activity(
        fake_db,
        period_start=datetime(2026, 7, 6, 9, tzinfo=UTC),
        period_end=datetime(2026, 7, 13, 9, tzinfo=UTC),
        org_ids={"org-1"},
    )

    analyses_sql = str(statements[0])
    alerts_sql = str(statements[1])
    assert "analyses.completed_at >=" in analyses_sql
    assert "analyses.completed_at <" in analyses_sql
    assert "monitor_alerts.created_at >=" in alerts_sql
    assert "monitor_alerts.created_at <" in alerts_sql


def test_existing_ambiguous_delivery_is_reconciled_only_and_not_resubmitted(monkeypatch):
    user = _user()
    delivery = _delivery(user=user, state="outcome_unknown")
    delivery.recipient_email = user.email
    delivery.unsubscribe_token_digest = "a" * 64
    delivery.unsubscribe_expires_at = datetime(2026, 10, 1, tzinfo=UTC)
    delivery.provider_attempt_started_at = datetime(2026, 7, 13, 9, tzinfo=UTC)
    db = SimpleNamespace(commit=lambda: None)

    monkeypatch.setattr(email_task_weekly, "bind_org_to_sync_session", lambda *args: None)
    monkeypatch.setattr(email_task_weekly, "_lock_digest_user", lambda *args, **kwargs: user)
    monkeypatch.setattr(
        email_task_weekly,
        "get_or_create_weekly_digest_delivery",
        lambda *args, **kwargs: delivery,
    )
    submit = MagicMock(side_effect=AssertionError("ambiguous delivery must never be submitted"))
    monkeypatch.setattr(email_task_weekly, "_submit_weekly_digest", submit)

    outcome = email_task_weekly._process_digest_recipient(
        db,
        listed_user=user,
        period_start=delivery.period_start,
        period_end=delivery.period_end,
        analyses_count=1,
        alerts_count=0,
        top_risks=[],
    )

    assert outcome == "pending"
    submit.assert_not_called()


def test_final_unsubscribe_recheck_cancels_before_provider_io(monkeypatch):
    listed_user = _user()
    active_user = _user(id=listed_user.id, org_id=listed_user.org_id)
    unsubscribed_user = _user(
        id=listed_user.id,
        org_id=listed_user.org_id,
        preferences={"email_digest_frequency": "off"},
    )
    delivery = _delivery(user=listed_user)
    locked_users = iter([active_user, unsubscribed_user])
    db = SimpleNamespace(commit=lambda: None, rollback=lambda: None)

    monkeypatch.setattr(email_task_weekly, "bind_org_to_sync_session", lambda *args: None)
    monkeypatch.setattr(
        email_task_weekly,
        "_lock_digest_user",
        lambda *args, **kwargs: next(locked_users),
    )
    monkeypatch.setattr(
        email_task_weekly,
        "get_or_create_weekly_digest_delivery",
        lambda *args, **kwargs: delivery,
    )

    def _claim(delivery, *, recipient_email, now):
        delivery.state = "dispatching"
        delivery.recipient_email = recipient_email
        delivery.provider_attempt_started_at = now
        delivery.unsubscribe_token_digest = "a" * 64
        delivery.unsubscribe_expires_at = now + timedelta(days=90)
        return WeeklyDigestDispatchClaim(
            delivery_id=delivery.id,
            submission_id=delivery.submission_id,
            unsubscribe_token="du1." + "t" * 86,
        )

    monkeypatch.setattr(email_task_weekly, "claim_weekly_digest_dispatch", _claim)
    monkeypatch.setattr(
        email_task_weekly,
        "lock_weekly_digest_delivery",
        lambda *args, **kwargs: delivery,
    )
    submit = MagicMock(side_effect=AssertionError("unsubscribed user must not be sent"))
    monkeypatch.setattr(email_task_weekly, "_submit_weekly_digest", submit)

    outcome = email_task_weekly._process_digest_recipient(
        db,
        listed_user=listed_user,
        period_start=delivery.period_start,
        period_end=delivery.period_end,
        analyses_count=1,
        alerts_count=0,
        top_risks=[],
    )

    assert outcome == "skipped"
    assert delivery.state == "cancelled"
    assert delivery.recipient_email is None
    assert delivery.unsubscribe_token_digest is None
    submit.assert_not_called()


def test_sweep_isolates_one_recipient_failure_and_continues(monkeypatch):
    org_id = uuid.uuid4()
    users = [_user(org_id=org_id), _user(org_id=org_id)]
    execute_results = iter([_FakeResult([org_id]), _FakeResult(users)])
    db = SimpleNamespace(
        execute=lambda _statement: next(execute_results),
        commit=lambda: None,
        rollback=lambda: None,
    )

    monkeypatch.setattr(
        email_task_weekly,
        "Session",
        lambda _engine: _FakeSessionContext(db),
    )
    monkeypatch.setattr(email_task_weekly, "get_sync_engine", lambda: object())
    monkeypatch.setattr(
        email_task_weekly,
        "_reconcile_due_deliveries",
        lambda *args, **kwargs: {"recovered": 0, "pending": 0, "errors": 0},
    )
    monkeypatch.setattr(
        email_task_weekly,
        "_aggregate_user_activity",
        lambda *args, **kwargs: {org_id: {"analyses_count": 1, "alerts_count": 0, "top_risks": []}},
    )
    outcomes = iter([RuntimeError("recipient one failed"), "sent"])

    def _process(*args, **kwargs):
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(email_task_weekly, "_process_digest_recipient", _process)
    monkeypatch.setattr(email_task_weekly, "_count_unresolved_deliveries", lambda *a, **k: 0)

    result = email_task_weekly.send_weekly_digest_task(SimpleNamespace())

    assert result == {
        "status": "completed",
        "sent": 1,
        "reconciled": 0,
        "errors": 1,
        "skipped": 0,
        "skipped_already_sent": 0,
        "pending": 0,
    }


def test_reconciliation_recovers_found_and_retains_ambiguous_deliveries(monkeypatch):
    org_id = uuid.uuid4()
    found_id = uuid.uuid4()
    unavailable_id = uuid.uuid4()
    missing_recipient_id = uuid.uuid4()
    due = [
        (found_id, "found-submission", "found@example.com"),
        (unavailable_id, "unknown-submission", "unknown@example.com"),
        (missing_recipient_id, "missing-recipient", None),
    ]
    deliveries = {
        delivery_id: SimpleNamespace(id=delivery_id, state="dispatching")
        for delivery_id, _submission_id, _recipient in due
    }
    db = SimpleNamespace(
        execute=lambda _statement: _FakeResult(due),
        commit=MagicMock(),
    )
    lookup = MagicMock(
        side_effect=[
            DeliveryLookupResult(status="found", message_id="provider-message"),
            RuntimeError("provider unavailable"),
        ]
    )
    record = MagicMock()

    monkeypatch.setattr(email_task_weekly, "bind_org_to_sync_session", lambda *args: None)
    monkeypatch.setattr(email_task_weekly, "_lookup_weekly_digest", lookup)
    monkeypatch.setattr(
        email_task_weekly,
        "lock_weekly_digest_delivery",
        lambda _db, *, delivery_id, org_id: deliveries[delivery_id],
    )
    monkeypatch.setattr(email_task_weekly, "record_weekly_digest_reconciliation", record)

    outcome = email_task_weekly._reconcile_due_deliveries(
        db,
        org_ids=[org_id],
        now=datetime(2026, 7, 16, 12, tzinfo=UTC),
    )

    assert outcome == {"recovered": 1, "pending": 2, "errors": 2}
    assert record.call_count == 3
    assert lookup.call_count == 2
    assert db.commit.call_count == 4


def test_reconciliation_ignores_delivery_that_became_terminal(monkeypatch):
    org_id = uuid.uuid4()
    delivery_id = uuid.uuid4()
    db = SimpleNamespace(
        execute=lambda _statement: _FakeResult(
            [(delivery_id, "submission", "recipient@example.com")]
        ),
        commit=MagicMock(),
    )
    record = MagicMock()

    monkeypatch.setattr(email_task_weekly, "bind_org_to_sync_session", lambda *args: None)
    monkeypatch.setattr(
        email_task_weekly,
        "_lookup_weekly_digest",
        lambda **_kwargs: DeliveryLookupResult(status="found", message_id="message"),
    )
    monkeypatch.setattr(
        email_task_weekly,
        "lock_weekly_digest_delivery",
        lambda *args, **kwargs: SimpleNamespace(state="provider_accepted"),
    )
    monkeypatch.setattr(email_task_weekly, "record_weekly_digest_reconciliation", record)

    outcome = email_task_weekly._reconcile_due_deliveries(
        db,
        org_ids=[org_id],
        now=datetime(2026, 7, 16, 12, tzinfo=UTC),
    )

    assert outcome == {"recovered": 0, "pending": 0, "errors": 0}
    record.assert_not_called()


def test_count_unresolved_deliveries_scopes_every_query_to_its_tenant(monkeypatch):
    org_ids = [uuid.uuid4(), uuid.uuid4()]
    results = iter([_FakeResult([2]), _FakeResult([3])])
    db = SimpleNamespace(execute=lambda _statement: next(results), commit=MagicMock())
    bound_orgs = []
    monkeypatch.setattr(
        email_task_weekly,
        "bind_org_to_sync_session",
        lambda _db, org_id: bound_orgs.append(org_id),
    )

    total = email_task_weekly._count_unresolved_deliveries(db, org_ids=org_ids)

    assert total == 5
    assert bound_orgs == org_ids
    assert db.commit.call_count == 2


def test_process_recipient_submits_once_and_records_provider_acceptance(monkeypatch):
    user = _user()
    delivery = _delivery(user=user)
    db = SimpleNamespace(commit=MagicMock(), rollback=MagicMock())
    claim = WeeklyDigestDispatchClaim(
        delivery_id=delivery.id,
        submission_id=delivery.submission_id,
        unsubscribe_token="du1." + "t" * 86,
    )
    record_submission = MagicMock()

    monkeypatch.setattr(email_task_weekly, "bind_org_to_sync_session", lambda *args: None)
    monkeypatch.setattr(email_task_weekly, "_lock_digest_user", lambda *args, **kwargs: user)
    monkeypatch.setattr(email_task_weekly, "weekly_digest_enabled", lambda _preferences: True)
    monkeypatch.setattr(
        email_task_weekly,
        "get_or_create_weekly_digest_delivery",
        lambda *args, **kwargs: delivery,
    )

    def _claim(*args, **kwargs):
        delivery.state = "dispatching"
        delivery.recipient_email = user.email
        return claim

    monkeypatch.setattr(email_task_weekly, "claim_weekly_digest_dispatch", _claim)
    monkeypatch.setattr(
        email_task_weekly,
        "lock_weekly_digest_delivery",
        lambda *args, **kwargs: delivery,
    )
    monkeypatch.setattr(email_task_weekly, "risk_ratings_restricted_for_role", lambda _role: False)
    monkeypatch.setattr(
        email_task_weekly,
        "build_weekly_digest_send_kwargs",
        lambda **kwargs: {"recipient": kwargs["user"].email},
    )
    monkeypatch.setattr(
        email_task_weekly,
        "_submit_weekly_digest",
        lambda *, payload: DeliverySubmissionResult(
            status="accepted",
            message_id="provider-message",
        ),
    )
    monkeypatch.setattr(email_task_weekly, "record_weekly_digest_submission", record_submission)

    outcome = email_task_weekly._process_digest_recipient(
        db,
        listed_user=user,
        period_start=delivery.period_start,
        period_end=delivery.period_end,
        analyses_count=2,
        alerts_count=1,
        top_risks=[],
    )

    assert outcome == "sent"
    record_submission.assert_called_once()
    assert record_submission.call_args.kwargs["result"].message_id == "provider-message"
    assert db.rollback.call_count == 0


def test_process_recipient_records_ambiguous_state_when_provider_raises(monkeypatch):
    user = _user()
    delivery = _delivery(user=user)
    db = SimpleNamespace(commit=MagicMock(), rollback=MagicMock())
    claim = WeeklyDigestDispatchClaim(
        delivery_id=delivery.id,
        submission_id=delivery.submission_id,
        unsubscribe_token="du1." + "t" * 86,
    )
    record_exception = MagicMock()

    monkeypatch.setattr(email_task_weekly, "bind_org_to_sync_session", lambda *args: None)
    monkeypatch.setattr(email_task_weekly, "_lock_digest_user", lambda *args, **kwargs: user)
    monkeypatch.setattr(email_task_weekly, "weekly_digest_enabled", lambda _preferences: True)
    monkeypatch.setattr(
        email_task_weekly,
        "get_or_create_weekly_digest_delivery",
        lambda *args, **kwargs: delivery,
    )

    def _claim(*args, **kwargs):
        delivery.state = "dispatching"
        delivery.recipient_email = user.email
        return claim

    monkeypatch.setattr(email_task_weekly, "claim_weekly_digest_dispatch", _claim)
    monkeypatch.setattr(
        email_task_weekly,
        "lock_weekly_digest_delivery",
        lambda *args, **kwargs: delivery,
    )
    monkeypatch.setattr(email_task_weekly, "risk_ratings_restricted_for_role", lambda _role: False)
    monkeypatch.setattr(
        email_task_weekly,
        "build_weekly_digest_send_kwargs",
        lambda **_kwargs: {},
    )
    monkeypatch.setattr(
        email_task_weekly,
        "_submit_weekly_digest",
        MagicMock(side_effect=RuntimeError("provider timeout")),
    )
    monkeypatch.setattr(
        email_task_weekly,
        "record_weekly_digest_submission_exception",
        record_exception,
    )

    outcome = email_task_weekly._process_digest_recipient(
        db,
        listed_user=user,
        period_start=delivery.period_start,
        period_end=delivery.period_end,
        analyses_count=1,
        alerts_count=0,
        top_risks=[],
    )

    assert outcome == "pending"
    record_exception.assert_called_once()
    assert db.rollback.call_count == 0


@pytest.mark.parametrize(
    ("current_user", "delivery_state", "digest_enabled", "expected"),
    [
        (None, "prepared", True, "skipped"),
        (_user(membership_active=False), "prepared", True, "skipped"),
        (_user(), "prepared", False, "skipped"),
        (_user(), "provider_accepted", True, "already_sent"),
        (_user(), "rejected", True, "terminal"),
    ],
)
def test_process_recipient_handles_authority_and_terminal_states(
    monkeypatch,
    current_user,
    delivery_state,
    digest_enabled,
    expected,
):
    listed_user = _user()
    if current_user is not None:
        current_user.id = listed_user.id
        current_user.org_id = listed_user.org_id
    delivery = _delivery(user=listed_user, state=delivery_state)
    db = SimpleNamespace(commit=MagicMock(), rollback=MagicMock())

    monkeypatch.setattr(email_task_weekly, "bind_org_to_sync_session", lambda *args: None)
    monkeypatch.setattr(
        email_task_weekly,
        "_lock_digest_user",
        lambda *args, **kwargs: current_user,
    )
    monkeypatch.setattr(
        email_task_weekly,
        "weekly_digest_enabled",
        lambda _preferences: digest_enabled,
    )
    monkeypatch.setattr(
        email_task_weekly,
        "get_or_create_weekly_digest_delivery",
        lambda *args, **kwargs: delivery,
    )

    outcome = email_task_weekly._process_digest_recipient(
        db,
        listed_user=listed_user,
        period_start=delivery.period_start,
        period_end=delivery.period_end,
        analyses_count=1,
        alerts_count=0,
        top_risks=[],
    )

    assert outcome == expected
