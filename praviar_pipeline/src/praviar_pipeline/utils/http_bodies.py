"""Bounded streaming primitives for untrusted HTTP response bodies."""

from __future__ import annotations

from typing import TYPE_CHECKING

from praviar_pipeline.errors import SourceUnavailableError

if TYPE_CHECKING:
    import httpx


async def read_bounded_response_body(
    response: httpx.Response,
    *,
    max_bytes: int,
    source: str,
    detail: str,
) -> bytes:
    """Read a streamed response body, rejecting declared or decoded overflow."""
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")

    declared_length = response.headers.get("Content-Length", "").strip()
    if declared_length:
        try:
            parsed_length = int(declared_length)
            if parsed_length < 0:
                raise ValueError
            if parsed_length > max_bytes:
                raise SourceUnavailableError(source, detail)
        except ValueError:
            raise SourceUnavailableError(source, "invalid Content-Length") from None

    body = bytearray()
    async for chunk in response.aiter_bytes():
        if len(body) + len(chunk) > max_bytes:
            raise SourceUnavailableError(source, detail)
        body.extend(chunk)
    return bytes(body)
