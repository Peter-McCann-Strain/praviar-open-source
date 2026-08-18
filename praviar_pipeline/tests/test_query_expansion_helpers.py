from __future__ import annotations

from praviar_pipeline.models.compound import ResolvedCompound
from praviar_pipeline.models.search import ExpandedSearchQueries
from praviar_pipeline.pipeline.query_expansion_helpers import (
    build_compound_context,
    build_no_search_prompt,
    build_search_agent_prompt,
    filter_invalid_cpc_codes,
    format_tavily_results,
)


def _compound() -> ResolvedCompound:
    return ResolvedCompound(
        name="aspirin",
        original_input="aspirin",
        input_type="name",
        canonical_smiles="CC(=O)OC1=CC=CC=C1C(=O)O",
        molecular_formula="C9H8O4",
        molecular_weight=180.16,
        pubchem_cid=2244,
        synonyms=["acetylsalicylic acid", "2-acetoxybenzoic acid"],
        cas_numbers=["50-78-2"],
        functional_groups=["ester", "carboxylic acid"],
    )


def test_build_compound_context_includes_resolved_fields() -> None:
    context = build_compound_context(_compound())

    assert "Compound: aspirin" in context
    assert "Known synonyms: acetylsalicylic acid, 2-acetoxybenzoic acid" in context
    assert "CAS numbers: 50-78-2" in context
    assert "Functional groups: ester, carboxylic acid" in context


def test_prompts_embed_compound_context() -> None:
    context = build_compound_context(_compound())

    assert "web_search tool available" in build_search_agent_prompt(context)
    assert "Generate expanded patent search queries" in build_no_search_prompt(context)


def test_format_tavily_results_truncates_and_separates_results() -> None:
    formatted = format_tavily_results(
        [
            {"title": "Result A", "content": "A" * 500},
            {"title": "Result B", "content": "short"},
        ]
    )

    assert "**Result A**" in formatted
    assert "**Result B**" in formatted
    assert "\n\n---\n\n" in formatted
    assert "A" * 401 not in formatted


def test_filter_invalid_cpc_codes_mutates_result() -> None:
    result = ExpandedSearchQueries(cpc_codes=["C12P7/00", "bad-code", "A61K31/00"])

    valid_codes, invalid_codes = filter_invalid_cpc_codes(
        result,
        validate_cpc_code_fn=lambda code: "/" in code and code[0].isalpha(),
    )

    assert valid_codes == ["C12P7/00", "A61K31/00"]
    assert invalid_codes == ["bad-code"]
    assert result.cpc_codes == valid_codes
