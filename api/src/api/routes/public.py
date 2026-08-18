"""Public, unauthenticated routes."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Request, Response

from api.client_ip import get_client_ip
from api.errors import APIError, problem_type_uri
from api.ratelimit import (
    limiter,
    public_share_challenge_rate_limit_key,
    public_share_rate_limit_key,
)
from api.schemas.common import SharedReportResponse
from api.schemas.reports import (
    ExternalGrantChallengeResponse,
    ExternalGrantVerificationRequest,
    ExternalGrantVerificationResponse,
)
from api.services.external_report_grants import (
    ACCESS_SECRET_HEADER,
    fetch_authorized_shared_analysis,
    issue_external_grant_challenge,
    verify_external_grant_challenge,
)
from api.services.public_reports import (
    build_shared_report_payload,
)
from api.services.system_health import collect_health_detail, collect_readiness_errors

router = APIRouter()
logger = structlog.get_logger()

_PROBLEM_4XX = {
    "404": {
        "description": "Not found",
        "content": {"application/problem+json": {"schema": {"type": "object"}}},
    },
    "429": {
        "description": "Rate limit exceeded",
        "content": {"application/problem+json": {"schema": {"type": "object"}}},
    },
}


@router.get(
    "/share/{token}",
    response_model=SharedReportResponse,
    openapi_extra={"responses": _PROBLEM_4XX},
)
@limiter.limit("10/minute", key_func=public_share_rate_limit_key)
async def get_shared_report(token: str, request: Request, response: Response) -> dict:
    """Return a report only with a live recipient-verification proof."""
    from api.db.session import async_session_factory

    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    forbidden_query_keys = {
        key.casefold()
        for key in request.query_params
        if key.casefold()
        in {
            "access_secret",
            "code",
            "password",
        }
    }
    if forbidden_query_keys:
        raise APIError(400, "Bad Request", "Access secrets are not accepted in URLs")
    access_secret = request.headers.get(ACCESS_SECRET_HEADER, "")
    analysis = await fetch_authorized_shared_analysis(
        token,
        access_secret=access_secret,
        async_session_factory_fn=async_session_factory,
        ip_address=get_client_ip(request) if request.client else "",
    )
    payload = build_shared_report_payload(analysis)

    logger.info(
        "shared_report_served",
        analysis_id=str(analysis.id),
        org_id=str(analysis.org_id),
        recipient_verified=True,
    )
    return payload


@router.post(
    "/share/{token}/challenge",
    response_model=ExternalGrantChallengeResponse,
    openapi_extra={"responses": _PROBLEM_4XX},
)
@limiter.limit("3/hour", key_func=public_share_challenge_rate_limit_key)
async def request_shared_report_verification(
    token: str,
    request: Request,
    response: Response,
) -> dict:
    """Send a code to the bound mailbox without revealing its identity."""
    from api.db.session import async_session_factory

    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    await issue_external_grant_challenge(
        token,
        async_session_factory_fn=async_session_factory,
    )
    return {"status": "verification_sent"}


@router.post(
    "/share/{token}/verify",
    response_model=ExternalGrantVerificationResponse,
    openapi_extra={"responses": _PROBLEM_4XX},
)
@limiter.limit("10/minute", key_func=public_share_rate_limit_key)
async def verify_shared_report_recipient(
    token: str,
    body: ExternalGrantVerificationRequest,
    request: Request,
    response: Response,
) -> dict:
    """Consume a one-time code and return a short-lived access secret."""
    from api.db.session import async_session_factory

    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    access_secret, access_expires_at = await verify_external_grant_challenge(
        token,
        code=body.code,
        async_session_factory_fn=async_session_factory,
    )
    return {
        "access_secret": access_secret,
        "access_expires_at": access_expires_at,
    }


@router.get("/api/health")
async def health_check() -> dict:
    """Live health check — reports API process status and dependency health.

    Always returns HTTP 200.  The "status" field is "ok" when all dependency
    probes pass within the 100 ms timeout, and "degraded" when one or more
    are slow or unreachable.  This endpoint must never itself fail with 5xx —
    a degraded dependency is reported in the response body so load balancers
    and uptime monitors keep the instance alive while operators investigate.

    Response shape::

        {
            "status": "ok" | "degraded",
            "version": "<release>",
            "checks": {
                "database": "ok" | "degraded" | "error",
                "redis":    "ok" | "degraded" | "error"
            },
            "latency_ms": {
                "database": 4.2,
                "redis":    1.8
            }
        }
    """
    import redis.asyncio as aioredis

    from api.cache import redis_connection_kwargs
    from api.config import get_settings
    from api.db.session import async_session_factory

    settings = get_settings()
    detail = await collect_health_detail(
        redis_url=settings.redis_url,
        async_session_factory_fn=async_session_factory,
        redis_from_url_fn=aioredis.from_url,
        logger=logger,
        redis_connection_kwargs=redis_connection_kwargs(settings),
    )
    return {"version": settings.release_version, **detail}


@router.get("/api/health/ready")
async def readiness_check() -> Response:
    """Deep readiness check — verifies DB and Redis connectivity.

    Deprecated: Cloud Run startup probes (configured in cloud-run.tf) supersede
    this endpoint for deployment readiness. Scheduled sunset 2027-01-01.
    """
    import redis.asyncio as aioredis
    from fastapi.responses import JSONResponse

    from api.cache import redis_connection_kwargs
    from api.config import get_settings
    from api.db.session import async_session_factory
    from api.errors import add_deprecation_headers

    settings = get_settings()
    errors = await collect_readiness_errors(
        redis_url=settings.redis_url,
        async_session_factory_fn=async_session_factory,
        redis_from_url_fn=aioredis.from_url,
        logger=logger,
        redis_connection_kwargs=redis_connection_kwargs(settings),
    )
    _sunset = "Thu, 01 Jan 2027 00:00:00 GMT"
    _link = "/api/health"
    if errors:
        from api.errors import ProblemDetail

        error_response = JSONResponse(
            status_code=503,
            content=ProblemDetail(
                type=problem_type_uri("service-unavailable"),
                title="Service Unavailable",
                status=503,
                detail=f"Health check failed: {'; '.join(errors)}",
            ).model_dump(),
            media_type="application/problem+json",
        )
        return add_deprecation_headers(error_response, sunset_date=_sunset, link=_link)
    response = JSONResponse({"status": "ready", "version": settings.release_version})
    return add_deprecation_headers(response, sunset_date=_sunset, link=_link)
