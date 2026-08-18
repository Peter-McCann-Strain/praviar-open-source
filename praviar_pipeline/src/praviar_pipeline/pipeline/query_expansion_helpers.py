"""Pure helpers for Step 1.5 query expansion."""

from __future__ import annotations

from typing import TYPE_CHECKING

from praviar_pipeline.sanitize import sanitize_untrusted_text

if TYPE_CHECKING:
    from praviar_pipeline.models.search import ExpandedSearchQueries


def build_compound_context(compound) -> str:
    """Build the compound context block for the LLM prompt."""
    synonym_list = ", ".join(compound.synonyms[:20]) if compound.synonyms else "none"
    cas_list = ", ".join(compound.cas_numbers[:5]) if compound.cas_numbers else "none"
    functional_group_list = (
        ", ".join(compound.functional_groups) if compound.functional_groups else "none"
    )

    return (
        f"Compound: {compound.name}\n"
        f"SMILES: {compound.canonical_smiles}\n"
        f"Molecular formula: {compound.molecular_formula}\n"
        f"Molecular weight: {compound.molecular_weight}\n"
        f"PubChem CID: {compound.pubchem_cid}\n"
        f"Known synonyms: {synonym_list}\n"
        f"CAS numbers: {cas_list}\n"
        f"Functional groups: {functional_group_list}\n"
    )


def build_search_agent_prompt(compound_context: str) -> str:
    """Build the user prompt for the web-grounded expansion path."""
    return (
        sanitize_untrusted_text(compound_context, data_type="compound_context") + "\n"
        "You have a web_search tool available. Use it to look up:\n"
        "1. The correct CPC codes for patents related to this compound's production\n"
        "2. Companies/assignees that hold patents in this space\n"
        "3. Production methods and process terms used in patent literature\n"
        "\n"
        "After searching, generate your response as a single JSON object with these fields:\n"
        "patent_synonyms, cpc_codes, key_assignees, process_keywords, compound_class_terms\n"
        "\n"
        "Output ONLY the JSON object after your searches are complete."
    )


def build_no_search_prompt(compound_context: str) -> str:
    """Build the user prompt for the pure-LLM fallback path."""
    return (
        sanitize_untrusted_text(compound_context, data_type="compound_context") + "\n"
        "Generate expanded patent search queries for this compound. Focus on "
        "production method patents (fermentation, synthesis, bioconversion) and "
        "broad genus claims that would cover this compound."
    )


def format_tavily_results(results: list[dict[str, str]]) -> str:
    """Format Tavily search results for the tool response."""
    formatted = []
    for result in results:
        snippet = result["content"][:400] if result["content"] else ""
        formatted.append(f"**{result['title']}**\nSource: {result.get('url', '')}\n{snippet}")
    return "\n\n---\n\n".join(formatted)


def filter_invalid_cpc_codes(
    result: ExpandedSearchQueries,
    *,
    validate_cpc_code_fn,
) -> tuple[list[str], list[str]]:
    """Remove invalid CPC codes from the expansion result."""
    valid_codes = [code for code in result.cpc_codes if validate_cpc_code_fn(code)]
    invalid_codes = [code for code in result.cpc_codes if not validate_cpc_code_fn(code)]
    result.cpc_codes = valid_codes
    return valid_codes, invalid_codes
