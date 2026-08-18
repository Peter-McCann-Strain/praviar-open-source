"""Conversation-preparation and history-persistence helpers for chat."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

import structlog

from api.config import APISettings, get_settings
from api.errors import APIError
from api.schemas.chat import ChatCapability, ChatPolicy, ChatToolPolicy, TrustMode
from api.services import chat_documents

if TYPE_CHECKING:
    from api.schemas.chat import ChatRequest

logger = structlog.get_logger()


@dataclass(frozen=True)
class ChatConversationScope:
    org_id: uuid.UUID
    analysis_id: uuid.UUID
    user_id: uuid.UUID


@dataclass(frozen=True)
class PreparedChatRequest:
    conversation_id: str
    history_scope: ChatConversationScope
    system_prompt: str
    messages: list[dict]
    history: list[dict]
    policy: ChatPolicy


def _fail_closed_on_history_backend_error(settings: APISettings | None = None) -> bool:
    runtime_settings = settings or get_settings()
    return getattr(runtime_settings, "app_env", None) == "prod"


def _raise_chat_history_backend_unavailable(action: str, exc: Exception) -> None:
    raise APIError(
        503,
        "Service Unavailable",
        f"Chat history backend is unavailable; refusing to {action}.",
    ) from exc


def issue_or_validate_conversation_id(conversation_id: str | None) -> str:
    """Return a server-issued UUID conversation id or reject caller-supplied junk."""
    if conversation_id is None:
        return str(uuid.uuid4())
    try:
        return str(uuid.UUID(conversation_id))
    except (TypeError, ValueError) as exc:
        raise APIError(
            400,
            "Bad Request",
            "Invalid conversation_id; use the UUID returned by the chat stream.",
        ) from exc


def conversation_history_key(
    conversation_id: str,
    *,
    scope: ChatConversationScope,
) -> str:
    """Build the Redis key for one user's conversation with one analysis."""
    return f"chat:v2:{scope.org_id}:{scope.analysis_id}:{scope.user_id}:{conversation_id}"


def _normalized_trust_mode(report_data: dict) -> str:
    trust_mode = str(report_data.get("trust_mode") or "explorer").strip().lower()
    if trust_mode in {"explorer", "counsel", "monitor"}:
        return trust_mode
    return "explorer"


def _external_evidence_scope_ready(evidence_scope: dict[str, Any]) -> bool:
    if evidence_scope.get("external_live_retrieval") is not True:
        return False

    raw_providers = evidence_scope.get("provider_capabilities")
    if raw_providers is None:
        raw_providers = evidence_scope.get("providers")
    if not isinstance(raw_providers, list):
        return False

    return any(
        isinstance(provider, dict) and provider.get("live_retrieval_supported") is True
        for provider in raw_providers
    )


def build_chat_policy(report_data: dict, *, patent_id: str | None = None) -> ChatPolicy:
    """Derive governed chat capabilities from the report payload."""
    trust_mode = _normalized_trust_mode(report_data)
    routing_profile = dict(report_data.get("routing_profile") or {})
    opinion_readiness = dict(report_data.get("opinion_readiness") or {})
    certification_scope = report_data.get("certification_scope") or {}
    record_completeness = report_data.get("record_completeness") or {}
    jurisdiction_matrix = list(report_data.get("jurisdiction_matrix") or [])
    uncertainty_register = list(report_data.get("uncertainty_register") or [])
    evidence_scope = dict(report_data.get("evidence_scope") or {})

    allowed_capabilities = [
        "report_grounded_qna",
        "claim_element_citation",
        "risk_summary",
        "patent_comparison",
        "uncertainty_surface",
    ]
    blocked_capabilities = [
        "external_search",
        "live_database_lookup",
        "tool_execution_claims",
    ]
    capability_matrix = [
        ChatCapability(
            name="report_grounded_qna",
            description="Answer questions only from the supplied report and patent context.",
            evidence_basis=[
                "report_data",
                "citations",
                "search_strategy_log",
            ],
        ),
        ChatCapability(
            name="claim_element_citation",
            description="Cite specific patent claims, elements, and report sections.",
            evidence_basis=[
                "patent_analyses",
                "patent_narratives",
                "claim_construction_record",
            ],
        ),
        ChatCapability(
            name="risk_summary",
            description="Summarize the report's risk and clearance posture.",
            evidence_basis=[
                "risk_summary",
                "clearance_decision",
                "opinion_readiness",
            ],
        ),
        ChatCapability(
            name="patent_comparison",
            description="Compare patents already present in the attached report.",
            evidence_basis=[
                "patent_analyses",
                "jurisdiction_matrix",
                "source_convergence",
            ],
        ),
        ChatCapability(
            name="uncertainty_surface",
            description="Surface limitations, gaps, and caution flags from the report.",
            evidence_basis=[
                "uncertainty_register",
                "data_coverage",
                "negative_search_log",
            ],
        ),
    ]
    system_directives = [
        "Use only the supplied report and any patent-specific document in context.",
        "Do not claim live retrieval, monitoring execution, or external database access.",
        "Ground every conclusion in cited report evidence.",
    ]

    if trust_mode == "explorer":
        allowed_capabilities.extend(
            ["screening_summary", "next_step_triage", "preliminary_risk_call"]
        )
        blocked_capabilities.extend(["opinion_language", "export_ready_summary"])
        system_directives.append(
            "Treat responses as preliminary screening and avoid opinion-like language."
        )
        capability_matrix.extend(
            [
                ChatCapability(
                    name="screening_summary",
                    description="Provide a fast, preliminary screen from the report.",
                    evidence_basis=["trust_mode", "risk_summary", "opinion_readiness"],
                ),
                ChatCapability(
                    name="next_step_triage",
                    description="Suggest concrete next steps based on reported gaps and risk.",
                    evidence_basis=["uncertainty_register", "data_coverage"],
                ),
                ChatCapability(
                    name="preliminary_risk_call",
                    description="Offer a cautionary, non-opinionated risk call.",
                    evidence_basis=["risk_summary", "clearance_decision"],
                ),
            ]
        )
    elif trust_mode == "counsel":
        allowed_capabilities.extend(
            ["clearance_readiness_review", "jurisdiction_matrix_review", "export_summary"]
        )
        blocked_capabilities.extend(["definitive_signoff_language"])
        system_directives.append(
            "Use evidence-bound caution: if export readiness is false, do not present "
            "the answer as a signable opinion."
        )
        capability_matrix.extend(
            [
                ChatCapability(
                    name="clearance_readiness_review",
                    description=(
                        "Review whether the report supports a governed clearance posture."
                    ),
                    evidence_basis=[
                        "clearance_decision",
                        "record_completeness",
                        "opinion_readiness",
                    ],
                ),
                ChatCapability(
                    name="jurisdiction_matrix_review",
                    description="Inspect jurisdiction-level decisioning and caution flags.",
                    evidence_basis=["jurisdiction_matrix", "routing_profile"],
                ),
                ChatCapability(
                    name="export_summary",
                    description=(
                        "Summarize the report in an export-oriented but still report-grounded form."
                    ),
                    evidence_basis=[
                        "opinion_readiness",
                        "record_completeness",
                        "clearance_decision",
                    ],
                ),
            ]
        )
        if opinion_readiness.get("export_ready") is True:
            allowed_capabilities.append("signable_opinion_summary")
            capability_matrix.append(
                ChatCapability(
                    name="signable_opinion_summary",
                    description=(
                        "Draft an export-ready summary only when the report says "
                        "export_ready is true."
                    ),
                    evidence_basis=[
                        "opinion_readiness.export_ready",
                        "record_completeness.clearance_grade_ready",
                    ],
                )
            )
        else:
            blocked_capabilities.append("signable_opinion_summary")
    else:
        allowed_capabilities.extend(["monitor_delta_summary", "watchlist_triage"])
        blocked_capabilities.extend(["signable_opinion_summary", "export_summary"])
        system_directives.append(
            "Focus on changes, watchlist implications, and what to monitor next."
        )
        capability_matrix.extend(
            [
                ChatCapability(
                    name="monitor_delta_summary",
                    description="Summarize changes and monitoring implications from the report.",
                    evidence_basis=["search_loop_result", "source_convergence"],
                ),
                ChatCapability(
                    name="watchlist_triage",
                    description="Surface follow-up items for ongoing monitoring and review.",
                    evidence_basis=["opinion_readiness", "uncertainty_register"],
                ),
            ]
        )

    if opinion_readiness.get("export_ready") is not True:
        blocked_capabilities.append("signable_opinion_summary")
    if bool(opinion_readiness.get("attorney_supervision_required", True)):
        blocked_capabilities.append("attorney_independent_signoff")

    external_scope_ready = _external_evidence_scope_ready(evidence_scope)
    external_retrieval_allowed = trust_mode in {"counsel", "monitor"} and external_scope_ready
    if external_retrieval_allowed:
        allowed_capabilities.append("external_evidence_expand")
    else:
        blocked_capabilities.append("external_evidence_expand")

    if routing_profile:
        system_directives.append(
            f"Routing profile: modality={routing_profile.get('modality', 'unknown')}, "
            f"capability_profile={routing_profile.get('capability_profile', 'unknown')}."
        )

    evidence_basis = [
        {"field": "trust_mode", "value": trust_mode},
        {"field": "routing_profile.modality", "value": routing_profile.get("modality", "unknown")},
        {
            "field": "routing_profile.capability_profile",
            "value": routing_profile.get("capability_profile", "unknown"),
        },
        {
            "field": "opinion_readiness.export_ready",
            "value": opinion_readiness.get("export_ready", False),
        },
        {
            "field": "opinion_readiness.attorney_supervision_required",
            "value": opinion_readiness.get("attorney_supervision_required", True),
        },
        {
            "field": "record_completeness.clearance_grade_ready",
            "value": record_completeness.get("clearance_grade_ready", False),
        },
        {
            "field": "certification_scope.attorney_supervision_required",
            "value": certification_scope.get("attorney_supervision_required", True)
            if isinstance(certification_scope, dict)
            else True,
        },
        {
            "field": "jurisdiction_matrix.count",
            "value": len(jurisdiction_matrix),
        },
        {
            "field": "uncertainty_register.count",
            "value": len(uncertainty_register),
        },
        {
            "field": "evidence_scope.external_live_retrieval",
            "value": evidence_scope.get("external_live_retrieval", False),
        },
        {
            "field": "evidence_scope.live_provider_ready",
            "value": external_scope_ready,
        },
    ]

    if patent_id:
        evidence_basis.append({"field": "scope.patent_id", "value": patent_id})

    # Deduplicate while preserving order.
    deduped_allowed: list[str] = []
    for capability in allowed_capabilities:
        if capability not in deduped_allowed:
            deduped_allowed.append(capability)

    deduped_blocked: list[str] = []
    for capability in blocked_capabilities:
        if capability not in deduped_blocked and capability not in deduped_allowed:
            deduped_blocked.append(capability)

    monitoring_actions_allowed = trust_mode == "monitor" and bool(
        report_data.get("search_loop_result")
    )
    tool_policy = ChatToolPolicy(
        allowed_actions=list(deduped_allowed),
        blocked_actions=list(deduped_blocked),
        external_retrieval_allowed=external_retrieval_allowed,
        monitoring_actions_allowed=monitoring_actions_allowed,
        notes=[
            "Chat responses stay report-grounded unless a governed evidence action "
            "is explicitly invoked from the workspace.",
            (
                "Governed external evidence expansion is available in the workspace."
                if external_retrieval_allowed
                else (
                    "No live patent search, database lookup, or external tool execution "
                    "is available in this surface unless the report evidence scope "
                    "declares live provider readiness."
                )
            ),
        ],
    )

    return ChatPolicy(
        trust_mode=cast(TrustMode, trust_mode),
        capability_profile=str(routing_profile.get("capability_profile") or "report_grounded"),
        routing_profile=routing_profile,
        opinion_readiness=opinion_readiness,
        allowed_capabilities=deduped_allowed,
        blocked_capabilities=deduped_blocked,
        capability_matrix=capability_matrix,
        tool_policy=tool_policy,
        evidence_basis=evidence_basis,
        system_directives=system_directives,
    )


def prepare_chat_request(
    body: ChatRequest,
    *,
    conversation_id: str,
    history_scope: ChatConversationScope,
    report_data: dict,
    history: list[dict],
    build_patent_document_fn,
    build_report_document_fn,
    patent_system_prompt: str,
    report_system_prompt: str,
) -> PreparedChatRequest:
    """Build document context, prompt, message array, and updated user history."""
    policy = build_chat_policy(report_data, patent_id=body.patent_id)
    if body.patent_id:
        document = build_patent_document_fn(body.patent_id, report_data)
        system_prompt = patent_system_prompt
    else:
        document = build_report_document_fn(report_data)
        system_prompt = report_system_prompt

    system_prompt = chat_documents.build_chat_system_prompt(system_prompt, policy)

    messages: list[dict] = []
    if not history:
        messages.append(
            {
                "role": "user",
                "content": [document, {"type": "text", "text": body.message}],
            }
        )
    else:
        first_msg = history[0]
        if isinstance(first_msg.get("content"), str):
            messages.append(
                {
                    "role": "user",
                    "content": [document, {"type": "text", "text": first_msg["content"]}],
                }
            )
        else:
            messages.append(first_msg)

        for msg in history[1:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": body.message})

    updated_history = list(history)
    updated_history.append(
        {
            "role": "user",
            "content": body.message,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )
    return PreparedChatRequest(
        conversation_id=conversation_id,
        history_scope=history_scope,
        system_prompt=system_prompt,
        messages=messages,
        history=updated_history,
        policy=policy,
    )


async def get_conversation_history(
    conversation_id: str,
    *,
    scope: ChatConversationScope,
    settings: APISettings | None = None,
    get_redis_fn,
) -> list[dict]:
    """Load conversation history from Redis."""
    try:
        redis = await get_redis_fn()
        data = await redis.get(conversation_history_key(conversation_id, scope=scope))
        if data:
            parsed = json.loads(data)
            if isinstance(parsed, list):
                return cast(list[dict[Any, Any]], parsed)
            raise TypeError("conversation history payload must be a JSON array")
    except Exception as exc:
        logger.warning("chat_history_load_failed", conversation_id=conversation_id, exc_info=True)
        if _fail_closed_on_history_backend_error(settings):
            _raise_chat_history_backend_unavailable("load prior conversation context", exc)
    return []


async def save_conversation_history(
    conversation_id: str,
    messages: list[dict],
    *,
    scope: ChatConversationScope,
    settings: APISettings,
    get_redis_fn,
) -> None:
    """Persist chat history with TTL and max-history trimming."""
    try:
        redis = await get_redis_fn()
        if len(messages) > settings.chat_max_history:
            messages = messages[-settings.chat_max_history :]
        await redis.set(
            conversation_history_key(conversation_id, scope=scope),
            json.dumps(messages, default=str),
            ex=settings.chat_history_ttl,
        )
    except Exception as exc:
        logger.warning("chat_history_save_failed", conversation_id=conversation_id, exc_info=True)
        if _fail_closed_on_history_backend_error(settings):
            _raise_chat_history_backend_unavailable("persist conversation context", exc)


async def clear_conversation_history(
    conversation_id: str,
    *,
    scope: ChatConversationScope,
    settings: APISettings | None = None,
    get_redis_fn,
) -> None:
    """Clear Redis chat history, failing closed in production."""
    try:
        redis = await get_redis_fn()
        await redis.delete(conversation_history_key(conversation_id, scope=scope))
    except Exception as exc:
        logger.warning("chat_history_clear_failed", conversation_id=conversation_id, exc_info=True)
        if _fail_closed_on_history_backend_error(settings):
            _raise_chat_history_backend_unavailable("clear conversation context", exc)
