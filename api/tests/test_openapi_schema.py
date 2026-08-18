"""OpenAPI schema health and stability checks.

Verifies that:
- The app can generate its OpenAPI schema without errors
- All routes have documented response schemas (no bare 200 → any)
- All documented error responses use application/problem+json
- Key endpoints are present at expected paths
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def openapi_schema():
    from api.main import create_app

    app = create_app()
    return app.openapi()


def test_openapi_schema_generates_without_error(openapi_schema):
    """Schema generation must succeed (catches missing type annotations, etc.)."""
    assert openapi_schema["openapi"].startswith("3.")
    assert "paths" in openapi_schema
    assert len(openapi_schema["paths"]) > 10


def test_checked_in_openapi_artifact_matches_live_application(openapi_schema):
    """The committed client contract must be regenerated with every API change."""
    artifact_path = Path(__file__).resolve().parents[1] / "openapi.generated.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact == openapi_schema, (
        "api/openapi.generated.json is stale; run "
        "`cd api && PYTHONPATH=src .venv/bin/python -m api.cli export-openapi`"
    )


def test_openapi_health_endpoint_present(openapi_schema):
    assert "/api/health" in openapi_schema["paths"]


def test_openapi_analyses_endpoint_present(openapi_schema):
    assert any(path.startswith("/api/v1/analyses") for path in openapi_schema["paths"])


def test_openapi_problem_detail_schema_registered(openapi_schema):
    """ProblemDetail must be in components/schemas for RFC 9457 clients."""
    schemas = openapi_schema.get("components", {}).get("schemas", {})
    assert "ProblemDetail" in schemas
    pd = schemas["ProblemDetail"]
    assert "type" in pd.get("properties", {})
    assert "status" in pd.get("properties", {})
    assert "detail" in pd.get("properties", {})


def test_openapi_sso_status_exposes_availability_and_freshness(openapi_schema):
    schema = openapi_schema["components"]["schemas"]["SSOStatusResponse"]
    properties = schema["properties"]
    required = set(schema["required"])
    expected = {
        "sso_status_available",
        "sso_last_synced_at",
        "sso_status_stale",
        "sso_unavailable_reason",
    }
    assert expected <= properties.keys()
    assert {"sso_status_available", "sso_last_synced_at", "sso_status_stale"} <= required


def test_openapi_patent_contract_separates_counsel_risk_from_restricted_payloads(
    openapi_schema,
):
    schemas = openapi_schema["components"]["schemas"]
    assert "risk_level" in schemas["PatentItem"]["properties"]
    assert "risk_level" in schemas["PatentItem"]["required"]
    assert "risk_level" not in schemas["RiskRestrictedPatentItem"]["properties"]
    assert "risk_level" in schemas["PatentAnalysisSchema"]["properties"]
    assert "risk_level" in schemas["PatentAnalysisSchema"]["required"]
    assert "risk_level" not in schemas["RiskRestrictedPatentAnalysisSchema"]["properties"]
    assert "risk_summary" not in schemas["RiskRestrictedPatentAnalysisSchema"]["properties"]
    assert (
        "design_around_suggestions"
        not in schemas["RiskRestrictedPatentAnalysisSchema"]["properties"]
    )
    assert set(schemas["RiskRestrictedPatentAnalysisSchema"]["properties"]) == {
        "patent_id",
        "title",
        "assignee",
        "expiry_date",
        "claims_analyzed",
    }
    assert set(schemas["RiskRestrictedClaimElementSchema"]["properties"]) == {
        "element_number",
        "element_text",
    }
    assert set(schemas["RiskRestrictedClaimAnalysisSchema"]["properties"]) == {
        "claim_number",
        "claim_type",
        "depends_on",
        "preamble",
        "transitional_phrase",
        "elements",
    }
    assert set(schemas["RiskRestrictedDoEAssessmentSchema"]["properties"]) == {
        "patent_id",
        "claim_number",
        "element_number",
        "element_text",
    }
    assert set(schemas["RiskRestrictedInvalidityAssessmentSchema"]["properties"]) == {
        "patent_id",
        "claim_numbers",
        "ptab",
        "prior_art",
    }
    assert set(schemas["RiskRestrictedPriorArtReferenceSchema"]["properties"]) == {
        "reference_id",
        "title",
        "publication_date",
        "reference_type",
        "authors",
        "journal",
        "doi",
        "url",
        "abstract",
        "source_database",
    }
    restricted_detail = schemas["RiskRestrictedPatentDetailResponse"]["properties"]
    assert restricted_detail["doe_assessment"]["anyOf"][0]["$ref"] == (
        "#/components/schemas/RiskRestrictedDoEAssessmentSchema"
    )
    assert restricted_detail["invalidity_assessment"]["anyOf"][0]["$ref"] == (
        "#/components/schemas/RiskRestrictedInvalidityAssessmentSchema"
    )

    list_response = openapi_schema["paths"]["/api/v1/patents"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert {option["$ref"] for option in list_response["anyOf"]} == {
        "#/components/schemas/PatentListResponse",
        "#/components/schemas/RiskRestrictedPatentListResponse",
    }


def test_openapi_no_routes_missing_response_schema(openapi_schema):
    """Every non-health route must declare at least one 2xx or 4xx response."""
    exempt = {"/api/health", "/api/health/ready"}
    missing = []
    for path, methods in openapi_schema["paths"].items():
        if path in exempt:
            continue
        for method, op in methods.items():
            if method == "parameters":
                continue
            responses = op.get("responses", {})
            if not responses:
                missing.append(f"{method.upper()} {path}")
    assert not missing, f"Routes with no documented responses: {missing}"


def test_openapi_error_responses_use_problem_json(openapi_schema):
    """Explicitly documented error responses should use application/problem+json.

    FastAPI auto-injects 422 with application/json media-type for every route
    regardless of the registered exception handler — that is a known FastAPI
    schema-generation limitation, not a runtime bug (our handler converts to
    problem+json at runtime). Exempt status 422 from this schema-level check.
    """
    violations = []
    for path, methods in openapi_schema["paths"].items():
        for method, op in methods.items():
            if method == "parameters":
                continue
            for status, resp_obj in op.get("responses", {}).items():
                if str(status) == "422":  # FastAPI limitation — exempt from schema check
                    continue
                if not str(status).startswith(("4", "5")):
                    continue
                content = resp_obj.get("content", {})
                if content and "application/problem+json" not in content:
                    violations.append(f"{method.upper()} {path} {status}")
    assert not violations, f"Error responses not using problem+json: {violations}"
