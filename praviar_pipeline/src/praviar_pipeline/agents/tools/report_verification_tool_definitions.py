"""Tool-definition builders for report verification."""

from __future__ import annotations

from typing import Any


def build_report_verification_tool_definitions() -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = [
        {
            "name": "check_patent_exists",
            "description": (
                "Verify that a patent ID mentioned in the report actually exists in "
                "the pipeline analysis data. Returns risk level and assignee if found."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "patent_id": {
                        "type": "string",
                        "description": "Patent publication number to verify",
                    },
                },
                "required": ["patent_id"],
            },
        },
        {
            "name": "check_risk_level",
            "description": (
                "Verify that a risk level stated in the report matches the actual "
                "pipeline assessment for a specific patent."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "patent_id": {
                        "type": "string",
                        "description": "Patent publication number",
                    },
                    "claimed_risk_level": {
                        "type": "string",
                        "description": "Risk level as stated in the report (high/medium/low/clear)",
                    },
                },
                "required": ["patent_id", "claimed_risk_level"],
            },
        },
        {
            "name": "check_element_status",
            "description": (
                "Verify that an element status (MET/NOT_MET/PARTIAL) stated in the "
                "report matches the actual claim analysis for a specific claim element."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "patent_id": {
                        "type": "string",
                        "description": "Patent publication number",
                    },
                    "claim_number": {
                        "type": "integer",
                        "description": "Claim number",
                    },
                    "element_number": {
                        "type": "integer",
                        "description": "Element number within the claim",
                    },
                    "claimed_status": {
                        "type": "string",
                        "description": (
                            "Status as stated in report (met/not_met/partially_met/unclear)"
                        ),
                    },
                },
                "required": [
                    "patent_id",
                    "claim_number",
                    "element_number",
                    "claimed_status",
                ],
            },
        },
        {
            "name": "check_date",
            "description": (
                "Verify that a date (expiry, filing, grant) stated in the report "
                "matches the actual pipeline data for a patent."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "patent_id": {
                        "type": "string",
                        "description": "Patent publication number",
                    },
                    "date_type": {
                        "type": "string",
                        "description": "Type of date: expiry, filing, grant, or priority",
                    },
                    "claimed_date": {
                        "type": "string",
                        "description": "Date as stated in the report (any reasonable format)",
                    },
                },
                "required": ["patent_id", "date_type", "claimed_date"],
            },
        },
        {
            "name": "check_assignee",
            "description": (
                "Verify that an assignee/owner name stated in the report matches "
                "the actual pipeline data for a patent. Uses fuzzy matching."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "patent_id": {
                        "type": "string",
                        "description": "Patent publication number",
                    },
                    "claimed_assignee": {
                        "type": "string",
                        "description": "Assignee name as stated in the report",
                    },
                },
                "required": ["patent_id", "claimed_assignee"],
            },
        },
    ]
    for definition in definitions:
        schema = definition["input_schema"]
        if "patent_id" in schema["properties"]:
            schema["properties"]["patent_id"]["pattern"] = r"^[A-Z]{2}[0-9]{4,16}[A-Z][0-9]$"
        schema["properties"]["assertion_id"] = {
            "type": "string",
            "pattern": r"^A[0-9]{5}-[a-f0-9]{12}$",
            "description": ("Exact deterministic assertion ID supplied in the verification prompt"),
        }
        schema["properties"]["assertion_text"] = {
            "type": "string",
            "minLength": 1,
            "maxLength": 100000,
            "description": ("Exact assertion text whose SHA-256 prefix is encoded in assertion_id"),
        }
        schema["required"] = [
            "assertion_id",
            "assertion_text",
            *schema["required"],
        ]
        schema["additionalProperties"] = False
    return definitions
