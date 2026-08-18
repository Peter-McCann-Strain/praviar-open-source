"""Focused tests for request input validation middleware and helpers."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport

from api.errors import APIError, api_error_handler
from api.middleware.input_validation import (
    InputValidationMiddleware,
    validate_analysis_input,
    validate_compound_name,
    validate_smiles_input,
)


@pytest.fixture
def input_validation_app() -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(APIError, api_error_handler)  # type: ignore[arg-type]
    app.add_middleware(InputValidationMiddleware, max_body_size=1_024)

    @app.post("/api/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/analyses", dependencies=[Depends(validate_analysis_input)])
    async def analyses() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/actions/empty")
    async def empty_action() -> dict[str, bool]:
        return {"ok": True}

    return app


@pytest.fixture
async def input_validation_client(input_validation_app: FastAPI):
    async with httpx.AsyncClient(
        transport=ASGITransport(app=input_validation_app),
        base_url="http://test",
    ) as client:
        yield client


@pytest.mark.parametrize(
    ("smiles", "expected"),
    [
        ("CC(=O)Oc1ccccc1C(=O)O", (True, "")),
        (
            "CC;DROP TABLE analyses",
            (
                False,
                "SMILES string contains invalid characters (possible injection attempt)",
            ),
        ),
        ("(" * 5001, (False, "SMILES string exceeds maximum length of 5000 characters")),
    ],
)
def test_validate_smiles_input(smiles: str, expected: tuple[bool, str]) -> None:
    assert validate_smiles_input(smiles) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Aspirin", (True, "")),
        ("x" * 501, (False, "Compound name exceeds maximum length of 500 characters")),
        ("Aspirin; DROP TABLE compounds", (False, "Compound name contains invalid characters")),
    ],
)
def test_validate_compound_name(name: str, expected: tuple[bool, str]) -> None:
    assert validate_compound_name(name) == expected


@pytest.mark.asyncio
async def test_middleware_rejects_unsupported_content_type(
    input_validation_client: httpx.AsyncClient,
) -> None:
    resp = await input_validation_client.post(
        "/analyses",
        content=b"{}",
        headers={"Content-Type": "text/plain"},
    )

    assert resp.status_code == 415
    assert resp.headers["content-type"] == "application/problem+json"
    assert resp.json()["detail"] == (
        "Content-Type 'text/plain' is not supported. Use application/json."
    )


@pytest.mark.asyncio
async def test_middleware_allows_bodyless_post_without_content_type(
    input_validation_client: httpx.AsyncClient,
) -> None:
    resp = await input_validation_client.post("/actions/empty")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


@pytest.mark.asyncio
async def test_middleware_rejects_oversized_request(
    input_validation_client: httpx.AsyncClient,
) -> None:
    resp = await input_validation_client.post(
        "/analyses",
        content=b"{}",
        headers={
            "Content-Type": "application/json",
            "Content-Length": "2048",
        },
    )

    assert resp.status_code == 413
    assert resp.headers["content-type"] == "application/problem+json"
    assert "exceeds the maximum allowed size (1024 bytes)" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_middleware_rejects_streamed_oversized_request_without_content_length(
    input_validation_client: httpx.AsyncClient,
) -> None:
    async def oversized_stream():
        yield b'{"compound_input":"'
        yield b"C" * 1100
        yield b'"}'

    resp = await input_validation_client.post(
        "/analyses",
        content=oversized_stream(),
        headers={"Content-Type": "application/json"},
    )

    assert resp.status_code == 413
    assert resp.headers["content-type"] == "application/problem+json"
    assert "maximum allowed size (1024 bytes)" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_middleware_allows_exempt_path_with_plain_text(
    input_validation_client: httpx.AsyncClient,
) -> None:
    resp = await input_validation_client.post(
        "/api/health",
        content=b"not-json",
        headers={"Content-Type": "text/plain"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


@pytest.mark.asyncio
async def test_validate_analysis_input_accepts_aliases(
    input_validation_client: httpx.AsyncClient,
) -> None:
    resp = await input_validation_client.post(
        "/analyses",
        content=json.dumps({"compound_input": "CC(=O)Oc1ccccc1C(=O)O", "name": "Aspirin"}),
        headers={"Content-Type": "application/json"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


@pytest.mark.asyncio
async def test_validate_analysis_input_rejects_invalid_smiles(
    input_validation_client: httpx.AsyncClient,
) -> None:
    resp = await input_validation_client.post(
        "/analyses",
        content=json.dumps({"smiles": "CC;DROP TABLE analyses", "name": "Aspirin"}),
        headers={"Content-Type": "application/json"},
    )

    assert resp.status_code == 422
    assert resp.json()["detail"] == (
        "SMILES string contains invalid characters (possible injection attempt)"
    )


@pytest.mark.asyncio
async def test_validate_analysis_input_rejects_invalid_name(
    input_validation_client: httpx.AsyncClient,
) -> None:
    resp = await input_validation_client.post(
        "/analyses",
        content=json.dumps(
            {"compound_smiles": "CC(=O)Oc1ccccc1C(=O)O", "compound_name": "x" * 501}
        ),
        headers={"Content-Type": "application/json"},
    )

    assert resp.status_code == 422
    assert resp.json()["detail"] == "Compound name exceeds maximum length of 500 characters"


@pytest.mark.asyncio
async def test_validate_analysis_input_rejects_malformed_json(
    input_validation_client: httpx.AsyncClient,
) -> None:
    """Malformed JSON must be rejected with RFC 9457 400, not silently accepted."""
    resp = await input_validation_client.post(
        "/analyses",
        content=b"not-json",
        headers={"Content-Type": "application/json"},
    )

    assert resp.status_code == 400
    assert resp.headers["content-type"] == "application/problem+json"
    body = resp.json()
    assert body["title"] == "Malformed JSON"
    assert body["detail"] == "Request body is not valid JSON."
    assert body["status"] == 400


@pytest.mark.asyncio
async def test_validate_analysis_input_rejects_non_object_json(
    input_validation_client: httpx.AsyncClient,
) -> None:
    """Top-level non-object JSON (e.g. a list) must be rejected with 400."""
    resp = await input_validation_client.post(
        "/analyses",
        content=b"[1, 2, 3]",
        headers={"Content-Type": "application/json"},
    )

    assert resp.status_code == 400
    assert resp.headers["content-type"] == "application/problem+json"
    assert resp.json()["title"] == "Invalid Request Body"
