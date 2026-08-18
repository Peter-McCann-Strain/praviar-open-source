"""Request input validation middleware.

Enforces body size limits, content-type checks, SMILES sanitization,
and request timeouts to protect the API from malformed or malicious input.

Usage:
    Applied globally in main.py:
        app.add_middleware(InputValidationMiddleware)
"""

from __future__ import annotations

import json
import re

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse
from starlette.types import Message

logger = structlog.get_logger()

# ── Defaults ─────────────────────────────────────────────────────────────────

DEFAULT_MAX_BODY_SIZE = 1_048_576  # 1 MB
MAX_SMILES_LENGTH = 5_000
MAX_COMPOUND_NAME_LENGTH = 500

# Paths exempt from JSON content-type requirement
CONTENT_TYPE_EXEMPT_PATHS = frozenset(
    {
        "/api/health",
        "/api/docs",
        "/api/openapi.json",
        "/api/redoc",
    }
)

# Paths exempt from body size check (GET, HEAD, OPTIONS don't have bodies)
BODYLESS_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "DELETE"})

# SMILES validation: reject strings with obvious shell/SQL injection patterns
_INJECTION_PATTERNS = re.compile(
    r"(?:"
    r"[;|`$]"  # shell metacharacters
    r"|<script"  # XSS
    r"|DROP\s+TABLE"  # SQL
    r"|UNION\s+SELECT"  # SQL
    r"|--\s"  # SQL comment
    r"|/\*"  # SQL block comment
    r")",
    re.IGNORECASE,
)

# Valid SMILES characters: alphanumeric, brackets, symbols used in SMILES notation
# This is intentionally permissive to allow valid extended SMILES
_VALID_SMILES_CHARS = re.compile(r"^[A-Za-z0-9@#%+\-=\[\]\(\)\\/\.:,\*\$\s]+$")

_SUPPORTED_CONTENT_TYPES = (
    "application/json",
    "application/x-www-form-urlencoded",
    "multipart/form-data",
)


# ── SMILES validation ────────────────────────────────────────────────────────


def _requires_content_type_check(method: str, path: str) -> bool:
    return method not in BODYLESS_METHODS and path not in CONTENT_TYPE_EXEMPT_PATHS


def _content_type_is_supported(content_type: str) -> bool:
    return any(allowed in content_type for allowed in _SUPPORTED_CONTENT_TYPES)


def _content_length_exceeds_limit(
    content_length: str | None,
    max_body_size: int,
) -> tuple[bool, int | None]:
    if not content_length:
        return False, None

    try:
        size = int(content_length)
    except ValueError:
        return False, None

    return size > max_body_size, size


def _request_declares_body(request: Request) -> bool:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            return int(content_length) > 0
        except ValueError:
            return True
    return "transfer-encoding" in request.headers


def _analysis_smiles_value(body: dict[str, object]) -> str:
    for key in ("compound_smiles", "smiles", "compound_input"):
        value = body.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _analysis_name_value(body: dict[str, object]) -> str:
    for key in ("compound_name", "name"):
        value = body.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def validate_smiles_input(smiles: str) -> tuple[bool, str]:
    """Validate a SMILES string for safety and basic correctness.

    Returns:
        (is_valid, error_message)
    """
    if not smiles:
        return True, ""

    if len(smiles) > MAX_SMILES_LENGTH:
        return False, f"SMILES string exceeds maximum length of {MAX_SMILES_LENGTH} characters"

    if _INJECTION_PATTERNS.search(smiles):
        return False, "SMILES string contains invalid characters (possible injection attempt)"

    if not _VALID_SMILES_CHARS.match(smiles):
        return False, "SMILES string contains characters not valid in SMILES notation"

    # Check balanced brackets
    bracket_depth = 0
    paren_depth = 0
    for ch in smiles:
        if ch == "[":
            bracket_depth += 1
        elif ch == "]":
            bracket_depth -= 1
        elif ch == "(":
            paren_depth += 1
        elif ch == ")":
            paren_depth -= 1
        if bracket_depth < 0 or paren_depth < 0:
            return False, "SMILES string has unbalanced brackets/parentheses"

    if bracket_depth != 0 or paren_depth != 0:
        return False, "SMILES string has unbalanced brackets/parentheses"

    return True, ""


def validate_compound_name(name: str) -> tuple[bool, str]:
    """Validate a compound name for safety.

    Returns:
        (is_valid, error_message)
    """
    if not name:
        return True, ""

    if len(name) > MAX_COMPOUND_NAME_LENGTH:
        return (
            False,
            f"Compound name exceeds maximum length of {MAX_COMPOUND_NAME_LENGTH} characters",
        )

    if _INJECTION_PATTERNS.search(name):
        return False, "Compound name contains invalid characters"

    return True, ""


# ── Problem JSON helper ──────────────────────────────────────────────────────


def _problem_response(
    status: int, title: str, detail: str, *, request: Request | None = None
) -> JSONResponse:
    """Return an RFC 9457 Problem Details error response."""
    from api.errors import _type_uri_for_status

    return JSONResponse(
        status_code=status,
        content={
            "type": _type_uri_for_status(status),
            "title": title,
            "status": status,
            "detail": detail,
            "instance": str(request.url.path) if request is not None else None,
            "request_id": getattr(request.state, "request_id", None)
            if request is not None
            else None,
        },
        media_type="application/problem+json",
    )


class _StreamingBodyTooLargeError(Exception):
    def __init__(self, size: int, max_size: int) -> None:
        self.size = size
        self.max_size = max_size
        super().__init__(f"Request body exceeded {max_size} bytes")


async def _buffer_request_body_with_limit(request: Request, max_body_size: int) -> None:
    received = 0
    original_receive = request._receive
    messages: list[Message] = []

    while True:
        message = await original_receive()
        if message.get("type") == "http.request":
            body = message.get("body", b"") or b""
            received += len(body)
            if received > max_body_size:
                raise _StreamingBodyTooLargeError(received, max_body_size)
            messages.append(message)
            if not message.get("more_body", False):
                break
            continue
        messages.append(message)
        break

    replay = iter(messages)

    async def replay_receive():
        try:
            return next(replay)
        except StopIteration:
            return {"type": "http.disconnect"}

    request._receive = replay_receive


# ── Middleware ────────────────────────────────────────────────────────────────


class InputValidationMiddleware(BaseHTTPMiddleware):
    """Validates request body size and content type.

    Request timeouts are enforced at the reverse-proxy layer (Cloudflare/nginx),
    not here — asyncio.wait_for interferes with Starlette body streaming.

    Args:
        app: The ASGI application.
        max_body_size: Maximum request body size in bytes (default 1 MB).
    """

    def __init__(
        self,
        app,
        max_body_size: int = DEFAULT_MAX_BODY_SIZE,
    ):
        super().__init__(app)
        self.max_body_size = max_body_size

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        method = request.method.upper()

        # ── Content-Type check ───────────────────────────────────────────
        if _requires_content_type_check(method, path) and _request_declares_body(request):
            content_type = request.headers.get("content-type", "")
            if not content_type:
                logger.warning("missing_content_type", path=path)
                return _problem_response(
                    415,
                    "Unsupported Media Type",
                    "Content-Type is required. Use application/json.",
                    request=request,
                )
            if not _content_type_is_supported(content_type):
                logger.warning(
                    "invalid_content_type",
                    path=path,
                    content_type=content_type,
                )
                return _problem_response(
                    415,
                    "Unsupported Media Type",
                    f"Content-Type '{content_type}' is not supported. Use application/json.",
                    request=request,
                )

        # ── Body size check ──────────────────────────────────────────────
        if method not in BODYLESS_METHODS:
            content_length_header = request.headers.get("content-length")
            too_large, size = _content_length_exceeds_limit(
                content_length_header,
                self.max_body_size,
            )
            if too_large and size is not None:
                logger.warning(
                    "request_body_too_large",
                    path=path,
                    content_length=size,
                    max_allowed=self.max_body_size,
                )
                return _problem_response(
                    413,
                    "Content Too Large",
                    f"Request body size ({size} bytes) exceeds the maximum "
                    f"allowed size ({self.max_body_size} bytes).",
                    request=request,
                )
            if content_length_header is None or size is None:
                try:
                    await _buffer_request_body_with_limit(request, self.max_body_size)
                except _StreamingBodyTooLargeError as exc:
                    logger.warning(
                        "request_stream_body_too_large",
                        path=path,
                        received_bytes=exc.size,
                        max_allowed=exc.max_size,
                    )
                    return _problem_response(
                        413,
                        "Content Too Large",
                        "Request body size exceeds the maximum allowed size "
                        f"({exc.max_size} bytes).",
                        request=request,
                    )

        # Request timeouts are handled at the reverse proxy level (Cloudflare/nginx)
        # rather than in middleware, since asyncio.wait_for interferes with
        # Starlette's BaseHTTPMiddleware request body streaming.
        #
        # FastAPI's RequestValidationError handler is registered at the app
        # exception-handler layer, which BaseHTTPMiddleware does not forward
        # exceptions to (Starlette limitation).  Catch it here so validation
        # errors always produce a proper 422 response instead of propagating
        # as an unhandled exception through the middleware stack.
        try:
            return await call_next(request)
        except Exception as exc:
            from fastapi.exceptions import RequestValidationError

            if isinstance(exc, RequestValidationError):
                return _problem_response(
                    422,
                    "Validation Error",
                    "Request body or query parameters failed validation",
                    request=request,
                )
            raise


# ── FastAPI dependency for route-level validation ────────────────────────────


async def validate_analysis_input(request: Request) -> None:
    """FastAPI dependency that validates SMILES and compound name inputs.

    Apply to analysis creation endpoints:
        @router.post("/analyses", dependencies=[Depends(validate_analysis_input)])
    """
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        from api.errors import APIError

        logger.warning(
            "malformed_json_body",
            path=request.url.path,
            error=str(exc),
        )
        raise APIError(
            400,
            "Malformed JSON",
            "Request body is not valid JSON.",
        ) from exc

    if not isinstance(body, dict):
        from api.errors import APIError

        logger.warning(
            "non_object_json_body",
            path=request.url.path,
            body_type=type(body).__name__,
        )
        raise APIError(
            400,
            "Invalid Request Body",
            "Request body must be a JSON object.",
        )

    # Validate SMILES if present
    smiles = _analysis_smiles_value(body)
    if smiles and isinstance(smiles, str):
        valid, error = validate_smiles_input(smiles)
        if not valid:
            from api.errors import APIError

            raise APIError(422, "Validation Error", error)

    # Validate compound name if present
    name = _analysis_name_value(body)
    if name and isinstance(name, str):
        valid, error = validate_compound_name(name)
        if not valid:
            from api.errors import APIError

            raise APIError(422, "Validation Error", error)
