"""Business logic for pipeline SSE replay and live event streaming."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any, Protocol, cast

import redis.asyncio as aioredis
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import Analysis, PipelineEvent
from api.errors import APIError

logger = structlog.get_logger()


class RedisPubSub(Protocol):
    async def subscribe(self, channel: str) -> Any: ...
    async def get_message(self, *, ignore_subscribe_messages: bool, timeout: float) -> Any: ...
    async def unsubscribe(self, channel: str) -> Any: ...


class RedisStreamClient(Protocol):
    def pubsub(self) -> RedisPubSub: ...
    async def aclose(self) -> Any: ...


def _sse_data(payload: str) -> str:
    """Wrap a pre-serialized payload in an SSE data frame."""
    return f"data: {payload}\n\n"


def serialize_pipeline_event(event: PipelineEvent) -> str:
    """Serialize a stored pipeline event into an SSE data frame."""
    return _sse_data(
        json.dumps(
            {
                "step": event.step_number,
                "step_name": event.step_name,
                "type": event.event_type,
                "payload": event.payload,
                "timestamp": event.created_at.isoformat(),
            }
        )
    )


async def load_pipeline_replay(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
) -> list[str]:
    """Verify access and serialize historical pipeline events for replay."""
    analysis = (
        await db.execute(
            select(Analysis).where(Analysis.id == analysis_id, Analysis.org_id == org_id)
        )
    ).scalar_one_or_none()
    if not analysis:
        raise APIError(404, "Not Found", "Analysis not found")

    events = (
        (
            await db.execute(
                select(PipelineEvent)
                .join(Analysis, PipelineEvent.analysis_id == Analysis.id)
                .where(PipelineEvent.analysis_id == analysis_id)
                .where(Analysis.org_id == org_id)
                .order_by(PipelineEvent.created_at)
            )
        )
        .scalars()
        .all()
    )
    return [serialize_pipeline_event(event) for event in events]


async def stream_pipeline_events(
    analysis_id: uuid.UUID,
    *,
    redis_url: str,
    max_stream_seconds: int,
    subscription_timeout: float,
    redis_client_factory: Callable[..., Any] = aioredis.from_url,
    redis_connection_kwargs: Mapping[str, Any] | None = None,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> AsyncIterator[str]:
    """Yield live SSE frames from Redis until completion, timeout, or disconnect."""
    redis_client = cast(
        RedisStreamClient,
        redis_client_factory(redis_url, **dict(redis_connection_kwargs or {})),
    )
    pubsub = redis_client.pubsub()
    channel = f"analysis:{analysis_id}"
    await pubsub.subscribe(channel)
    stream_start = monotonic_fn()

    try:
        while True:
            if monotonic_fn() - stream_start > max_stream_seconds:
                logger.info(
                    "sse_stream_timeout",
                    analysis_id=str(analysis_id),
                    elapsed_s=round(monotonic_fn() - stream_start, 1),
                )
                yield _sse_data(
                    json.dumps(
                        {
                            "type": "timeout",
                            "payload": {"message": "Stream timed out"},
                        }
                    )
                )
                break

            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=subscription_timeout,
            )
            if message and message["type"] == "message":
                raw = message["data"]
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                yield _sse_data(raw)

                try:
                    event = json.loads(raw)
                    if event.get("type") in ("completed", "failed"):
                        break
                except json.JSONDecodeError as exc:
                    logger.warning(
                        "sse_json_decode_error",
                        raw=raw[:200],
                        error=str(exc),
                    )
            else:
                yield ": heartbeat\n\n"
    except GeneratorExit:
        logger.info(
            "sse_client_disconnected",
            analysis_id=str(analysis_id),
            elapsed_s=round(monotonic_fn() - stream_start, 1),
        )
    except Exception:
        logger.error("sse_stream_error", analysis_id=str(analysis_id), exc_info=True)
        raise
    finally:
        logger.debug("sse_cleanup_start", analysis_id=str(analysis_id))
        await pubsub.unsubscribe(channel)
        await redis_client.aclose()
        logger.debug("sse_cleanup_done", analysis_id=str(analysis_id))
