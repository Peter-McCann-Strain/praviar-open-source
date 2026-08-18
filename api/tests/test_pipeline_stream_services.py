"""Tests for pipeline stream service helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from api.errors import APIError
from api.services.pipeline_stream import load_pipeline_replay, stream_pipeline_events


@pytest.mark.asyncio
async def test_load_pipeline_replay_serializes_stored_events(mock_db):
    analysis = SimpleNamespace(id=uuid.uuid4())
    event = SimpleNamespace(
        step_number=2,
        step_name="search",
        event_type="progress",
        payload={"progress_pct": 42.0},
        created_at=datetime(2026, 4, 11, tzinfo=UTC),
    )
    analysis_result = SimpleNamespace(scalar_one_or_none=lambda: analysis)
    events_result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [event]))
    mock_db.execute.side_effect = [analysis_result, events_result]

    replay = await load_pipeline_replay(
        mock_db,
        analysis_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
    )

    assert replay == [
        'data: {"step": 2, "step_name": "search", "type": "progress", '
        '"payload": {"progress_pct": 42.0}, "timestamp": "2026-04-11T00:00:00+00:00"}\n\n'
    ]
    event_query = str(mock_db.execute.await_args_list[1].args[0])
    assert "JOIN analyses" in event_query
    assert "analyses.org_id" in event_query


@pytest.mark.asyncio
async def test_load_pipeline_replay_raises_when_analysis_missing(mock_db):
    mock_db.execute.return_value.scalar_one_or_none.return_value = None

    with pytest.raises(APIError) as exc_info:
        await load_pipeline_replay(
            mock_db,
            analysis_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
        )

    assert exc_info.value.status == 404


@pytest.mark.asyncio
async def test_stream_pipeline_events_yields_live_message_and_cleans_up():
    class FakePubSub:
        def __init__(self):
            self.subscribed = []
            self.unsubscribed = []

        async def subscribe(self, channel):
            self.subscribed.append(channel)

        async def unsubscribe(self, channel):
            self.unsubscribed.append(channel)

        async def get_message(self, **kwargs):
            return {"type": "message", "data": b'{"type":"completed"}'}

    class FakeRedis:
        def __init__(self):
            self.pubsub_obj = FakePubSub()
            self.closed = False

        def pubsub(self):
            return self.pubsub_obj

        async def aclose(self):
            self.closed = True

    redis = FakeRedis()
    analysis_id = uuid.uuid4()

    events = [
        event
        async for event in stream_pipeline_events(
            analysis_id,
            redis_url="redis://unused",
            max_stream_seconds=10,
            subscription_timeout=1.0,
            redis_client_factory=lambda _: redis,
            monotonic_fn=lambda: 0.0,
        )
    ]

    assert events == ['data: {"type":"completed"}\n\n']
    assert redis.pubsub_obj.subscribed == [f"analysis:{analysis_id}"]
    assert redis.pubsub_obj.unsubscribed == [f"analysis:{analysis_id}"]
    assert redis.closed is True


@pytest.mark.asyncio
async def test_stream_pipeline_events_passes_bounded_redis_connection_kwargs():
    class FakePubSub:
        async def subscribe(self, _channel):
            return None

        async def unsubscribe(self, _channel):
            return None

        async def get_message(self, **_kwargs):
            return {"type": "message", "data": b'{"type":"completed"}'}

    class FakeRedis:
        def pubsub(self):
            return FakePubSub()

        async def aclose(self):
            return None

    redis = FakeRedis()
    redis_client_factory = MagicMock(return_value=redis)

    events = [
        event
        async for event in stream_pipeline_events(
            uuid.uuid4(),
            redis_url="redis://unused",
            max_stream_seconds=10,
            subscription_timeout=1.0,
            redis_client_factory=redis_client_factory,
            redis_connection_kwargs={
                "socket_connect_timeout": 1.0,
                "socket_timeout": 2.0,
                "health_check_interval": 15,
            },
            monotonic_fn=lambda: 0.0,
        )
    ]

    assert events == ['data: {"type":"completed"}\n\n']
    redis_client_factory.assert_called_once_with(
        "redis://unused",
        socket_connect_timeout=1.0,
        socket_timeout=2.0,
        health_check_interval=15,
    )


@pytest.mark.asyncio
async def test_stream_pipeline_events_emits_heartbeat_then_timeout():
    class FakePubSub:
        def __init__(self):
            self.unsubscribed = []

        async def subscribe(self, channel):
            self.channel = channel

        async def unsubscribe(self, channel):
            self.unsubscribed.append(channel)

        async def get_message(self, **kwargs):
            return None

    class FakeRedis:
        def __init__(self):
            self.pubsub_obj = FakePubSub()
            self.closed = False

        def pubsub(self):
            return self.pubsub_obj

        async def aclose(self):
            self.closed = True

    redis = FakeRedis()
    ticks = iter([0.0, 0.0, 2.0, 2.0])
    analysis_id = uuid.uuid4()

    events = [
        event
        async for event in stream_pipeline_events(
            analysis_id,
            redis_url="redis://unused",
            max_stream_seconds=1,
            subscription_timeout=1.0,
            redis_client_factory=lambda _: redis,
            monotonic_fn=lambda: next(ticks),
        )
    ]

    assert events[0] == ": heartbeat\n\n"
    assert '"type": "timeout"' in events[1]
    assert redis.pubsub_obj.unsubscribed == [f"analysis:{analysis_id}"]
    assert redis.closed is True
