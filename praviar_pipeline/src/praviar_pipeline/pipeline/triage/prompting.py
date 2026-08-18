"""Prompt construction helpers for Step 3 triage."""

from __future__ import annotations

from praviar_pipeline.utils.formatting import format_patent_context


def format_patent_for_triage(
    patent,
    *,
    max_abstract: int,
    max_claims: int,
    drawing_summary: str = "",
) -> str:
    """Format a patent hit for the triage prompt."""
    text = format_patent_context(
        patent,
        max_abstract=max_abstract,
        max_claims=max_claims,
    )
    if drawing_summary:
        text = f"{text}\n\n{drawing_summary}"
    return text


def build_triage_user_prompt(compound_context: str, formatted_patents: list[str]) -> str:
    """Build the user prompt for a triage batch."""
    patents_text = "\n\n---\n\n".join(formatted_patents)
    return f"""Analyze the following patents for relevance to the target compound.

{compound_context}

---

PATENTS TO CLASSIFY:

{patents_text}

---

Classify each patent and return your results. For every RELEVANT or
POSSIBLY_RELEVANT patent you MUST populate the blocking_potential field with a
concise, specific risk statement (e.g. "Composition-of-matter claim directly
covers the target compound - high blocking risk if in-force and valid"). Without
claims text, infer blocking risk from the title, abstract, and CPC codes."""
