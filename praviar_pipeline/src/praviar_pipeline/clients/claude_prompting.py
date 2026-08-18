"""Prompt and JSON handling helpers for the Claude client."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from praviar_pipeline.sanitize import UNTRUSTED_DATA_POLICY

logger = structlog.get_logger()

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def current_date_context() -> str:
    """Return the current date context to prepend to Claude system prompts."""
    now = datetime.now(tz=UTC)
    return (
        f"CURRENT DATE: {now.strftime('%B %d, %Y')} (UTC). "
        "You are operating with real-time data. Patents with publication years "
        "up to and including the current year are valid and exist in public "
        "patent databases. Do NOT reject or question patent IDs based on your "
        "training data cutoff — trust the data provided to you as ground truth.\n\n"
    )


def load_prompt(filename: str) -> str:
    """Load a prompt template from the prompts directory.

    Records the filename and SHA256 of the on-disk content with the manifest
    :class:`PromptHasher` so the final report manifest can pin the exact
    prompt revisions used in a run.
    """
    from praviar_pipeline.manifest import get_prompt_hasher

    path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    text = path.read_text()
    get_prompt_hasher().record(filename, text)
    return text


def build_effective_system(system: str, json_schema: dict[str, Any] | None = None) -> str:
    """Build the Claude system prompt with runtime date context and optional schema."""
    effective_system = current_date_context() + UNTRUSTED_DATA_POLICY + "\n\n" + system
    if not json_schema:
        return effective_system

    schema_text = json.dumps(json_schema, indent=2)
    return (
        effective_system + "\n\nOutput your analysis as a single JSON object matching this schema. "
        "Output ONLY the JSON, no other text.\n\n"
        f"```json\n{schema_text}\n```"
    )


def build_system_content(system: str, *, cache_system: bool) -> str | list[dict[str, Any]]:
    """Build Anthropic system content with optional prompt caching markers."""
    if not cache_system:
        return system
    return [
        {
            "type": "text",
            "text": system,
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        }
    ]


def extract_json(text: str) -> str:
    """Extract JSON from model text that may include markdown or preamble."""
    stripped = text.strip()

    if stripped.startswith("{"):
        return repair_truncated_json(stripped)

    match = re.search(r"```(?:json)?\s*\n?(.*?)```", stripped, re.DOTALL)
    if match:
        return repair_truncated_json(match.group(1).strip())

    match = re.search(r"```(?:json)?\s*\n?(.*)", stripped, re.DOTALL)
    if match:
        candidate = match.group(1).strip()
        if candidate.startswith("{"):
            return repair_truncated_json(candidate)

    # Scan for the first brace that opens a balanced JSON object, skipping
    # bare braces in preamble text like "For claim {1}: {...}". We walk each
    # `{` candidate and check whether it closes before the next `{`.
    search_start = 0
    while True:
        first_brace = stripped.find("{", search_start)
        if first_brace == -1:
            break
        # Walk forward to find the matching closing brace.
        depth = 0
        in_str = False
        esc = False
        end = -1
        for i, ch in enumerate(stripped[first_brace:], start=first_brace):
            if esc:
                esc = False
                continue
            if ch == "\\" and in_str:
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end != -1:
            candidate = stripped[first_brace : end + 1]
            # Skip trivially short objects like `{1}` that are not JSON dicts.
            if len(candidate) > 4 and ":" in candidate:
                return candidate
            search_start = first_brace + 1
        else:
            # No closing brace — truncated; repair from here.
            return repair_truncated_json(stripped[first_brace:])

    return stripped


def repair_truncated_json(text: str) -> str:
    """Repair truncated JSON by closing unbalanced braces and brackets."""
    open_braces = 0
    open_brackets = 0
    in_string = False
    escape_next = False

    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            open_braces += 1
        elif ch == "}":
            open_braces -= 1
        elif ch == "[":
            open_brackets += 1
        elif ch == "]":
            open_brackets -= 1

    if open_braces <= 0 and open_brackets <= 0:
        return text

    repaired = text.rstrip()
    repaired = re.sub(r"[,:]\s*$", "", repaired)
    # Strip a trailing orphaned partial key (e.g. `, "design_around_sug` at end
    # of output). This pattern matches a comma then an unclosed quote with no
    # further quotes — i.e. the truncation fell inside a key name, not a value.
    # Closing it as `""` would produce `{..., ""}` which is invalid JSON.
    repaired = re.sub(r',\s*"[^"]*$', "", repaired)
    # Close any remaining open string value (truncation inside a value).
    repaired = re.sub(r'"[^"]*$', '""', repaired)
    repaired += "]" * max(0, open_brackets)
    repaired += "}" * max(0, open_braces)

    logger.warning(
        "json_truncation_repaired",
        original_length=len(text),
        open_braces=open_braces,
        open_brackets=open_brackets,
    )

    return repaired
