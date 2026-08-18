"""Business logic helpers for chat routes."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, cast

import anthropic
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.cache import get_redis
from api.config import APISettings, get_settings
from api.db.models import Analysis
from api.errors import APIError
from api.schemas.chat import ChatRequest
from api.services import chat_documents, chat_history, chat_stream
from api.services.no_paid_api import assert_paid_api_allowed
from api.services.report_access import require_completed_report_payload

logger = structlog.get_logger()

REPORT_CHAT_SYSTEM = chat_documents.REPORT_CHAT_SYSTEM
PATENT_CHAT_SYSTEM = chat_documents.PATENT_CHAT_SYSTEM
ChatConversationScope = chat_history.ChatConversationScope
PreparedChatRequest = chat_history.PreparedChatRequest
build_chat_policy = chat_history.build_chat_policy
issue_or_validate_conversation_id = chat_history.issue_or_validate_conversation_id


def build_report_document(report_data: dict) -> dict:
    """Structure the full FTO report as a citable Anthropic document."""
    return chat_documents.build_report_document(report_data)


def build_patent_document(patent_id: str, report_data: dict) -> dict:
    """Structure a single-patent view as a citable Anthropic document."""
    return chat_documents.build_patent_document(patent_id, report_data)


def extract_citations(content_blocks: list) -> list[dict]:
    """Extract citation metadata from Anthropic content blocks."""
    return chat_stream.extract_citations(content_blocks)


def prepare_chat_request(
    body: ChatRequest,
    *,
    conversation_id: str,
    history_scope: ChatConversationScope,
    report_data: dict,
    history: list[dict],
) -> PreparedChatRequest:
    """Build document context, prompt, message array, and updated user history."""
    return chat_history.prepare_chat_request(
        body,
        conversation_id=conversation_id,
        history_scope=history_scope,
        report_data=report_data,
        history=history,
        build_patent_document_fn=build_patent_document,
        build_report_document_fn=build_report_document,
        patent_system_prompt=PATENT_CHAT_SYSTEM,
        report_system_prompt=REPORT_CHAT_SYSTEM,
    )


def _extract_delta_citation(citation: object) -> dict:
    """Normalize a streaming citation delta into the public response shape."""
    return chat_stream.extract_delta_citation(citation)


def _build_usage(final_message: object) -> dict:
    """Normalize Anthropic usage metadata into the public response shape."""
    return chat_stream.build_usage(final_message)


def _append_assistant_message(
    history: list[dict],
    *,
    content: str,
    citations: list[dict],
) -> list[dict]:
    """Append the assistant reply to persisted conversation history."""
    return chat_stream.append_assistant_message(history, content=content, citations=citations)


async def get_analysis_report_for_chat(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
) -> Analysis:
    """Load an analysis, enforcing org access and report availability."""
    result = await db.execute(
        select(Analysis).where(
            Analysis.id == analysis_id,
            Analysis.org_id == org_id,
        )
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise APIError(404, "Not Found", "Report not found")
    require_completed_report_payload(analysis, detail="Report not found")
    return analysis


async def get_conversation_history(
    conversation_id: str,
    *,
    scope: ChatConversationScope,
    settings: APISettings | None = None,
) -> list[dict]:
    """Load conversation history from Redis."""
    runtime_settings = settings or get_settings()
    return await chat_history.get_conversation_history(
        conversation_id,
        scope=scope,
        settings=runtime_settings,
        get_redis_fn=get_redis,
    )


async def save_conversation_history(
    conversation_id: str,
    messages: list[dict],
    *,
    scope: ChatConversationScope,
    settings: APISettings | None = None,
) -> None:
    """Persist chat history with TTL and max-history trimming."""
    runtime_settings = settings or get_settings()
    await chat_history.save_conversation_history(
        conversation_id,
        messages,
        scope=scope,
        settings=runtime_settings,
        get_redis_fn=get_redis,
    )


async def clear_conversation_history(
    conversation_id: str,
    *,
    scope: ChatConversationScope,
    settings: APISettings | None = None,
) -> None:
    """Clear Redis chat history, failing closed in production."""
    runtime_settings = settings or get_settings()
    await chat_history.clear_conversation_history(
        conversation_id,
        scope=scope,
        settings=runtime_settings,
        get_redis_fn=get_redis,
    )


async def stream_chat_events(
    *,
    settings: APISettings,
    prepared: PreparedChatRequest,
    client_factory: Callable[..., chat_stream.ChatMessagesClient] | None = None,
    save_history_fn: Callable[..., Awaitable[None]] = save_conversation_history,
) -> AsyncIterator[dict[str, Any]]:
    """Yield normalized chat stream events and persist the completed assistant reply."""
    if client_factory is None:
        assert_paid_api_allowed("Anthropic chat")
    async for event in chat_stream.stream_chat_events(
        settings=settings,
        prepared=prepared,
        client_factory=client_factory
        or cast(Callable[..., chat_stream.ChatMessagesClient], anthropic.AsyncAnthropic),
        save_history_fn=save_history_fn,
        extract_citations_fn=extract_citations,
        extract_delta_citation_fn=_extract_delta_citation,
        build_usage_fn=_build_usage,
        append_assistant_message_fn=_append_assistant_message,
    ):
        yield event
