"""SSE streaming for pipeline progress."""

import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from api.cache import redis_connection_kwargs
from api.config import get_settings
from api.deps import CurrentUser, DBSession
from api.services.pipeline_stream import (
    load_pipeline_replay as _load_pipeline_replay,
)
from api.services.pipeline_stream import (
    stream_pipeline_events as _stream_pipeline_events,
)

router = APIRouter()


@router.get("/analyses/{analysis_id}/stream")
async def stream_pipeline(
    analysis_id: uuid.UUID,
    user: CurrentUser,
    db: DBSession,
) -> StreamingResponse:
    """SSE endpoint for real-time pipeline progress.

    1. Replay all existing events from the DB (catch-up on reconnect)
    2. Subscribe to Redis PubSub for new events
    3. Stream until pipeline completes or client disconnects
    """
    replayed = await _load_pipeline_replay(db, analysis_id=analysis_id, org_id=user.org_id)
    settings = get_settings()

    async def event_generator():
        for data in replayed:
            yield data
        async for data in _stream_pipeline_events(
            analysis_id,
            redis_url=settings.redis_url,
            max_stream_seconds=settings.sse_max_stream_seconds,
            subscription_timeout=settings.sse_subscription_timeout,
            redis_connection_kwargs=redis_connection_kwargs(settings),
        ):
            yield data

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
