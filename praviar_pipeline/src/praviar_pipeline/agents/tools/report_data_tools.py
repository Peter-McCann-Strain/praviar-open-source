"""ReportDataToolkit — tools for LLM data access during report generation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from praviar_pipeline.tools_definitions import TOOL_DEFINITIONS as _SHARED_TOOL_DEFS

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from praviar_pipeline.pipeline.report_data_store import ReportDataStore

logger = structlog.get_logger()

_GET_CURRENT_DATE_DEF = next(d for d in _SHARED_TOOL_DEFS if d["name"] == "get_current_date")

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "get_portfolio_summary",
        "description": (
            "Get the full portfolio overview: compound info, overall risk level, "
            "patents by risk, assignee distribution, source health, data limitations, "
            "action items, and critic findings. CALL THIS FIRST to orient yourself "
            "before writing any section."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_report_scope_and_reliance",
        "description": (
            "Get structured guardrails for source-health, jurisdiction signals, "
            "negative-search wording, claim-text coverage, privilege marking, and "
            "legal reliance posture. CALL THIS before writing coverage, negative "
            "search, claim-text-unavailable, or disclaimer/reliance language."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_patent_analysis",
        "description": (
            "Get complete claim-by-claim analysis for one patent. Returns risk level, "
            "each claim with element-by-element status (MET/NOT_MET/PARTIAL), reasoning, "
            "and design-around suggestions. Use for Key Patent Analysis section."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "patent_id": {
                    "type": "string",
                    "description": "Patent publication number (e.g. 'US7964580B2')",
                },
            },
            "required": ["patent_id"],
        },
    },
    {
        "name": "get_doe_assessment",
        "description": (
            "Get Doctrine of Equivalents assessment for a patent. Returns FWR "
            "(function-way-result) test results, prosecution history estoppel "
            "analysis, and overall equivalence per element. Use when claim elements "
            "are NOT_MET or PARTIALLY_MET."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "patent_id": {
                    "type": "string",
                    "description": "Patent publication number",
                },
            },
            "required": ["patent_id"],
        },
    },
    {
        "name": "get_invalidity_assessment",
        "description": (
            "Get invalidity assessment for a patent: prior art references with "
            "DOI/title/date, PTAB proceedings with case numbers, Graham factors, "
            "enablement screening, and overall invalidity strength. Use for "
            "Invalidity/DoE/PTAB section."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "patent_id": {
                    "type": "string",
                    "description": "Patent publication number",
                },
            },
            "required": ["patent_id"],
        },
    },
    {
        "name": "get_patent_details",
        "description": (
            "Get enriched patent metadata: PTAB proceedings, Orange Book/Purple Book "
            "listing, patent term (PTA/PTE, terminal disclaimer, maintenance fees), "
            "ownership/assignment history, legal events. Use for patent term and "
            "regulatory context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "patent_id": {
                    "type": "string",
                    "description": "Patent publication number",
                },
            },
            "required": ["patent_id"],
        },
    },
    {
        "name": "get_drawing_evidence",
        "description": (
            "Get chemical structure drawing analysis (OCSR) for a patent. Returns "
            "extracted structures, Tanimoto similarity to target compound, substructure "
            "match results. Use when structural evidence is relevant."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "patent_id": {
                    "type": "string",
                    "description": "Patent publication number",
                },
            },
            "required": ["patent_id"],
        },
    },
    {
        "name": "get_prior_art_references",
        "description": (
            "Get all prior art references for a patent with full citation data: "
            "authors, title, journal, DOI, publication date, anticipation/obviousness "
            "scores. Use to build bibliography entries."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "patent_id": {
                    "type": "string",
                    "description": "Patent publication number",
                },
            },
            "required": ["patent_id"],
        },
    },
    {
        "name": "get_critic_findings",
        "description": (
            "Get the portfolio-level critic/QA report: cross-patent consistency "
            "findings, risk-claim mismatches, and quality score. Use to integrate "
            "QA findings into the report."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    _GET_CURRENT_DATE_DEF,
]


class ReportDataToolkit:
    """Toolkit providing pipeline data access to LLMs during report generation.

    Implements the Toolkit protocol (tool_definitions + execute).
    Never raises — returns human-readable error strings.
    """

    def __init__(self, data_store: ReportDataStore) -> None:
        self._store = data_store
        self._handlers: dict[str, Callable[[dict], Awaitable[str]]] = {
            "get_portfolio_summary": self._exec_portfolio_summary,
            "get_report_scope_and_reliance": self._exec_scope_and_reliance,
            "get_patent_analysis": self._exec_patent_analysis,
            "get_doe_assessment": self._exec_doe_assessment,
            "get_invalidity_assessment": self._exec_invalidity_assessment,
            "get_patent_details": self._exec_patent_details,
            "get_drawing_evidence": self._exec_drawing_evidence,
            "get_prior_art_references": self._exec_prior_art_references,
            "get_critic_findings": self._exec_critic_findings,
            "get_current_date": self._exec_current_date,
        }

    @property
    def tool_definitions(self) -> list[dict[str, Any]]:
        return TOOL_DEFINITIONS

    async def execute(self, tool_name: str, tool_input: dict) -> str:
        handler = self._handlers.get(tool_name)
        if not handler:
            return f"Unknown tool: {tool_name}. Available: {list(self._handlers.keys())}"
        try:
            return await handler(tool_input)
        except Exception:
            logger.error(
                "report_tool_error",
                tool=tool_name,
            )
            return f"Tool '{tool_name}' failed with a data access or validation error"

    async def _exec_portfolio_summary(self, _: dict) -> str:
        return self._store.format_portfolio_summary()

    async def _exec_scope_and_reliance(self, _: dict) -> str:
        return self._store.format_scope_and_reliance()

    async def _exec_patent_analysis(self, input_data: dict) -> str:
        patent_id = input_data.get("patent_id", "")
        if not patent_id:
            return "Error: patent_id is required."
        return self._store.format_analysis(patent_id)

    async def _exec_doe_assessment(self, input_data: dict) -> str:
        patent_id = input_data.get("patent_id", "")
        if not patent_id:
            return "Error: patent_id is required."
        return self._store.format_doe(patent_id)

    async def _exec_invalidity_assessment(self, input_data: dict) -> str:
        patent_id = input_data.get("patent_id", "")
        if not patent_id:
            return "Error: patent_id is required."
        return self._store.format_invalidity(patent_id)

    async def _exec_patent_details(self, input_data: dict) -> str:
        patent_id = input_data.get("patent_id", "")
        if not patent_id:
            return "Error: patent_id is required."
        return self._store.format_patent_details(patent_id)

    async def _exec_drawing_evidence(self, input_data: dict) -> str:
        patent_id = input_data.get("patent_id", "")
        if not patent_id:
            return "Error: patent_id is required."
        return self._store.format_drawing_evidence(patent_id)

    async def _exec_prior_art_references(self, input_data: dict) -> str:
        patent_id = input_data.get("patent_id", "")
        if not patent_id:
            return "Error: patent_id is required."
        return self._store.format_prior_art_references(patent_id)

    async def _exec_critic_findings(self, _: dict) -> str:
        return self._store.format_critic_findings()

    async def _exec_current_date(self, _: dict) -> str:
        now = datetime.now(UTC)
        return f"Current date and time (UTC): {now.strftime('%Y-%m-%d %H:%M:%S')}"
