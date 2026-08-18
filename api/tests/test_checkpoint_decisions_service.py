from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from api.errors import APIError
from api.schemas.checkpoint_decisions import CheckpointDecisionIn
from api.services.checkpoint_decisions import (
    fetch_checkpoint_decision,
    upsert_checkpoint_decision,
)


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4())


def _body(
    *, checkpoint_type: str = "analysis_review", decision: str = "approve", note: str = ""
) -> CheckpointDecisionIn:
    return CheckpointDecisionIn(
        checkpoint_type=checkpoint_type,
        decision=decision,
        note=note,
    )


@pytest.mark.asyncio
async def test_fetch_checkpoint_decision_returns_org_scoped_record() -> None:
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    stored = SimpleNamespace(checkpoint_id="analysis:review")
    result = MagicMock()
    result.scalar_one_or_none.return_value = stored
    db = AsyncMock()
    db.execute.return_value = result

    with patch(
        "api.services.checkpoint_decisions.assert_analysis_in_org",
        new=AsyncMock(),
    ) as assert_in_org:
        returned = await fetch_checkpoint_decision(
            db,
            analysis_id=analysis_id,
            org_id=org_id,
            checkpoint_id="analysis:review",
        )

    assert returned is stored
    assert_in_org.assert_awaited_once_with(db, analysis_id=analysis_id, org_id=org_id)
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_checkpoint_decision_raises_not_found_for_missing_record() -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute.return_value = result

    with (
        patch(
            "api.services.checkpoint_decisions.assert_analysis_in_org",
            new=AsyncMock(),
        ),
        pytest.raises(APIError) as exc_info,
    ):
        await fetch_checkpoint_decision(
            db,
            analysis_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            checkpoint_id="missing",
        )

    assert exc_info.value.status == 404
    assert exc_info.value.detail == "Checkpoint decision not found"


@pytest.mark.asyncio
async def test_upsert_checkpoint_decision_creates_and_flushes_new_record() -> None:
    user = _user()
    analysis_id = uuid.uuid4()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.add = MagicMock()
    db.execute.return_value = result

    with patch(
        "api.services.checkpoint_decisions.assert_analysis_in_org",
        new=AsyncMock(),
    ) as assert_in_org:
        created, action = await upsert_checkpoint_decision(
            db,
            analysis_id=analysis_id,
            checkpoint_id="analysis:review",
            user=user,
            body=_body(note="Reviewed evidence."),
        )

    assert action == "checkpoint_decision.create"
    assert created.analysis_id == analysis_id
    assert created.org_id == user.org_id
    assert created.reviewer_id == user.id
    assert created.note == "Reviewed evidence."
    assert_in_org.assert_awaited_once_with(db, analysis_id=analysis_id, org_id=user.org_id)
    db.add.assert_called_once_with(created)
    db.flush.assert_awaited_once_with()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_checkpoint_decision_updates_existing_mutable_record() -> None:
    user = _user()
    existing = SimpleNamespace(
        checkpoint_type="search_review",
        decision="approve",
        note="Initial review",
        reviewer_id=uuid.uuid4(),
        reviewed_at=None,
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing
    db = AsyncMock()
    db.execute.return_value = result

    with patch(
        "api.services.checkpoint_decisions.assert_analysis_in_org",
        new=AsyncMock(),
    ):
        returned, action = await upsert_checkpoint_decision(
            db,
            analysis_id=uuid.uuid4(),
            checkpoint_id="search:review",
            user=user,
            body=_body(
                checkpoint_type="analysis_review",
                decision="modify",
                note="Add register evidence.",
            ),
        )

    assert returned is existing
    assert action == "checkpoint_decision.update"
    assert existing.checkpoint_type == "analysis_review"
    assert existing.decision == "modify"
    assert existing.note == "Add register evidence."
    assert existing.reviewer_id == user.id
    assert existing.reviewed_at is not None
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_checkpoint_decision_recovers_from_concurrent_insert() -> None:
    user = _user()
    concurrent = SimpleNamespace(
        checkpoint_type="analysis_review",
        decision="approve",
        note="First writer",
        reviewer_id=uuid.uuid4(),
        reviewed_at=None,
    )
    absent = MagicMock()
    absent.scalar_one_or_none.return_value = None
    present = MagicMock()
    present.scalar_one_or_none.return_value = concurrent
    db = AsyncMock()
    db.add = MagicMock()
    db.execute.side_effect = [absent, present]
    db.flush.side_effect = IntegrityError("insert", {}, Exception("unique violation"))

    with patch(
        "api.services.checkpoint_decisions.assert_analysis_in_org",
        new=AsyncMock(),
    ):
        returned, action = await upsert_checkpoint_decision(
            db,
            analysis_id=uuid.uuid4(),
            checkpoint_id="analysis:review",
            user=user,
            body=_body(decision="modify", note="Second writer"),
        )

    assert returned is concurrent
    assert action == "checkpoint_decision.update"
    assert concurrent.decision == "modify"
    assert concurrent.note == "Second writer"
    db.rollback.assert_awaited_once_with()
    assert db.execute.await_count == 2


@pytest.mark.asyncio
async def test_upsert_checkpoint_decision_reraises_unresolved_insert_race() -> None:
    empty_result = MagicMock()
    empty_result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.add = MagicMock()
    db.execute.side_effect = [empty_result, empty_result]
    db.flush.side_effect = IntegrityError("insert", {}, Exception("unique violation"))

    with (
        patch(
            "api.services.checkpoint_decisions.assert_analysis_in_org",
            new=AsyncMock(),
        ),
        pytest.raises(IntegrityError),
    ):
        await upsert_checkpoint_decision(
            db,
            analysis_id=uuid.uuid4(),
            checkpoint_id="analysis:review",
            user=_user(),
            body=_body(),
        )

    db.rollback.assert_awaited_once_with()
