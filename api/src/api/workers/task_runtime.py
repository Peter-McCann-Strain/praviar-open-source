"""Runtime setup helpers for worker tasks."""

from __future__ import annotations

from dataclasses import dataclass

import redis
from sqlalchemy import Engine

from api.cache import redis_connection_kwargs


@dataclass(slots=True)
class PipelineTaskRuntime:
    settings: object
    redis_client: redis.Redis
    engine: Engine


def build_pipeline_runtime(
    *,
    get_settings_fn,
    redis_from_url,
    get_sync_engine_fn,
) -> PipelineTaskRuntime:
    settings = get_settings_fn()
    return PipelineTaskRuntime(
        settings=settings,
        redis_client=redis_from_url(settings.redis_url, **redis_connection_kwargs(settings)),
        engine=get_sync_engine_fn(),
    )
