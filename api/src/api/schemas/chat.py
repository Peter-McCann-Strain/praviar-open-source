"""Request/response schemas for chat."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TrustMode = Literal["explorer", "counsel", "monitor"]


class ChatCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    enabled: bool = True
    description: str = ""
    evidence_basis: list[str] = Field(default_factory=list)


class ChatToolPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_mode: str = "report_grounded_only"
    allowed_actions: list[str] = Field(default_factory=list)
    blocked_actions: list[str] = Field(default_factory=list)
    external_retrieval_allowed: bool = False
    monitoring_actions_allowed: bool = False
    notes: list[str] = Field(default_factory=list)


class ChatPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trust_mode: TrustMode = "explorer"
    capability_profile: str = "report_grounded"
    routing_profile: dict[str, Any] = Field(default_factory=dict)
    opinion_readiness: dict[str, Any] = Field(default_factory=dict)
    allowed_capabilities: list[str] = Field(default_factory=list)
    blocked_capabilities: list[str] = Field(default_factory=list)
    capability_matrix: list[ChatCapability] = Field(default_factory=list)
    tool_policy: ChatToolPolicy = Field(default_factory=ChatToolPolicy)
    evidence_basis: list[dict[str, Any]] = Field(default_factory=list)
    system_directives: list[str] = Field(default_factory=list)


MAX_CHAT_MESSAGE_LENGTH = 8000


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., min_length=1, max_length=MAX_CHAT_MESSAGE_LENGTH)
    patent_id: str | None = Field(default=None, max_length=64)  # Scope to a single patent
    conversation_id: str | None = Field(default=None, max_length=64)  # Resume existing conversation


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    role: str  # "user" | "assistant"
    content: str
    citations: list[dict] | None = None
    timestamp: str
