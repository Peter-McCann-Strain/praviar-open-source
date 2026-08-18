"""Shared Pydantic base classes for the Praviar Pipeline model hierarchy.

This module is the canonical home for cross-cutting model fragments that
many concrete models share. The first such fragment is :class:`PatentBase`,
which carries the patent-identity fields (``patent_id``, ``jurisdiction``)
that 73+ models in this package were redeclaring independently.

Conventions
-----------
External boundary models (data ingested from third-party APIs/clients) use
``extra="forbid"`` so that schema drift surfaces as a validation error
rather than a silent miss. Internal pipeline-state models that need to
roundtrip through LLM-emitted JSON (which often contains harmless surplus
fields) use ``extra="ignore"`` and document the choice in their docstring.
``PatentBase`` defaults to ``forbid`` because it is most often used at an
external boundary; subclasses override ``model_config`` when they need
``ignore`` semantics — see :class:`praviar_pipeline.models.analysis.PatentAnalysis`
and :class:`praviar_pipeline.models.critic.CriticFinding` for examples.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PatentBase(BaseModel):
    """Shared identity fields for any model representing a patent or part thereof.

    Subclasses inherit ``patent_id`` (required) and ``jurisdiction`` (optional)
    so the wider model hierarchy keeps a single canonical declaration of these
    fields. The default ``model_config`` is ``extra="forbid"`` — strict, suited
    to external-boundary models. Subclasses that need lenient parsing (e.g.
    LLM output that may carry surplus keys) should override ``model_config``
    locally and add a docstring explaining why.

    Field semantics
    ---------------
    - ``patent_id``: normalised patent identifier such as ``US7851188B2`` or
      ``EP1234567A1``. Required because every patent-shaped record in the
      pipeline must be addressable by a stable id.
    - ``jurisdiction``: issuing patent office (``US``, ``EP``, ``WO``, ...).
      Defaults to empty string rather than ``None`` so downstream string
      operations (joins, filtering, formatting) are total — the original
      ``PatentHit`` field used this convention and we preserve it.
    """

    model_config = ConfigDict(extra="forbid")

    patent_id: str = Field(
        description="Normalized patent identifier (e.g. US7851188B2, EP1234567A1)"
    )
    jurisdiction: str = Field(
        default="",
        description="Issuing patent office (US, EP, WO, JP, KR, CN, IN, CA, AU)",
    )


class ToolDefinition(BaseModel):
    """Typed shape for an Anthropic tool definition handed to the API.

    The Anthropic Messages API accepts tool definitions as JSON objects with
    a fixed shape (``name``, ``description``, ``input_schema``). Several
    pipeline call-sites historically passed these as ``list[dict[str, Any]]``,
    which loses type safety at every boundary. This model captures the
    canonical shape so call-sites can construct typed values and call
    ``model_dump()`` to obtain the wire form expected by the SDK.

    The ``input_schema`` field is intentionally typed as ``dict[str, object]``
    — JSON Schema is recursive and the SDK validates it server-side, so a
    Pydantic-typed mirror would duplicate that validation without adding
    value. Treat it as an opaque blob from the caller's perspective.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Tool name as the model will see it")
    description: str = Field(
        description="Natural-language description shown to the model. Should explain "
        "what the tool does and when the model should call it.",
    )
    input_schema: dict[str, object] = Field(
        description="JSON Schema for the tool input. Validated server-side by the API.",
    )


__all__ = [
    "PatentBase",
    "ToolDefinition",
]
