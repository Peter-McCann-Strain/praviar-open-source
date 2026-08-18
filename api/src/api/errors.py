"""RFC 9457 Problem Details error responses.

Provides a structured error model and custom exception handlers that return
application/problem+json responses, giving clients machine-readable error types.

Usage in routes:
    raise APIError(404, "Not Found", "No analysis with that ID exists in your org")

Type URIs follow the non-dereferenceable pattern:
https://problems.praviar.invalid/<slug>
Common slugs: not-found, forbidden, validation-error, rate-limit-exceeded,
              service-unavailable, bad-request, conflict, unauthorised
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from fastapi import Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

if TYPE_CHECKING:
    from slowapi.errors import RateLimitExceeded as _RateLimitExceeded
else:
    try:
        from slowapi.errors import RateLimitExceeded as _RateLimitExceeded
    except ImportError:  # slowapi optional in some environments
        _RateLimitExceeded = Exception

PROBLEM_TYPE_BASE_URI = "https://problems.praviar.invalid/"
_PROBLEM_TYPE_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# Mapping from HTTP status code to (slug, human-readable title).
_STATUS_MAP: dict[int, tuple[str, str]] = {
    400: ("bad-request", "Bad Request"),
    401: ("unauthorised", "Unauthorised"),
    403: ("forbidden", "Forbidden"),
    404: ("not-found", "Not Found"),
    410: ("gone", "Gone"),
    409: ("conflict", "Conflict"),
    413: ("content-too-large", "Content Too Large"),
    415: ("unsupported-media-type", "Unsupported Media Type"),
    422: ("validation-error", "Validation Error"),
    429: ("rate-limit-exceeded", "Rate Limit Exceeded"),
    500: ("internal-server-error", "Internal Server Error"),
    502: ("bad-gateway", "Bad Gateway"),
    503: ("service-unavailable", "Service Unavailable"),
    504: ("gateway-timeout", "Gateway Timeout"),
}


def problem_type_uri(slug: str) -> str:
    """Return a stable RFC 9457 type URI under the reserved ``.invalid`` TLD."""
    if _PROBLEM_TYPE_SLUG.fullmatch(slug) is None:
        raise ValueError("Problem type slugs must be lowercase kebab-case")
    return f"{PROBLEM_TYPE_BASE_URI}{slug}"


def _type_uri_for_status(status: int) -> str:
    slug, _ = _STATUS_MAP.get(status, ("error", "Error"))
    return problem_type_uri(slug)


def _title_for_status(status: int) -> str:
    _, title = _STATUS_MAP.get(status, ("error", "Error"))
    return title


class ProblemDetail(BaseModel):
    """RFC 9457 Problem Details response body."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: str | None = None
    request_id: str | None = None  # extension field


class APIError(Exception):
    """Raise in route handlers for RFC 9457 error responses."""

    def __init__(
        self,
        status: int,
        title: str,
        detail: str,
        *,
        type_uri: str | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        self.status = status
        self.title = title
        self.detail = detail
        # Derive a canonical type URI when the caller has not supplied one.
        self.type_uri = type_uri if type_uri is not None else _type_uri_for_status(status)
        self.retry_after_seconds = retry_after_seconds
        super().__init__(detail)


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """Convert APIError to RFC 9457 Problem Details JSON response."""
    response = JSONResponse(
        status_code=exc.status,
        content=ProblemDetail(
            type=exc.type_uri,
            title=exc.title,
            status=exc.status,
            detail=exc.detail,
            instance=str(request.url.path),
            request_id=getattr(request.state, "request_id", None),
        ).model_dump(),
        media_type="application/problem+json",
    )
    if exc.retry_after_seconds is not None:
        response.headers["Retry-After"] = str(exc.retry_after_seconds)
    return response


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Convert FastAPI/Starlette HTTPException to RFC 9457 Problem Details JSON response."""
    status = exc.status_code
    detail_str = str(exc.detail) if exc.detail is not None else _title_for_status(status)
    response = JSONResponse(
        status_code=status,
        content=ProblemDetail(
            type=_type_uri_for_status(status),
            title=_title_for_status(status),
            status=status,
            detail=detail_str,
            instance=str(request.url.path),
            request_id=getattr(request.state, "request_id", None),
        ).model_dump(),
        media_type="application/problem+json",
    )
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def rate_limit_exceeded_handler(request: Request, exc: _RateLimitExceeded) -> JSONResponse:
    """Convert slowapi RateLimitExceeded to an RFC 9457 Problem Details JSON response.

    slowapi's default handler returns plain-text ``429 Too Many Requests``.
    This handler ensures the rate-limit path honours the application/problem+json
    contract the same as every other error path.
    """
    detail_str = str(exc.detail) if hasattr(exc, "detail") and exc.detail else "Rate limit exceeded"
    response = JSONResponse(
        status_code=429,
        content=ProblemDetail(
            type=_type_uri_for_status(429),
            title=_title_for_status(429),
            status=429,
            detail=detail_str,
            instance=str(request.url.path),
            request_id=getattr(request.state, "request_id", None),
        ).model_dump(),
        media_type="application/problem+json",
    )
    # Prefer the Retry-After slowapi already computed; fall back to 60 s.
    retry_after = "60"
    if hasattr(exc, "headers") and exc.headers:
        retry_after = exc.headers.get("Retry-After", "60")
    response.headers["Retry-After"] = retry_after
    return response


def _sanitise_validation_errors(errors: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return a copy of Pydantic error dicts with all values coerced to JSON-safe types.

    Pydantic model-validator errors can carry live Python objects (e.g. ``ValueError``)
    in the ``ctx`` sub-dict.  ``JSONResponse`` uses the stdlib JSON encoder which
    cannot serialise those objects, so they must be converted to strings first.
    """
    safe: list[dict[str, Any]] = []
    for err in errors:
        entry = {k: v for k, v in err.items() if k != "ctx"}
        if "ctx" in err:
            entry["ctx"] = {ck: str(cv) for ck, cv in err["ctx"].items()}
        safe.append(entry)
    return safe


async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Convert Pydantic RequestValidationError (422) to an RFC 9457 Problem Details JSON response.

    FastAPI's built-in handler for this exception type returns application/json.
    This handler replaces it so the 422 path also honours application/problem+json.
    The individual validation errors are included as an extension field.
    """
    return JSONResponse(
        status_code=422,
        content=ProblemDetail(
            type=_type_uri_for_status(422),
            title=_title_for_status(422),
            status=422,
            detail="Request body or query parameters failed validation",
            instance=str(request.url.path),
            request_id=getattr(request.state, "request_id", None),
        ).model_dump()
        | {"errors": _sanitise_validation_errors(exc.errors())},
        media_type="application/problem+json",
    )


# ---------------------------------------------------------------------------
# Deprecation / Sunset header helpers  (RFC 8594 + draft-ietf-httpapi-deprecation-header)
# ---------------------------------------------------------------------------


def add_deprecation_headers(
    response: JSONResponse,
    *,
    sunset_date: str | None = None,
    link: str | None = None,
) -> JSONResponse:
    """Attach RFC 8594 ``Sunset`` and deprecation headers to a response.

    Args:
        response:    The JSONResponse to annotate.
        sunset_date: HTTP-date string for the ``Sunset`` header (RFC 8594),
                     e.g. ``"Sat, 01 Jan 2028 00:00:00 GMT"``.
        link:        URL of the replacement endpoint to include as a
                     ``Link: <url>; rel="successor-version"`` header.

    Returns the same response object (mutated in-place) for chaining.

    Usage in a route handler::

        from api.errors import add_deprecation_headers

        @router.get("/v1/old-endpoint")
        async def old_endpoint():
            response = JSONResponse(content={...})
            return add_deprecation_headers(
                response,
                sunset_date="Sat, 01 Jan 2028 00:00:00 GMT",
                link="https://api.example.invalid/v2/new-endpoint",
            )
    """
    response.headers["Deprecation"] = "true"
    if sunset_date:
        response.headers["Sunset"] = sunset_date
    if link:
        response.headers["Link"] = f'<{link}>; rel="successor-version"'
    return response
