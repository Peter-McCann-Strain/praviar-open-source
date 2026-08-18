from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.errors import APIError
from api.services.blocking_sdk import BlockingSDKCallTimeoutError
from api.services.offboarding import (
    ClaimedUseErasureAuthorization,
    execute_org_erasure,
    process_pending_erasures_async,
)


def _make_org(
    *,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
) -> SimpleNamespace:
    org_id = uuid.uuid4()
    return SimpleNamespace(
        id=org_id,
        deletion_status=None,
        deletion_scheduled_at=None,
        name="Example",
        slug="example",
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        offboarding_billing_cancellation_status=None,
        offboarding_stripe_subscription_id=None,
        offboarding_billing_cancellation_attempts=0,
        offboarding_billing_last_attempt_at=None,
        offboarding_billing_confirmed_at=None,
        offboarding_billing_last_error_code=None,
    )


def _make_db(org: SimpleNamespace) -> AsyncMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = org
    db = AsyncMock()
    db.execute.return_value = result
    return db


class _SessionContext:
    def __init__(self, session: AsyncMock) -> None:
        self.session = session

    async def __aenter__(self) -> AsyncMock:
        return self.session

    async def __aexit__(self, *_args: object) -> None:
        return None


@pytest.mark.asyncio
async def test_org_erasure_redacts_credit_capacity_request_snapshots():
    org = _make_org()
    org_id = org.id
    db = _make_db(org)

    with patch(
        "api.services.offboarding.write_audit_log",
        new=AsyncMock(),
    ):
        await execute_org_erasure(
            db,
            org_id=org_id,
            executed_by_user_id=uuid.uuid4(),
            executed_by_email="admin@example.com",
        )

    sql_statements = [str(call.args[0]) for call in db.execute.await_args_list if call.args]
    credit_redaction = next(
        statement for statement in sql_statements if "UPDATE credit_capacity_requests" in statement
    )
    assert "requester_name = '[ERASED]'" in credit_redaction
    assert "WHEN status = 'declined' THEN '[ERASED]'" in credit_redaction
    assert "ELSE NULL END" in credit_redaction
    assert any(
        "DELETE FROM organization_compounds WHERE org_id =" in statement
        for statement in sql_statements
    )
    assert any(
        "DELETE FROM weekly_digest_deliveries WHERE org_id =" in statement
        for statement in sql_statements
    )
    analysis_redaction = next(
        call.args[0]
        for call in db.execute.await_args_list
        if call.args
        and "UPDATE analyses SET" in str(call.args[0])
        and "compound_input" in str(call.args[0])
    )
    redaction_values = {
        column.key: expression.value for column, expression in analysis_redaction._values.items()
    }
    assert redaction_values["compound_input"] == "[ERASED]"
    assert redaction_values["input_type"] == "name"
    assert redaction_values["submitted_identity_confirmed"] is False
    assert redaction_values["submitted_identity_value"] is None
    assert org.offboarding_billing_cancellation_status == "not_required"
    assert org.offboarding_billing_confirmed_at is not None
    assert db.commit.await_count == 3


@pytest.mark.asyncio
async def test_org_erasure_explicitly_authorizes_claimed_use_receipt_deletion():
    org = _make_org()
    db = _make_db(org)
    actor_id = uuid.uuid4()
    authorization = ClaimedUseErasureAuthorization(
        authorization_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        org_id=org.id,
        actor_kind="platform_superadmin",
        actor_user_id=actor_id,
        actor_email="admin@example.com",
        authorized_at=datetime.now(UTC),
    )
    settings = SimpleNamespace(
        app_env="test",
        platform_admin_user_ids=[actor_id],
        gcs_bucket_name="",
        gcp_project_id="",
        export_dir="/tmp/praviar-exports",
    )

    with (
        patch("api.services.offboarding.get_settings", return_value=settings),
        patch(
            "api.services.offboarding.write_audit_log",
            new=AsyncMock(),
        ) as audit,
    ):
        await execute_org_erasure(
            db,
            org_id=org.id,
            authorization=authorization,
            use_database_boundary=True,
        )

    audit_actions = [call.kwargs["action"] for call in audit.await_args_list]
    assert audit_actions.index("org.report_archives_deleted") < audit_actions.index(
        "org.claimed_use_receipts_erasure_authorized"
    )
    assert audit_actions.index("org.claimed_use_receipts_erasure_authorized") < audit_actions.index(
        "org.data_erased"
    )

    statements = [call.args[0] for call in db.execute.await_args_list if call.args]
    assert any("public.erase_claimed_use_receipts" in str(statement) for statement in statements)
    assert not any(
        "app.claimed_use_receipt_erasure_org_id" in str(statement) for statement in statements
    )
    authorization_audit = next(
        call
        for call in audit.await_args_list
        if call.kwargs["action"] == "org.claimed_use_receipts_erasure_authorized"
    )
    assert authorization_audit.kwargs["details"]["authorization_id"] == str(
        authorization.authorization_id
    )


@pytest.mark.asyncio
async def test_org_erasure_cancels_subscription_before_terminal_erasure():
    org = _make_org(
        stripe_customer_id="cus_world_class",
        stripe_subscription_id="sub_world_class",
    )
    db = _make_db(org)
    cancelled = SimpleNamespace(status="canceled")

    with (
        patch(
            "api.services.blocking_sdk.run_blocking_sdk_call",
            new=AsyncMock(return_value=cancelled),
        ) as cancel_call,
        patch("api.services.offboarding.write_audit_log", new=AsyncMock()),
    ):
        result = await execute_org_erasure(
            db,
            org_id=org.id,
            executed_by_user_id=uuid.uuid4(),
            executed_by_email="admin@example.com",
        )

    assert result["deletion_status"] == "erased"
    assert org.deletion_status == "erased"
    assert org.offboarding_billing_cancellation_status == "confirmed"
    assert org.offboarding_billing_confirmed_at is not None
    assert org.stripe_customer_id is None
    assert org.stripe_subscription_id is None
    assert org.offboarding_stripe_subscription_id is None
    assert org.offboarding_billing_cancellation_attempts == 1
    assert db.commit.await_count == 4
    cancel_call.assert_awaited_once()
    _, fn, subscription_id = cancel_call.await_args.args
    assert callable(fn)
    assert subscription_id == "sub_world_class"
    assert cancel_call.await_args.kwargs["idempotency_key"].startswith(f"org-erasure-{org.id}-")


@pytest.mark.asyncio
async def test_org_erasure_stripe_failure_is_retryable_and_preserves_billing_locators():
    org = _make_org(
        stripe_customer_id="cus_still_active",
        stripe_subscription_id="sub_still_active",
    )
    db = _make_db(org)

    with (
        patch(
            "api.services.blocking_sdk.run_blocking_sdk_call",
            new=AsyncMock(side_effect=RuntimeError("provider unavailable")),
        ),
        pytest.raises(APIError) as raised,
    ):
        await execute_org_erasure(
            db,
            org_id=org.id,
            executed_by_user_id=uuid.uuid4(),
            executed_by_email="admin@example.com",
        )

    assert raised.value.status == 503
    assert raised.value.retry_after_seconds == 60
    assert org.deletion_status == "billing_cancellation_pending"
    assert org.offboarding_billing_cancellation_status == "retryable"
    assert org.offboarding_billing_last_error_code == "RuntimeError"
    assert org.stripe_customer_id == "cus_still_active"
    assert org.stripe_subscription_id == "sub_still_active"
    assert org.offboarding_stripe_subscription_id == "sub_still_active"
    assert org.name == "Example"
    assert org.slug == "example"
    assert db.commit.await_count == 2
    assert not any(
        "UPDATE analyses SET" in str(call.args[0])
        for call in db.execute.await_args_list
        if call.args
    )


@pytest.mark.asyncio
async def test_org_erasure_timeout_retries_same_subscription_idempotently_then_erases():
    org = _make_org(
        stripe_customer_id="cus_timeout",
        stripe_subscription_id="sub_timeout",
    )
    db = _make_db(org)
    cancel_call = AsyncMock(
        side_effect=[
            BlockingSDKCallTimeoutError("stripe timed out"),
            SimpleNamespace(status="canceled"),
        ]
    )

    with (
        patch(
            "api.services.blocking_sdk.run_blocking_sdk_call",
            new=cancel_call,
        ),
        patch("api.services.offboarding.write_audit_log", new=AsyncMock()),
    ):
        with pytest.raises(APIError) as first_attempt:
            await execute_org_erasure(
                db,
                org_id=org.id,
                executed_by_user_id=uuid.uuid4(),
                executed_by_email="admin@example.com",
            )

        assert first_attempt.value.status == 503
        assert org.deletion_status == "billing_cancellation_pending"
        assert org.stripe_subscription_id == "sub_timeout"
        assert org.offboarding_stripe_subscription_id == "sub_timeout"

        result = await execute_org_erasure(
            db,
            org_id=org.id,
            executed_by_user_id=uuid.uuid4(),
            executed_by_email="admin@example.com",
        )

    assert result["deletion_status"] == "erased"
    assert org.offboarding_billing_cancellation_attempts == 2
    assert org.offboarding_billing_cancellation_status == "confirmed"
    assert cancel_call.await_count == 2
    first_call, second_call = cancel_call.await_args_list
    assert first_call.args[2] == second_call.args[2] == "sub_timeout"
    assert first_call.kwargs["idempotency_key"] == second_call.kwargs["idempotency_key"]


@pytest.mark.asyncio
async def test_org_erasure_refuses_to_orphan_subscription_without_cancelled_confirmation():
    org = _make_org(
        stripe_customer_id="cus_active",
        stripe_subscription_id="sub_active",
    )
    db = _make_db(org)

    with (
        patch(
            "api.services.blocking_sdk.run_blocking_sdk_call",
            new=AsyncMock(return_value=SimpleNamespace(status="active")),
        ),
        pytest.raises(APIError) as raised,
    ):
        await execute_org_erasure(
            db,
            org_id=org.id,
            executed_by_user_id=uuid.uuid4(),
            executed_by_email="admin@example.com",
        )

    assert raised.value.status == 503
    assert org.deletion_status != "erased"
    assert org.offboarding_billing_cancellation_status == "retryable"
    assert org.offboarding_billing_last_error_code == "_StripeCancellationUnconfirmedError"
    assert org.stripe_customer_id == "cus_active"
    assert org.stripe_subscription_id == "sub_active"
    assert org.offboarding_stripe_subscription_id == "sub_active"
    assert db.commit.await_count == 2


@pytest.mark.asyncio
async def test_org_erasure_deletes_and_verifies_exact_tenant_gcs_prefix_before_erasure():
    org = _make_org()
    db = _make_db(org)
    actor_id = uuid.uuid4()
    storage = MagicMock()
    storage.delete_prefix.return_value = 3
    settings = SimpleNamespace(
        app_env="prod",
        gcs_bucket_name="praviar-reports",
        gcp_project_id="praviar-prod",
        export_dir="/tmp/praviar-exports",
        platform_admin_user_ids=[actor_id],
    )
    sdk_call = AsyncMock(return_value=3)

    with (
        patch("api.services.offboarding.get_settings", return_value=settings),
        patch(
            "api.services.object_storage.ObjectStorage",
            return_value=storage,
        ) as storage_class,
        patch(
            "api.services.offboarding.run_blocking_sdk_call",
            new=sdk_call,
        ),
        patch(
            "api.services.offboarding._consume_claimed_use_erasure_authorization",
            new=AsyncMock(return_value=0),
        ),
        patch("api.services.offboarding.write_audit_log", new=AsyncMock()) as audit,
    ):
        result = await execute_org_erasure(
            db,
            org_id=org.id,
            authorization=ClaimedUseErasureAuthorization(
                authorization_id=uuid.uuid4(),
                request_id=uuid.uuid4(),
                org_id=org.id,
                actor_kind="platform_superadmin",
                actor_user_id=actor_id,
                actor_email="admin@example.com",
                authorized_at=datetime.now(UTC),
            ),
            use_database_boundary=True,
        )

    assert result["deletion_status"] == "erased"
    storage_class.assert_called_once_with(
        bucket="praviar-reports",
        project="praviar-prod",
    )
    sdk_call.assert_awaited_once()
    assert sdk_call.await_args.args[:2] == (
        "gcs.org_exports.delete_prefix",
        storage.delete_prefix,
    )
    assert sdk_call.await_args.args[2] == f"exports/{org.id}/"
    assert sdk_call.await_args.kwargs["max_attempts"] == 1
    archive_audit = next(
        call
        for call in audit.await_args_list
        if call.kwargs["action"] == "org.report_archives_deleted"
    )
    assert archive_audit.kwargs["details"]["archive_target"] == (
        f"gs://praviar-reports/exports/{org.id}/"
    )
    assert archive_audit.kwargs["details"]["deleted_object_count"] == 3
    assert archive_audit.kwargs["details"]["verified_empty"] is True


@pytest.mark.asyncio
async def test_org_erasure_archive_failure_is_retryable_and_never_claims_terminal_erasure():
    org = _make_org()
    db = _make_db(org)
    actor_id = uuid.uuid4()
    settings = SimpleNamespace(
        app_env="prod",
        gcs_bucket_name="praviar-reports",
        gcp_project_id="praviar-prod",
        export_dir="/tmp/praviar-exports",
        platform_admin_user_ids=[actor_id],
    )

    with (
        patch("api.services.offboarding.get_settings", return_value=settings),
        patch("api.services.object_storage.ObjectStorage", return_value=MagicMock()),
        patch(
            "api.services.offboarding.run_blocking_sdk_call",
            new=AsyncMock(side_effect=RuntimeError("GCS unavailable")),
        ),
        patch("api.services.offboarding.write_audit_log", new=AsyncMock()),
        pytest.raises(APIError) as raised,
    ):
        await execute_org_erasure(
            db,
            org_id=org.id,
            authorization=ClaimedUseErasureAuthorization(
                authorization_id=uuid.uuid4(),
                request_id=uuid.uuid4(),
                org_id=org.id,
                actor_kind="platform_superadmin",
                actor_user_id=actor_id,
                actor_email="admin@example.com",
                authorized_at=datetime.now(UTC),
            ),
            use_database_boundary=True,
        )

    assert raised.value.status == 503
    assert raised.value.retry_after_seconds == 60
    assert org.deletion_status == "archive_deletion_pending"
    assert org.name == "Example"
    assert org.slug == "example"
    assert db.commit.await_count == 2
    assert not any(
        "compound_input" in str(call.args[0]) for call in db.execute.await_args_list if call.args
    )


@pytest.mark.asyncio
async def test_pending_erasure_sweep_retries_durable_billing_cancellation_state():
    org = _make_org(
        stripe_customer_id="cus_retry",
        stripe_subscription_id="sub_retry",
    )
    org.deletion_status = "billing_cancellation_pending"
    org.offboarding_billing_cancellation_status = "retryable"
    org.offboarding_stripe_subscription_id = "sub_retry"
    org.offboarding_billing_cancellation_attempts = 1
    org.offboarding_billing_last_error_code = "BlockingSDKCallTimeoutError"

    snapshot_result = MagicMock()
    snapshot_result.scalars.return_value.all.return_value = [org]
    snapshot_db = AsyncMock()
    snapshot_db.execute.return_value = snapshot_result

    recheck_result = MagicMock()
    recheck_result.scalar_one_or_none.return_value = org
    retry_db = AsyncMock()
    retry_db.execute.return_value = recheck_result

    session_factory = MagicMock(
        side_effect=[
            _SessionContext(snapshot_db),
            _SessionContext(retry_db),
        ]
    )
    execute_erasure = AsyncMock(return_value={"deletion_status": "erased"})

    with (
        patch("api.db.session.async_session_factory", session_factory),
        patch(
            "api.services.offboarding.execute_org_erasure",
            execute_erasure,
        ),
    ):
        result = await process_pending_erasures_async()

    assert result["erased_count"] == 1
    assert result["error_count"] == 0
    execute_erasure.assert_awaited_once_with(
        retry_db,
        org_id=org.id,
        authorization=None,
        use_database_boundary=False,
        executed_by_user_id=uuid.UUID(int=0),
        executed_by_email="system@praviar.internal",
    )
    snapshot_query = snapshot_db.execute.await_args.args[0]
    recheck_query = retry_db.execute.await_args.args[0]
    assert snapshot_query.compile().params["deletion_status_1"] == [
        "pending",
        "billing_cancellation_pending",
        "archive_deletion_pending",
    ]
    assert recheck_query.compile().params["deletion_status_1"] == [
        "pending",
        "billing_cancellation_pending",
        "archive_deletion_pending",
    ]


@pytest.mark.asyncio
async def test_org_erasure_does_not_duplicate_a_fresh_inflight_cancellation():
    org = _make_org(
        stripe_customer_id="cus_inflight",
        stripe_subscription_id="sub_inflight",
    )
    org.deletion_status = "billing_cancellation_pending"
    org.offboarding_billing_cancellation_status = "pending"
    org.offboarding_stripe_subscription_id = "sub_inflight"
    org.offboarding_billing_cancellation_attempts = 1
    org.offboarding_billing_last_attempt_at = datetime.now(UTC)
    db = _make_db(org)
    cancel_call = AsyncMock(return_value=SimpleNamespace(status="canceled"))

    with (
        patch(
            "api.services.blocking_sdk.run_blocking_sdk_call",
            new=cancel_call,
        ),
        pytest.raises(APIError) as raised,
    ):
        await execute_org_erasure(
            db,
            org_id=org.id,
            executed_by_user_id=uuid.uuid4(),
            executed_by_email="admin@example.com",
        )

    assert raised.value.status == 503
    assert raised.value.title == "Billing cancellation in progress"
    assert org.deletion_status == "billing_cancellation_pending"
    assert org.stripe_subscription_id == "sub_inflight"
    cancel_call.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_org_erasure_detects_replacement_subscription_before_local_erasure():
    org = _make_org(
        stripe_customer_id="cus_replacement",
        stripe_subscription_id="sub_original",
    )
    db = _make_db(org)

    async def _cancel_original(*_args: object, **_kwargs: object) -> SimpleNamespace:
        org.stripe_subscription_id = "sub_replacement"
        return SimpleNamespace(status="canceled")

    with (
        patch(
            "api.services.blocking_sdk.run_blocking_sdk_call",
            new=AsyncMock(side_effect=_cancel_original),
        ),
        pytest.raises(APIError) as raised,
    ):
        await execute_org_erasure(
            db,
            org_id=org.id,
            executed_by_user_id=uuid.uuid4(),
            executed_by_email="admin@example.com",
        )

    assert raised.value.status == 503
    assert org.deletion_status == "billing_cancellation_pending"
    assert org.offboarding_billing_cancellation_status is None
    assert org.offboarding_stripe_subscription_id is None
    assert org.stripe_customer_id == "cus_replacement"
    assert org.stripe_subscription_id == "sub_replacement"
    assert org.name == "Example"
    assert db.commit.await_count == 3
    assert not any(
        "UPDATE analyses SET" in str(call.args[0])
        for call in db.execute.await_args_list
        if call.args
    )
