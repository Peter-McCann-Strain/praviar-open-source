"""Tests for chat routes."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from conftest import bind_report_data, valid_report_data

from api.db.models import AnalysisStatus
from api.errors import APIError


class TestChatRoutes:
    @pytest.mark.asyncio
    async def test_chat_returns_503_without_api_key(self, scientist_client):
        client, _db = scientist_client

        with patch(
            "api.routes.chat.get_settings",
            return_value=SimpleNamespace(anthropic_api_key=""),
        ):
            response = await client.post(
                f"/api/v1/analyses/{uuid.uuid4()}/chat",
                json={"message": "Summarize the report"},
            )

        assert response.status_code == 503
        assert response.json()["detail"] == "Chat not available — Anthropic API key not configured"

    @pytest.mark.asyncio
    async def test_chat_returns_404_when_report_missing(self, scientist_client):
        client, _db = scientist_client
        analysis_id = uuid.uuid4()

        with (
            patch(
                "api.routes.chat.get_settings",
                return_value=SimpleNamespace(
                    anthropic_api_key="test-key",
                    chat_model="claude-sonnet-4-6",
                    chat_max_tokens=2048,
                ),
            ),
            patch(
                "api.routes.chat._get_analysis_report_for_chat",
                new=AsyncMock(side_effect=APIError(404, "Not Found", "Report not found")),
            ),
        ):
            response = await client.post(
                f"/api/v1/analyses/{analysis_id}/chat",
                json={"message": "Summarize the report"},
            )

        assert response.status_code == 404
        assert response.json()["detail"] == "Report not found"

    @pytest.mark.asyncio
    async def test_chat_forbidden_for_client_role(self, client_role_client):
        client, _db = client_role_client

        with (
            patch(
                "api.routes.chat.get_settings",
                return_value=SimpleNamespace(
                    anthropic_api_key="test-key",
                    chat_model="claude-sonnet-4-6",
                    chat_max_tokens=2048,
                ),
            ),
            patch(
                "api.routes.chat._get_analysis_report_for_chat",
                new=AsyncMock(
                    return_value=MagicMock(
                        status=AnalysisStatus.COMPLETED,
                        report_data={"risk_summary": {}},
                    )
                ),
            ) as get_report,
        ):
            response = await client.post(
                f"/api/v1/analyses/{uuid.uuid4()}/chat",
                json={"message": "Summarize the report"},
            )

        assert response.status_code == 403
        assert response.json()["detail"] == "Clients can only view summaries"
        get_report.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_chat_filters_risk_context_for_non_attorney_when_required(
        self,
        scientist_client,
    ):
        client, _db = scientist_client
        raw_report = valid_report_data(
            risk_summary={
                "overall_risk": "medium",
                "blocking_patents_count": 0,
                "total_patents_analyzed": 1,
                "executive_summary": (
                    "Clearance decision: UNCLEAR. 0 blocking patents identified from 1 analyzed."
                ),
                "key_risks": ["claim coverage"],
            },
            action_items=["send legal opinion"],
        )
        filtered_report = {"risk_summary": {"executive_summary": "restricted"}}
        prepared = SimpleNamespace(
            conversation_id=str(uuid.uuid4()),
            policy=SimpleNamespace(
                trust_mode="explorer",
                capability_profile="report",
                opinion_readiness={},
            ),
            history=[],
        )

        async def events(**_kwargs):
            yield {"type": "done"}

        analysis_id = uuid.uuid4()
        bind_report_data(raw_report, analysis_id=analysis_id)

        with (
            patch(
                "api.routes.chat.get_settings",
                return_value=SimpleNamespace(
                    anthropic_api_key="test-key",
                    chat_model="claude-sonnet-4-6",
                    chat_max_tokens=2048,
                    require_attorney_role_for_risk_ratings=True,
                ),
            ),
            patch(
                "api.routes.chat._get_analysis_report_for_chat",
                new=AsyncMock(
                    return_value=MagicMock(
                        id=analysis_id,
                        org_id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
                        status=AnalysisStatus.COMPLETED,
                        report_data=raw_report,
                    )
                ),
            ),
            patch(
                "api.routes.chat._get_conversation_history",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "api.routes.chat._filter_risk_ratings",
                return_value=filtered_report,
            ) as filter_risk,
            patch(
                "api.routes.chat._prepare_chat_request",
                return_value=prepared,
            ) as prepare_chat,
            patch(
                "api.routes.chat._reserve_chat_budget",
                new=AsyncMock(return_value=SimpleNamespace(amount_microusd=1000)),
            ) as reserve_budget,
            patch("api.routes.chat._stream_chat_events", side_effect=events),
        ):
            response = await client.post(
                f"/api/v1/analyses/{analysis_id}/chat",
                json={"message": "Summarize the report"},
            )

        assert response.status_code == 200
        filter_risk.assert_called_once_with(raw_report)
        assert prepare_chat.call_args.kwargs["report_data"] == filtered_report
        reserve_budget.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_chat_rejects_non_completed_report_payload(self, scientist_client):
        client, _db = scientist_client
        analysis_id = uuid.uuid4()

        with (
            patch(
                "api.routes.chat.get_settings",
                return_value=SimpleNamespace(
                    anthropic_api_key="test-key",
                    chat_model="claude-sonnet-4-6",
                    chat_max_tokens=2048,
                ),
            ),
            patch(
                "api.routes.chat._get_analysis_report_for_chat",
                new=AsyncMock(
                    return_value=MagicMock(
                        status=AnalysisStatus.RUNNING,
                        report_data={"risk_summary": {"overall_risk": "high"}},
                    )
                ),
            ),
            patch(
                "api.routes.chat._get_conversation_history",
                new=AsyncMock(return_value=[]),
            ) as get_history,
            patch("api.routes.chat._prepare_chat_request") as prepare_chat,
        ):
            response = await client.post(
                f"/api/v1/analyses/{analysis_id}/chat",
                json={"message": "Summarize the report"},
            )

        assert response.status_code == 404
        assert response.json()["detail"] == "Report not found"
        get_history.assert_not_awaited()
        prepare_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_chat_rejects_unissued_conversation_labels(self, scientist_client):
        client, _db = scientist_client
        analysis_id = uuid.uuid4()

        with (
            patch(
                "api.routes.chat.get_settings",
                return_value=SimpleNamespace(
                    anthropic_api_key="test-key",
                    chat_model="claude-sonnet-4-6",
                    chat_max_tokens=2048,
                ),
            ),
            patch(
                "api.routes.chat._get_analysis_report_for_chat",
                new=AsyncMock(
                    return_value=MagicMock(
                        status=AnalysisStatus.COMPLETED,
                        report_data={"ok": True},
                    )
                ),
            ) as get_report,
            patch(
                "api.routes.chat._get_conversation_history",
                new=AsyncMock(return_value=[]),
            ) as get_history,
        ):
            response = await client.post(
                f"/api/v1/analyses/{analysis_id}/chat",
                json={
                    "message": "Summarize the report",
                    "conversation_id": "conversation-123",
                },
            )

        assert response.status_code == 400
        get_report.assert_not_awaited()
        get_history.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_chat_rejects_empty_message(self, scientist_client):
        client, _db = scientist_client

        response = await client.post(
            f"/api/v1/analyses/{uuid.uuid4()}/chat",
            json={"message": ""},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_chat_rejects_oversized_message(self, scientist_client):
        client, _db = scientist_client

        response = await client.post(
            f"/api/v1/analyses/{uuid.uuid4()}/chat",
            json={"message": "x" * 8001},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_clear_chat_history_delegates_to_services(self, scientist_client):
        client, _db = scientist_client
        analysis_id = uuid.uuid4()
        conversation_id = uuid.uuid4()

        with (
            patch(
                "api.routes.chat._get_analysis_report_for_chat",
                new=AsyncMock(
                    return_value=MagicMock(
                        status=AnalysisStatus.COMPLETED,
                        report_data={"ok": True},
                    )
                ),
            ) as get_report,
            patch(
                "api.routes.chat._clear_conversation_history",
                new=AsyncMock(),
            ) as clear_history,
        ):
            response = await client.delete(f"/api/v1/analyses/{analysis_id}/chat/{conversation_id}")

        assert response.status_code == 200
        assert response.json() == {
            "status": "cleared",
            "conversation_id": str(conversation_id),
        }
        get_report.assert_awaited_once()
        clear_history.assert_awaited_once_with(
            str(conversation_id),
            scope=ANY,
            settings=ANY,
        )

    @pytest.mark.asyncio
    async def test_clear_chat_history_forbidden_for_client_role(self, client_role_client):
        client, _db = client_role_client

        with patch(
            "api.routes.chat._get_analysis_report_for_chat",
            new=AsyncMock(
                return_value=MagicMock(
                    status=AnalysisStatus.COMPLETED,
                    report_data={"ok": True},
                )
            ),
        ) as get_report:
            response = await client.delete(f"/api/v1/analyses/{uuid.uuid4()}/chat/{uuid.uuid4()}")

        assert response.status_code == 403
        assert response.json()["detail"] == "Clients can only view summaries"
        get_report.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_clear_chat_history_rejects_unissued_conversation_labels(
        self,
        scientist_client,
    ):
        client, _db = scientist_client
        analysis_id = uuid.uuid4()

        with (
            patch(
                "api.routes.chat._get_analysis_report_for_chat",
                new=AsyncMock(
                    return_value=MagicMock(
                        status=AnalysisStatus.COMPLETED,
                        report_data={"ok": True},
                    )
                ),
            ),
            patch(
                "api.routes.chat._clear_conversation_history",
                new=AsyncMock(),
            ) as clear_history,
        ):
            response = await client.delete(f"/api/v1/analyses/{analysis_id}/chat/conversation-123")

        assert response.status_code == 400
        clear_history.assert_not_awaited()
