"""Formatting helpers for pre-parsed patent claims."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from praviar_pipeline.utils.claim_parser_parsing import ParsedClaim


def format_pre_parsed_claims(claims: list[ParsedClaim]) -> str:
    """Format pre-parsed claims for inclusion in LLM prompts."""
    if not claims:
        return "No claims could be parsed from the patent text."

    independent = [claim for claim in claims if claim.claim_type == "independent"]
    dependent = [claim for claim in claims if claim.claim_type == "dependent"]

    lines = [
        f"PRE-PARSED CLAIMS ({len(independent)} independent, {len(dependent)} dependent)",
        "=" * 60,
        "",
    ]

    for claim in claims:
        dep_info = ""
        if claim.depends_on is not None:
            dep_info = f" [depends on Claim {claim.depends_on}]"

        lines.append(f"Claim {claim.claim_number} ({claim.claim_type}{dep_info}):")
        if claim.preamble:
            lines.append(f"  Preamble: {claim.preamble}")
            lines.append(
                f"  Element 0 (preamble candidate; assess and reproduce verbatim): {claim.preamble}"
            )
        if claim.transitional_phrase:
            lines.append(f'  Transitional phrase: "{claim.transitional_phrase}"')
        for element in claim.elements:
            lines.append(f"  Element {element.element_number}: {element.element_text}")
        lines.append("")

    lines.append("=" * 60)
    lines.append(
        "IMPORTANT: Use the claim structure above exactly as parsed. "
        "Do NOT re-parse, paraphrase, omit, or re-number the elements. "
        "Reproduce each element_text verbatim. For Element 0, separately classify "
        "the preamble as limiting, nonlimiting, or unresolved under the governing "
        "jurisdiction and cite the record basis; do not assume every preamble is "
        "limiting. For each element, assess whether the target compound/process "
        "meets it."
    )
    return "\n".join(lines)
