"""Specification-text parsing and chunking for Step 4 claim construction.

Under the governing US standard (Phillips v. AWH Corp., 2005) claim terms must
be construed in light of the patent specification. Step 4 retrieves the full
specification text from BigQuery; this module turns that raw text into a
column/line-addressable structure and reduces oversized specifications by
definition-aware chunking rather than blunt truncation, so the passages that
actually define ambiguous claim terms survive into the prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import structlog

logger = structlog.get_logger()

# Patent description text from BigQuery carries paragraph markers such as
# ``[0001]``. Granted-patent specifications are also addressable by column and
# line. We surface both so a construed term can carry a precise citation.
_PARAGRAPH_MARKER = re.compile(r"\[(\d{3,5})\]")

# Phrases that introduce a lexicographic definition in a patent specification.
# A passage carrying one of these is a claim-construction anchor and is never
# dropped by the chunker.
_DEFINITION_CUES: tuple[str, ...] = (
    "as used herein",
    "as used in this",
    "is defined as",
    "are defined as",
    "refers to",
    "refer to",
    "the term",
    "means, in the context",
    "for the purposes of this",
    "shall mean",
    "is intended to mean",
)


@dataclass(frozen=True)
class SpecPassage:
    """A column/line-addressable passage of specification text."""

    paragraph: str
    text: str
    is_definition: bool

    @property
    def citation(self) -> str:
        """A short, human-readable citation for this passage."""
        if self.paragraph:
            return f"para. {self.paragraph}"
        return "spec."


def _passage_has_definition_cue(text: str) -> bool:
    lowered = text.lower()
    return any(cue in lowered for cue in _DEFINITION_CUES)


def parse_spec_passages(spec_text: str) -> list[SpecPassage]:
    """Split raw specification text into addressable passages.

    Splitting is driven by paragraph markers (``[0001]``) when present;
    otherwise the text is split on blank lines. Each passage records whether it
    introduces a lexicographic definition so the chunker can preserve it.
    """
    if not spec_text or not spec_text.strip():
        return []

    passages: list[SpecPassage] = []
    markers = list(_PARAGRAPH_MARKER.finditer(spec_text))

    if markers:
        for index, match in enumerate(markers):
            start = match.end()
            end = markers[index + 1].start() if index + 1 < len(markers) else len(spec_text)
            body = spec_text[start:end].strip()
            if not body:
                continue
            passages.append(
                SpecPassage(
                    paragraph=match.group(1),
                    text=body,
                    is_definition=_passage_has_definition_cue(body),
                )
            )
        return passages

    # No paragraph markers: fall back to blank-line splitting. Such passages are
    # not column/line addressable, so the paragraph reference is left empty.
    for block in re.split(r"\n\s*\n", spec_text):
        body = block.strip()
        if not body:
            continue
        passages.append(
            SpecPassage(
                paragraph="",
                text=body,
                is_definition=_passage_has_definition_cue(body),
            )
        )
    return passages


def chunk_spec_text(spec_text: str, *, max_chars: int) -> str:
    """Reduce an oversized specification to ``max_chars`` without blunt truncation.

    The historical behaviour sliced the first ``max_chars`` characters, which
    silently discarded every definition that happened to sit past the cut. This
    routine instead keeps all definition-bearing passages and fills the
    remaining budget with leading context, so ambiguous claim terms can still be
    construed against the passages that define them.

    A specification already within budget is returned unchanged, so existing
    inputs see no behavioural difference.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if len(spec_text) <= max_chars:
        return spec_text

    passages = parse_spec_passages(spec_text)
    if not passages:
        # Unparseable text: keep the documented cap as a last resort.
        return spec_text[:max_chars]

    definition_passages = [p for p in passages if p.is_definition]
    context_passages = [p for p in passages if not p.is_definition]

    selected: list[SpecPassage] = []
    used = 0
    separator_cost = len("\n\n")

    def _rendered_cost(passage: SpecPassage) -> int:
        # Account for the paragraph marker prefix (``[0001] ``) added at render
        # time so the result never overruns ``max_chars``.
        prefix = len(f"[{passage.paragraph}] ") if passage.paragraph else 0
        return len(passage.text) + prefix + separator_cost

    def _try_add(passage: SpecPassage) -> bool:
        nonlocal used
        cost = _rendered_cost(passage)
        if used + cost > max_chars:
            return False
        selected.append(passage)
        used += cost
        return True

    # Definitions first: they are the claim-construction anchors.
    dropped_definitions = 0
    for passage in definition_passages:
        if not _try_add(passage):
            dropped_definitions += 1

    # Fill the remaining budget with leading context for general orientation.
    for passage in context_passages:
        if not _try_add(passage):
            break

    if not selected:
        # Every individual passage exceeds the budget (e.g. one enormous block
        # of unparagraphed text). Fall back to the documented character cap so
        # at least the leading specification context survives.
        logger.warning(
            "spec_text_no_passage_within_budget",
            original_chars=len(spec_text),
            max_chars=max_chars,
        )
        return spec_text[:max_chars]

    if dropped_definitions:
        logger.warning(
            "spec_text_definitions_dropped",
            dropped=dropped_definitions,
            total_definitions=len(definition_passages),
            max_chars=max_chars,
        )

    # Re-order to original document order so paragraph numbering reads naturally.
    order = {id(p): index for index, p in enumerate(passages)}
    selected.sort(key=lambda p: order[id(p)])

    rendered: list[str] = []
    for passage in selected:
        if passage.paragraph:
            rendered.append(f"[{passage.paragraph}] {passage.text}")
        else:
            rendered.append(passage.text)
    result = "\n\n".join(rendered)

    logger.info(
        "spec_text_chunked",
        original_chars=len(spec_text),
        chunked_chars=len(result),
        max_chars=max_chars,
        definitions_kept=len(definition_passages) - dropped_definitions,
        context_passages_kept=len(selected) - (len(definition_passages) - dropped_definitions),
    )
    return result
