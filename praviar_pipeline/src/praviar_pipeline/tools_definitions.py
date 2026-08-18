"""Anthropic tool definitions for FTO research helpers."""

from __future__ import annotations

from typing import Any

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "get_current_date",
        "description": (
            "Get the current date and time in UTC. Use this to determine "
            "whether patents are expired, recently published, or to "
            "contextualize dates in patent prosecution history. Also useful "
            "to verify that patent publication dates are valid."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "lookup_patent",
        "description": (
            "Look up patent metadata by publication number. Returns title, "
            "abstract, filing date, grant date, priority date, and assignee. "
            "Use this when you encounter a cited patent and need additional "
            "context, or to verify information about a patent."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "patent_id": {
                    "type": "string",
                    "description": (
                        "Patent publication number (e.g. 'US-7851188-B2', 'US-2025074964-A1')"
                    ),
                },
            },
            "required": ["patent_id"],
        },
    },
    {
        "name": "check_patent_status",
        "description": (
            "Check the prosecution and legal status of a US patent. Returns "
            "application number, filing date, prosecution history summary "
            "(number of office actions, amendments, rejections), and whether "
            "a notice of allowance was issued. Use this to assess patent "
            "validity and prosecution history context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "patent_id": {
                    "type": "string",
                    "description": "US patent number to check status for",
                },
            },
            "required": ["patent_id"],
        },
    },
]
