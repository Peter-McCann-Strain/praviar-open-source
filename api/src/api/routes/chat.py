"""Chat with FTO report -- Claude-powered conversational analysis.

Architecture:
- Report context is validated and bounded by the configured chat budget
- Citations API provides source attribution with character-level references
- Prompt caching reduces repeated context processing without asserting cost
- SSE streaming for real-time responses
- Conversation history in Redis (24h TTL)
"""

import json
import uuid

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from api.config import get_settings
from api.db.models import UserRole
from api.deps import CurrentUser, DBSession
from api.errors import APIError
from api.ratelimit import limiter
from api.schemas.chat import ChatRequest
from api.services.chat import (
    ChatConversationScope,
)
from api.services.chat import (
    clear_conversation_history as _clear_conversation_history,
)
from api.services.chat import (
    get_analysis_report_for_chat as _get_analysis_report_for_chat,
)
from api.services.chat import (
    get_conversation_history as _get_conversation_history,
)
from api.services.chat import (
    issue_or_validate_conversation_id as _issue_or_validate_conversation_id,
)
from api.services.chat import (
    prepare_chat_request as _prepare_chat_request,
)
from api.services.chat import (
    stream_chat_events as _stream_chat_events,
)
from api.services.chat_budget import (
    reconcile_chat_budget as _reconcile_chat_budget,
)
from api.services.chat_budget import reserve_chat_budget as _reserve_chat_budget
from api.services.report_access import require_completed_report_payload
from api.services.report_content import (
    filter_risk_ratings as _filter_risk_ratings,
)

logger = structlog.get_logger()
router = APIRouter()


def _sse_event(payload: dict) -> str:
    """Serialize a payload into an SSE frame."""
    return f"data: {json.dumps(payload)}\n\n"


def _ensure_chat_report_access(user: CurrentUser) -> None:
    if user.role == UserRole.CLIENT:
        raise APIError(403, "Forbidden", "Clients can only view summaries")


# ── Route ────────────────────────────────────────────────────────────


@router.post("/analyses/{analysis_id}/chat")
@limiter.limit("20/minute")
async def chat_with_report(
    analysis_id: uuid.UUID,
    body: ChatRequest,
    user: CurrentUser,
    db: DBSession,
    request: Request,
) -> StreamingResponse:
    """Chat with an FTO report. Returns SSE-streamed Claude response with citations."""
    settings = get_settings()

    if not settings.anthropic_api_key:
        raise APIError(
            503,
            "Service Unavailable",
            "Chat not available — Anthropic API key not configured",
        )

    _ensure_chat_report_access(user)
    conversation_id = _issue_or_validate_conversation_id(body.conversation_id)
    analysis = await _get_analysis_report_for_chat(
        db,
        analysis_id=analysis_id,
        org_id=user.org_id,
    )
    report_data = require_completed_report_payload(analysis, detail="Report not found")
    require_attorney = getattr(settings, "require_attorney_role_for_risk_ratings", False)
    if require_attorney and user.role not in (UserRole.ATTORNEY, UserRole.ADMIN):
        report_data = _filter_risk_ratings(report_data)
        logger.info(
            "chat_upl_risk_filtered",
            user_role=user.role.value,
            analysis_id=str(analysis_id),
        )

    history_scope = ChatConversationScope(
        org_id=user.org_id,
        analysis_id=analysis_id,
        user_id=user.id,
    )
    history = await _get_conversation_history(
        conversation_id,
        scope=history_scope,
        settings=settings,
    )
    prepared = _prepare_chat_request(
        body,
        conversation_id=conversation_id,
        history_scope=history_scope,
        report_data=report_data,
        history=history,
    )
    budget_reservation = await _reserve_chat_budget(
        prepared=prepared,
        scope=history_scope,
        settings=settings,
    )

    logger.info(
        "chat_request",
        analysis_id=analysis_id,
        conversation_id=prepared.conversation_id,
        patent_id=body.patent_id,
        trust_mode=prepared.policy.trust_mode,
        capability_profile=prepared.policy.capability_profile,
        export_ready=bool(prepared.policy.opinion_readiness.get("export_ready", False)),
        history_length=len(prepared.history),
    )

    async def generate():
        completed_usage: dict | None = None
        async for event in _stream_chat_events(settings=settings, prepared=prepared):
            if event.get("type") == "done" and isinstance(event.get("usage"), dict):
                completed_usage = event["usage"]
            yield _sse_event(event)
        if completed_usage is not None:
            try:
                await _reconcile_chat_budget(
                    reservation=budget_reservation,
                    usage=completed_usage,
                    settings=settings,
                )
            except Exception:
                # The full conservative reservation remains charged, so a
                # reconciliation outage cannot permit overspend.
                logger.warning(
                    "chat_budget_reconciliation_failed",
                    analysis_id=str(analysis_id),
                    conversation_id=prepared.conversation_id,
                    exc_info=True,
                )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/analyses/{analysis_id}/chat/{conversation_id}")
async def clear_chat_history(
    analysis_id: uuid.UUID,
    conversation_id: str,
    user: CurrentUser,
    db: DBSession,
) -> dict:
    """Clear chat conversation history."""
    _ensure_chat_report_access(user)
    validated_conversation_id = _issue_or_validate_conversation_id(conversation_id)
    await _get_analysis_report_for_chat(db, analysis_id=analysis_id, org_id=user.org_id)
    await _clear_conversation_history(
        validated_conversation_id,
        scope=ChatConversationScope(
            org_id=user.org_id,
            analysis_id=analysis_id,
            user_id=user.id,
        ),
        settings=get_settings(),
    )
    return {"status": "cleared", "conversation_id": validated_conversation_id}
