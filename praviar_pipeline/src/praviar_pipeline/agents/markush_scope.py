"""MarkushScopeAgent — reason about whether a target compound falls within
the scope of a Markush claim.

Phase E capability. Consumed from the drawing pipeline when the classifier
flags an image as MARKUSH and MarkushGrapher-2 has produced a CXSMILES.
Runs Claude Opus 4.7 in a bounded tool-use loop against RDKit/SMARTS/R-group
enumeration tools. Output is a MarkushScopeVerdict attached to the
DrawingStructure.

Design principles:
  - Text-only. The image was already turned into CXSMILES by MG2; the agent
    reasons about scope, not pixels.
  - ≥1 tool call required before verdict. Prevents hallucinated verdicts
    grounded only in the claim prose.
  - Hard turn cap (default 8). Model/tool execution is bounded; abstain rather
    than churn.
  - Prompt caching: stable preamble + tools + claim text kept at the front
    so repeat invocations on the same patent (different targets) reuse the
    cache.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, cast

import structlog

from praviar_pipeline.agents.tools.markush_tools import MarkushToolkit
from praviar_pipeline.models.drawing import MarkushScopeVerdict
from praviar_pipeline.sanitize import sanitize_prompt_value, sanitize_untrusted_text

if TYPE_CHECKING:
    from praviar_pipeline.clients.claude import ClaudeClient

logger = structlog.get_logger()

_SYSTEM_PROMPT = """You are a pharmaceutical patent attorney assistant specialising in \
Markush claim scope analysis. Given:
  - A Markush scaffold (CXSMILES with [*:N] placeholders)
  - R-group definitions parsed from claim text
  - A target compound SMILES
  - Excerpts of the claim text

Determine whether the target compound falls within the Markush scope. Return a verdict \
of "in_scope", "out_of_scope", or "ambiguous".

Rules:
  1. You MUST call at least one tool (rdkit_substructure_match OR rgroup_enumerate) \
before issuing a verdict. A verdict unsupported by tool evidence is not acceptable.
  2. If the R-group enumeration exceeds the hard cap (overflowed=True), issue "ambiguous" \
with abstained_reason="enumeration_overflow".
  3. If the scaffold substructure does not match the target, verdict MUST be "out_of_scope".
  4. If every R-group in the target matches at least one option in the corresponding \
substitution list, verdict is "in_scope".
  5. Prefer "ambiguous" with a clear abstained_reason over a guess.
  6. Output your final answer as JSON in the exact format below, inside a single \
<verdict> block:

<verdict>
{
  "verdict": "in_scope" | "out_of_scope" | "ambiguous",
  "reasoning": "one-to-three-sentence rationale grounded in tool results",
  "enumerated_hits": ["canonical SMILES of R-group hits", ...],
  "confidence": 0.0 to 1.0,
  "abstained_reason": "" or a short phrase if verdict == ambiguous"
}
</verdict>
"""

_PATENT_ID_RE = re.compile(r"^[A-Za-z]{2}[A-Za-z0-9./-]{1,63}$")


def _validated_structure(value: str, *, field: str) -> str:
    """Reject markup/control characters without rewriting chemical syntax."""
    if not value or len(value) > 20_000 or any(char in value for char in "<>&\r\n\x00"):
        raise ValueError(f"Invalid {field} structure encoding")
    return value


@dataclass(slots=True, frozen=True)
class MarkushScopeInput:
    """Inputs to MarkushScopeAgent.run()."""

    scaffold_cxsmiles: str
    target_smiles: str
    claim_text: str
    rgroup_definitions: dict[str, list[str]]
    patent_id: str = ""


def _extract_verdict_block(text: str) -> dict[str, Any] | None:
    """Pull the JSON object out of a <verdict>...</verdict> block.

    Returns None if no well-formed verdict found — caller should treat that
    as an abstention.
    """
    if not text:
        return None
    start = text.find("<verdict>")
    if start < 0:
        return None
    end = text.find("</verdict>", start)
    if end < 0:
        return None
    body = text[start + len("<verdict>") : end].strip()
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def _normalise_verdict(
    raw: dict[str, Any] | None,
    *,
    tool_calls: int,
    agent_model: str,
) -> MarkushScopeVerdict:
    """Coerce a parsed verdict dict into a validated MarkushScopeVerdict.

    Unknown verdict strings → "ambiguous". Missing fields defaulted.
    """
    if not raw:
        return MarkushScopeVerdict(
            verdict="ambiguous",
            reasoning="Agent produced no parseable verdict block.",
            abstained_reason="no_verdict_block",
            tool_calls=tool_calls,
            agent_model=agent_model,
        )

    verdict_value = str(raw.get("verdict", "")).strip().lower()
    if verdict_value not in {"in_scope", "out_of_scope", "ambiguous"}:
        verdict_value = "ambiguous"
    verdict = cast(
        "Literal['in_scope', 'out_of_scope', 'ambiguous']",
        verdict_value,
    )

    try:
        confidence = float(raw.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    hits_raw = raw.get("enumerated_hits", []) or []
    enumerated_hits = [str(h) for h in hits_raw if h] if isinstance(hits_raw, list) else []

    return MarkushScopeVerdict(
        verdict=verdict,
        reasoning=str(raw.get("reasoning", ""))[:4000],
        enumerated_hits=enumerated_hits,
        confidence=confidence,
        tool_calls=tool_calls,
        agent_model=agent_model,
        abstained_reason=str(raw.get("abstained_reason", ""))[:200],
    )


class MarkushScopeAgent:
    """Bounded tool-use loop that produces a MarkushScopeVerdict.

    Usage:
        agent = MarkushScopeAgent(claude=claude_client)
        verdict = await agent.run(MarkushScopeInput(...))

    The agent is stateless across invocations — each `run()` creates a fresh
    MarkushToolkit so tool_call counts don't leak across targets.
    """

    def __init__(
        self,
        claude: ClaudeClient,
        *,
        model_id: str | None = None,
        max_turns: int = 8,
        max_output_tokens: int = 6000,
    ) -> None:
        self._claude = claude
        self._model_id = model_id  # None → settings.claude_deep_model
        self._max_turns = max_turns
        self._max_output_tokens = max_output_tokens

    def _resolve_model(self) -> str:
        if self._model_id:
            return self._model_id
        from praviar_pipeline.config import get_settings

        return get_settings().claude_deep_model

    def _format_task(self, inp: MarkushScopeInput) -> str:
        """Build the user-content turn for the tool-use loop."""
        rgroups_json = json.dumps(inp.rgroup_definitions or {}, indent=2)
        if inp.patent_id and not _PATENT_ID_RE.fullmatch(inp.patent_id):
            raise ValueError("Invalid patent identifier")
        parts = [
            "<markush_scope_task>",
            (
                f"<patent_id>{sanitize_prompt_value(inp.patent_id)}</patent_id>"
                if inp.patent_id
                else ""
            ),
            "<scaffold_cxsmiles>"
            + _validated_structure(inp.scaffold_cxsmiles, field="scaffold")
            + "</scaffold_cxsmiles>",
            "<target_smiles>"
            + _validated_structure(inp.target_smiles, field="target")
            + "</target_smiles>",
            sanitize_untrusted_text(rgroups_json, data_type="rgroup_definitions"),
            sanitize_untrusted_text(
                inp.claim_text,
                max_len=6000,
                data_type="claim_excerpt",
            ),
            "</markush_scope_task>",
            "",
            "Decide whether the target compound falls within the Markush scope. "
            "Use the tools to ground your verdict — at least one tool call is required.",
        ]
        return "\n".join(p for p in parts if p)

    async def run(self, inp: MarkushScopeInput) -> MarkushScopeVerdict:
        """Execute the agent and return a validated MarkushScopeVerdict.

        The agent is required to call ≥1 tool. If zero tools were used, the
        returned verdict is coerced to "ambiguous" with
        abstained_reason="no_tool_use".
        """
        if not inp.target_smiles or not inp.scaffold_cxsmiles:
            return MarkushScopeVerdict(
                verdict="ambiguous",
                reasoning="Missing target or scaffold.",
                abstained_reason="missing_inputs",
            )

        toolkit = MarkushToolkit()
        model = self._resolve_model()

        # complete_text drives the tool-use loop when a toolkit is supplied.
        # Returns (response_text, metadata); we only need the text for
        # verdict parsing.
        response_text, _meta = await self._claude.complete_text(
            model=model,
            system=_SYSTEM_PROMPT,
            user=self._format_task(inp),
            toolkit=toolkit,
            max_tokens=self._max_output_tokens,
            cache_system=True,
            role="markush_scope",
        )

        raw_verdict = _extract_verdict_block(response_text)
        verdict = _normalise_verdict(
            raw_verdict,
            tool_calls=toolkit.call_count,
            agent_model=model,
        )

        # Enforce the "at least one tool call" rule post-hoc. If the agent
        # somehow produced a verdict without calling a tool, coerce to
        # ambiguous regardless of what it claimed.
        if toolkit.call_count == 0 and verdict.verdict != "ambiguous":
            logger.warning(
                "markush_scope_no_tool_use_verdict_rejected",
                claimed_verdict=verdict.verdict,
            )
            return MarkushScopeVerdict(
                verdict="ambiguous",
                reasoning=verdict.reasoning
                or "Agent issued a verdict without calling any grounding tools.",
                abstained_reason="no_tool_use",
                confidence=0.0,
                tool_calls=0,
                agent_model=model,
            )

        return verdict
