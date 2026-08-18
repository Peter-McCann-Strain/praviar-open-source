"""Search expansion models — output of Step 1.5 (query expansion)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

QueryExpansionOrigin = Literal[
    "unknown",
    "web_grounded_agent",
    "model_without_live_grounding",
    "coverage_assessment_agent",
    "evidence_directive",
]


class QueryExpansionProvenance(BaseModel):
    """How an expanded patent-search query set was produced.

    Search terms can materially change a Freedom-to-Operate conclusion.  This
    record distinguishes live-grounded expansion from model-only generation
    and preserves the actual grounding queries and source locators used.
    """

    model_config = ConfigDict(extra="forbid")

    origin: QueryExpansionOrigin = "unknown"
    grounded: bool = False
    model_name: str = Field(default="", max_length=200)
    grounding_queries: list[str] = Field(default_factory=list, max_length=20)
    source_urls: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("grounding_queries")
    @classmethod
    def _validate_grounding_queries(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if any(len(value) > 500 for value in cleaned):
            raise ValueError("grounding query exceeds 500 characters")
        return cleaned

    @field_validator("source_urls")
    @classmethod
    def _validate_source_urls(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if any(
            len(value) > 2000 or not (value.startswith("https://") or value.startswith("http://"))
            for value in cleaned
        ):
            raise ValueError("query-expansion source URL is invalid")
        return cleaned


class ExpandedSearchQueryTerms(BaseModel):
    """Search terms that the model is permitted to generate."""

    model_config = ConfigDict(extra="ignore")

    patent_synonyms: list[str] = Field(
        default_factory=list,
        description="Broad patent synonyms (e.g. 'C4 dicarboxylic acid', 'amber acid')",
    )
    cpc_codes: list[str] = Field(
        default_factory=list,
        description="Predicted CPC classification codes (e.g. 'C12P7/46', 'C07C55/10')",
    )
    key_assignees: list[str] = Field(
        default_factory=list,
        description="Companies known to patent in this compound's production space",
    )
    process_keywords: list[str] = Field(
        default_factory=list,
        description="Production method terms (e.g. 'fermentation', 'biosynthesis')",
    )
    compound_class_terms: list[str] = Field(
        default_factory=list,
        description="Genus-level chemical descriptions (e.g. 'dicarboxylic acid')",
    )


class ExpandedSearchQueries(ExpandedSearchQueryTerms):
    """Search terms plus system-owned provenance consumed by Step 2.

    Provenance is deliberately excluded from :class:`ExpandedSearchQueryTerms`
    so an LLM cannot author or corrupt the record of how its terms were
    obtained.
    """

    provenance: QueryExpansionProvenance = Field(
        default_factory=QueryExpansionProvenance,
        description="Origin and live-source evidence for this exact query expansion.",
    )
