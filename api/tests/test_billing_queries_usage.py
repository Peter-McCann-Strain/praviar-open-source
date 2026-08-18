from __future__ import annotations

import uuid
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import make_mock_db

from api.db.models import OrgPlan
from api.services.billing_queries import (
    AnalysisCreditReservation,
    check_usage_limit,
    check_usage_limit_for_org,
    consume_analysis_credits,
    get_consumed_analysis_credit_count,
    record_usage_event,
    refund_analysis_credit_reservation,
    refund_cancelled_analysis_credits,
)


def _make_org(**kw: object) -> MagicMock:
    org = MagicMock()
    org.id = kw.get("id", uuid.uuid4())
    org.plan = kw.get("plan", OrgPlan.STARTER)
    org.max_analyses_per_month = kw.get("max_analyses_per_month", 8)
    org.subscription_status = kw.get("subscription_status", "active")
    org.billing_cycle_start = kw.get("billing_cycle_start")
    return org


@pytest.mark.asyncio
async def test_get_consumed_analysis_credit_count_returns_net_consumes() -> None:
    db = make_mock_db()
    result = MagicMock()
    result.scalar_one.return_value = -2
    db.execute = AsyncMock(return_value=result)

    assert await get_consumed_analysis_credit_count(db, uuid.uuid4(), None) == 2


@pytest.mark.asyncio
async def test_get_consumed_analysis_credit_count_nets_refunds_to_zero() -> None:
    db = make_mock_db()
    result = MagicMock()
    result.scalar_one.return_value = 0
    db.execute = AsyncMock(return_value=result)

    assert await get_consumed_analysis_credit_count(db, uuid.uuid4(), None) == 0


@pytest.mark.asyncio
async def test_get_consumed_analysis_credit_count_ignores_unmatched_refund_credit() -> None:
    db = make_mock_db()
    result = MagicMock()
    result.scalar_one.return_value = 1
    db.execute = AsyncMock(return_value=result)

    assert await get_consumed_analysis_credit_count(db, uuid.uuid4(), None) == 0


@pytest.mark.asyncio
async def test_check_usage_limit_for_org_uses_plan_cap_when_missing() -> None:
    db = make_mock_db()
    org = _make_org(max_analyses_per_month=None)
    get_monthly_usage_fn = AsyncMock(return_value=5)

    assert await check_usage_limit_for_org(
        db,
        org=org,
        get_monthly_usage_fn=get_monthly_usage_fn,
        plan_limit_for_fn=lambda plan_key: 8 if plan_key == "starter" else 0,
    ) == (True, 5, 8)


@pytest.mark.asyncio
async def test_check_usage_limit_for_org_scopes_usage_and_credits_to_same_fallback_period() -> None:
    db = make_mock_db()
    org = _make_org(
        plan=OrgPlan.FREE,
        max_analyses_per_month=2,
        billing_cycle_start=None,
    )
    get_monthly_usage_fn = AsyncMock(return_value=1)
    get_consumed_credit_count_fn = AsyncMock(return_value=0)

    result = await check_usage_limit_for_org(
        db,
        org=org,
        get_monthly_usage_fn=get_monthly_usage_fn,
        plan_limit_for_fn=lambda _plan_key: 2,
        requested_analyses=2,
        get_credit_balance_fn=AsyncMock(return_value=0),
        get_consumed_credit_count_fn=get_consumed_credit_count_fn,
        consume_credits_fn=AsyncMock(),
    )

    assert result == (False, 1, 2)
    usage_period = get_monthly_usage_fn.await_args.args[2]
    credit_period = get_consumed_credit_count_fn.await_args.args[2]
    assert usage_period == credit_period
    assert usage_period.tzinfo is UTC
    assert usage_period.day == 1
    assert usage_period.hour == usage_period.minute == usage_period.second == 0


@pytest.mark.asyncio
async def test_check_usage_limit_for_org_uses_included_allowance_before_credits() -> None:
    db = make_mock_db()
    org = _make_org(max_analyses_per_month=8)
    get_monthly_usage_fn = AsyncMock(return_value=7)
    get_credit_balance_fn = AsyncMock(return_value=3)
    get_consumed_credit_count_fn = AsyncMock(return_value=0)
    consume_credits_fn = AsyncMock()

    assert await check_usage_limit_for_org(
        db,
        org=org,
        get_monthly_usage_fn=get_monthly_usage_fn,
        plan_limit_for_fn=lambda plan_key: 8 if plan_key == "starter" else 0,
        get_credit_balance_fn=get_credit_balance_fn,
        get_consumed_credit_count_fn=get_consumed_credit_count_fn,
        consume_credits_fn=consume_credits_fn,
    ) == (True, 7, 11)
    consume_credits_fn.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_usage_limit_for_org_reserves_credits_after_plan_allowance() -> None:
    db = make_mock_db()
    org = _make_org(max_analyses_per_month=8)
    get_monthly_usage_fn = AsyncMock(return_value=8)
    get_credit_balance_fn = AsyncMock(return_value=3)
    get_consumed_credit_count_fn = AsyncMock(return_value=0)
    consume_credits_fn = AsyncMock()

    assert await check_usage_limit_for_org(
        db,
        org=org,
        get_monthly_usage_fn=get_monthly_usage_fn,
        plan_limit_for_fn=lambda plan_key: 8 if plan_key == "starter" else 0,
        get_credit_balance_fn=get_credit_balance_fn,
        get_consumed_credit_count_fn=get_consumed_credit_count_fn,
        consume_credits_fn=consume_credits_fn,
    ) == (True, 8, 11)
    consume_credits_fn.assert_awaited_once()
    assert consume_credits_fn.await_args.kwargs["credits"] == 1


@pytest.mark.asyncio
async def test_check_usage_limit_for_org_records_credit_reservation_metadata() -> None:
    db = make_mock_db()
    org = _make_org(max_analyses_per_month=8)
    get_monthly_usage_fn = AsyncMock(return_value=8)
    get_credit_balance_fn = AsyncMock(return_value=3)
    get_consumed_credit_count_fn = AsyncMock(return_value=0)
    consume_credits_fn = AsyncMock()
    reservations: list[AnalysisCreditReservation] = []
    analysis_id = uuid.uuid4()

    assert await check_usage_limit_for_org(
        db,
        org=org,
        get_monthly_usage_fn=get_monthly_usage_fn,
        plan_limit_for_fn=lambda plan_key: 8 if plan_key == "starter" else 0,
        get_credit_balance_fn=get_credit_balance_fn,
        get_consumed_credit_count_fn=get_consumed_credit_count_fn,
        consume_credits_fn=consume_credits_fn,
        reservation_id="credit-reservation-1",
        reservation_details={"source": "analysis.create"},
        credit_reservations=reservations,
        analysis_id=analysis_id,
    ) == (True, 8, 11)

    consume_credits_fn.assert_awaited_once()
    assert consume_credits_fn.await_args.kwargs["reservation_id"] == "credit-reservation-1"
    assert consume_credits_fn.await_args.kwargs["analysis_id"] == analysis_id
    assert consume_credits_fn.await_args.kwargs["details"] == {
        "requested_analyses": 1,
        "included_remaining": 0,
        "source": "analysis.create",
    }
    assert reservations == [
        AnalysisCreditReservation(
            org_id=org.id,
            reservation_id="credit-reservation-1",
            credits=1,
        )
    ]


@pytest.mark.asyncio
async def test_check_usage_limit_for_org_can_defer_credit_insert_under_org_lock() -> None:
    db = make_mock_db()
    org = _make_org(max_analyses_per_month=8)
    consume_credits_fn = AsyncMock()
    reservations: list[AnalysisCreditReservation] = []

    result = await check_usage_limit_for_org(
        db,
        org=org,
        get_monthly_usage_fn=AsyncMock(return_value=8),
        plan_limit_for_fn=lambda plan_key: 8 if plan_key == "starter" else 0,
        get_credit_balance_fn=AsyncMock(return_value=1),
        get_consumed_credit_count_fn=AsyncMock(return_value=0),
        consume_credits_fn=consume_credits_fn,
        reservation_id="deferred-credit-reservation-1",
        reservation_details={"source": "analysis.create"},
        credit_reservations=reservations,
        analysis_id=uuid.uuid4(),
        defer_credit_consumption=True,
    )

    assert result == (True, 8, 9)
    consume_credits_fn.assert_not_awaited()
    assert reservations == [
        AnalysisCreditReservation(
            org_id=org.id,
            reservation_id="deferred-credit-reservation-1",
            credits=1,
        )
    ]


@pytest.mark.asyncio
async def test_refund_analysis_credit_reservation_appends_compensating_entry() -> None:
    db = make_mock_db()
    existing_result = MagicMock()
    existing_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=existing_result)
    org_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    reservation = AnalysisCreditReservation(
        org_id=org_id,
        reservation_id="credit-reservation-1",
        credits=1,
    )

    await refund_analysis_credit_reservation(
        db,
        org_id=org_id,
        reservation=reservation,
        analysis_id=analysis_id,
        details={"reason": "pipeline_dispatch_failed"},
    )

    ledger = db.add.call_args.args[0]
    assert ledger.org_id == org_id
    assert ledger.analysis_id == analysis_id
    assert ledger.kind == "refund"
    assert ledger.credits_delta == 1
    assert ledger.details == {
        "reservation_id": "credit-reservation-1",
        "reason": "pipeline_dispatch_failed",
    }
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_refund_cancelled_analysis_credits_replays_consumption_reservation() -> None:
    db = make_mock_db()
    org_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    consumption = MagicMock(
        org_id=org_id,
        analysis_id=analysis_id,
        kind="consume",
        credits_delta=-2,
        details={"reservation_id": "credit-reservation-1"},
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [consumption]
    db.execute = AsyncMock(return_value=result)

    with patch(
        "api.services.billing_queries.refund_analysis_credit_reservation",
        new=AsyncMock(),
    ) as refund:
        refunded = await refund_cancelled_analysis_credits(
            db,
            org_id=org_id,
            analysis_id=analysis_id,
        )

    assert refunded == 2
    refund.assert_awaited_once_with(
        db,
        org_id=org_id,
        reservation=AnalysisCreditReservation(
            org_id=org_id,
            reservation_id="credit-reservation-1",
            credits=2,
        ),
        analysis_id=analysis_id,
        details={"reason": "analysis_cancelled", "source": "analysis.delete"},
    )


@pytest.mark.asyncio
async def test_refund_cancelled_analysis_credits_fails_closed_without_reservation() -> None:
    db = make_mock_db()
    consumption = MagicMock(credits_delta=-1, details={})
    result = MagicMock()
    result.scalars.return_value.all.return_value = [consumption]
    db.execute = AsyncMock(return_value=result)

    with pytest.raises(RuntimeError, match="missing its reservation identifier"):
        await refund_cancelled_analysis_credits(
            db,
            org_id=uuid.uuid4(),
            analysis_id=uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_consume_credit_reservation_is_idempotent_before_insert() -> None:
    db = make_mock_db()
    existing_result = MagicMock()
    existing_result.scalar_one_or_none.return_value = uuid.uuid4()
    db.execute = AsyncMock(return_value=existing_result)

    await consume_analysis_credits(
        db,
        org_id=uuid.uuid4(),
        credits=1,
        reservation_id="credit-reservation-1",
    )

    db.add.assert_not_called()
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_refund_credit_reservation_is_idempotent_before_insert() -> None:
    db = make_mock_db()
    existing_result = MagicMock()
    existing_result.scalar_one_or_none.return_value = uuid.uuid4()
    db.execute = AsyncMock(return_value=existing_result)
    org_id = uuid.uuid4()

    await refund_analysis_credit_reservation(
        db,
        org_id=org_id,
        reservation=AnalysisCreditReservation(
            org_id=org_id,
            reservation_id="credit-reservation-1",
            credits=1,
        ),
    )

    db.add.assert_not_called()
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_usage_limit_for_org_rejects_when_no_plan_or_credit_capacity() -> None:
    db = make_mock_db()
    org = _make_org(max_analyses_per_month=8)
    get_monthly_usage_fn = AsyncMock(return_value=8)

    assert await check_usage_limit_for_org(
        db,
        org=org,
        get_monthly_usage_fn=get_monthly_usage_fn,
        plan_limit_for_fn=lambda plan_key: 8 if plan_key == "starter" else 0,
        get_credit_balance_fn=AsyncMock(return_value=0),
        get_consumed_credit_count_fn=AsyncMock(return_value=0),
        consume_credits_fn=AsyncMock(),
    ) == (False, 8, 8)


@pytest.mark.asyncio
async def test_lapsed_enforcement_uses_same_capacity_as_read_models() -> None:
    db = make_mock_db()
    org = _make_org(
        plan=OrgPlan.PRO,
        max_analyses_per_month=20,
        subscription_status="canceled",
    )
    consume_credits_fn = AsyncMock()

    result = await check_usage_limit_for_org(
        db,
        org=org,
        get_monthly_usage_fn=AsyncMock(return_value=5),
        plan_limit_for_fn=lambda plan: {"free": 3, "pro": 20}[plan],
        get_credit_balance_fn=AsyncMock(return_value=2),
        get_consumed_credit_count_fn=AsyncMock(return_value=0),
        consume_credits_fn=consume_credits_fn,
    )

    assert result == (True, 5, 7)
    consume_credits_fn.assert_awaited_once()
    assert consume_credits_fn.await_args.kwargs["credits"] == 1


@pytest.mark.asyncio
async def test_record_usage_event_logs_usage_event() -> None:
    db = make_mock_db()

    with patch("api.services.billing_queries.logger") as logger:
        await record_usage_event(db, uuid.uuid4(), uuid.uuid4())

    logger.info.assert_called_once()


@pytest.mark.asyncio
async def test_check_usage_limit_returns_zero_tuple_for_missing_org() -> None:
    db = make_mock_db()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)

    with patch("api.services.billing_queries.logger") as logger:
        assert await check_usage_limit(db, uuid.uuid4()) == (False, 0, 0)

    logger.error.assert_called_once()
