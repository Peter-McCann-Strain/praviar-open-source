"""Reasoning trace models — captures every decision made by research agents."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ToolCall(BaseModel):
    """Record of a single tool invocation by a research agent."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    tool_input: dict = Field(default_factory=dict)
    tool_output_summary: str = Field(
        default="",
        description="Truncated summary of tool output (for storage efficiency)",
    )
    duration_ms: int = 0


class AgentRound(BaseModel):
    """One think→act→observe cycle within a research agent."""

    model_config = ConfigDict(extra="forbid")

    round_number: int
    thinking_summary: str = Field(
        default="",
        description="Summary of agent's reasoning from extended thinking",
    )
    tool_calls: list[ToolCall] = Field(default_factory=list)
    observations: str = Field(
        default="",
        description="What the agent learned this round",
    )
    scratchpad_delta: dict = Field(
        default_factory=dict,
        description="Changes to the running scratchpad this round",
    )
    decision: str = Field(
        default="",
        description="What the agent decided to do next and why",
    )


class ReasoningTrace(BaseModel):
    """Full audit trail for a research agent's multi-round investigation."""

    model_config = ConfigDict(extra="forbid")

    agent_type: str = Field(description="e.g. claim_analysis, prosecution, prior_art, report")
    model: str = ""
    patent_id: str = ""
    rounds: list[AgentRound] = Field(default_factory=list)
    self_critique: str = Field(
        default="",
        description="Agent's self-assessment of its own analysis quality",
    )
    revisions_made: list[str] = Field(
        default_factory=list,
        description="Changes made after self-critique",
    )
    final_output_summary: str = Field(
        default="",
        description="Brief summary of the agent's final conclusion",
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_duration_ms: int = 0
