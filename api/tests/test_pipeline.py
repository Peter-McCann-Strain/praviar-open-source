"""Tests for pipeline SSE routes."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from api.errors import APIError


async def _yield_once(value: str):
    yield value


class TestPipelineRoutes:
    @pytest.mark.asyncio
    async def test_stream_pipeline_returns_404_when_analysis_missing(self, scientist_client):
        client, _db = scientist_client
        analysis_id = uuid.uuid4()

        with patch(
            "api.routes.pipeline._load_pipeline_replay",
            new=AsyncMock(side_effect=APIError(404, "Not Found", "Analysis not found")),
        ):
            response = await client.get(f"/api/v1/analyses/{analysis_id}/stream")

        assert response.status_code == 404
        assert response.json()["detail"] == "Analysis not found"

    @pytest.mark.asyncio
    async def test_stream_pipeline_replays_and_streams_live_events(self, scientist_client):
        client, _db = scientist_client
        analysis_id = uuid.uuid4()

        with (
            patch(
                "api.routes.pipeline._load_pipeline_replay",
                new=AsyncMock(return_value=['data: {"type":"replay"}\n\n']),
            ),
            patch(
                "api.routes.pipeline._stream_pipeline_events",
                return_value=_yield_once('data: {"type":"completed"}\n\n'),
            ),
        ):
            async with client.stream("GET", f"/api/v1/analyses/{analysis_id}/stream") as response:
                body = await response.aread()

        assert response.status_code == 200
        assert body.decode("utf-8") == ('data: {"type":"replay"}\n\ndata: {"type":"completed"}\n\n')
