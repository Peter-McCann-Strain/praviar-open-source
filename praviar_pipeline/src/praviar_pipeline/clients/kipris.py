"""KIPRIS Plus (Korea) patent API client — Korean patent search.

Provides access to the Korean Intellectual Property Rights Information Service
(KIPRIS Plus) for searching Korean patents by keywords or applicant name.
API returns XML responses; authentication via ServiceKey query parameter.
Request pacing follows the operator-configured local cap.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from urllib.parse import quote

import httpx
import structlog
from aiolimiter import AsyncLimiter
from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring
from tenacity import (
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from praviar_pipeline.clients.base import AsyncClientMixin
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import AuthenticationError, SourceUnavailableError

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element

logger = structlog.get_logger()

BASE_URL = "https://plus.kipris.or.kr/kipo-api/kipi"


class KIPRISClient(AsyncClientMixin):
    """Async client for the KIPRIS Plus REST API.

    Searches Korean patent data by keyword or applicant name.
    Requires a ServiceKey from plus.kipris.or.kr.
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._external_client = client is not None
        settings = get_settings()
        self._api_key = settings.kipris_api_key
        self._max_results = settings.kipris_max_results

        if not self._api_key:
            logger.warning(
                "kipris_disabled",
            )
        else:
            logger.debug("kipris_client_init", status="enabled")

        self._client = client or httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=httpx.Timeout(
                settings.http_timeout_default, connect=settings.http_connect_timeout
            ),
            limits=httpx.Limits(
                max_connections=settings.http_max_connections,
                max_keepalive_connections=settings.http_max_keepalive,
            ),
        )
        self._limiter = AsyncLimiter(
            max_rate=settings.kipris_requests_per_minute,
            time_period=60,
        )

    async def close(self) -> None:
        if not self._external_client:
            await self._client.aclose()

    async def _get_and_parse(self, path: str, params: dict[str, str]) -> list[dict]:
        """Rate-limited GET request to KIPRIS + XML parse.

        Returns the parsed list of patent dicts. Wrapping at the parsed-list
        level (rather than raw XML) means only successful XML-parsed results
        are recorded — :class:`SourceUnavailableError` raised by
        :meth:`_parse_items` on malformed XML propagates unrecorded so replay
        doesn't resurrect bad data. Cache hits bypass tenacity and the
        rate limiter — we only retry/limit live calls.
        """
        # Inline import — survives the aggressive format hook.
        import json

        from praviar_pipeline.response_cache import CacheMode, get_current_cache

        cache = get_current_cache()
        if cache is None or cache.mode == CacheMode.DISABLED:
            return await self._fetch_and_parse_uncached(path, params)
        # Build body from params minus the ServiceKey — we key on the
        # semantically-meaningful search params so a rotated key still hits
        # the same cache entry.
        keyed = {k: v for k, v in params.items() if k != "ServiceKey"}
        body = json.dumps(keyed, sort_keys=True)
        return await cache.wrap(
            source="kipris",
            method="GET",
            url=path,
            body=body,
            call=lambda: self._fetch_and_parse_uncached(path, params),
        )

    async def _fetch_and_parse_uncached(self, path: str, params: dict[str, str]) -> list[dict]:
        """Live HTTP GET + XML parse — retries via tenacity, never cached here."""
        xml_text = await self._get(path, params)
        return self._parse_items(xml_text)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10),
        retry=retry_if_not_exception_type(
            (AuthenticationError, asyncio.CancelledError, SourceUnavailableError)
        ),
    )
    async def _get(self, path: str, params: dict[str, str]) -> str:
        """Rate-limited GET request to KIPRIS. Returns raw XML text."""
        params["ServiceKey"] = quote(self._api_key, safe="")
        async with self._limiter:
            resp = await self._client.get(path, params=params)
            if resp.status_code in (401, 403):
                raise AuthenticationError(
                    "KIPRIS API key is invalid or missing",
                    source="kipris",
                )
            resp.raise_for_status()
            return resp.text

    def _parse_items(self, xml_text: str) -> list[dict]:
        """Parse KIPRIS XML response into a list of patent dicts.

        Expected structure: <response><body><items><item>...</item></items></body></response>

        Raises:
            SourceUnavailableError: If the XML cannot be parsed. A parse
                error indicates either API schema drift (we need to know)
                or genuine data corruption (we need to skip safely via the
                orchestrator's SourceHealthEntry(FAILED) path). Silently
                returning empty would mask both cases.
        """
        parse_failure_type: str | None = None
        try:
            root = fromstring(xml_text)
        except (ParseError, DefusedXmlException) as exc:
            parse_failure_type = type(exc).__name__
            logger.error(
                "kipris_xml_parse_error",
                error_type=parse_failure_type,
            )
        if parse_failure_type is not None:
            raise SourceUnavailableError(
                "kipris",
                "XML response could not be parsed safely",
            ) from None

        items: list[dict] = []
        for item in root.iter("item"):
            pub_number = (
                self._text(item, "applicationNumber")
                or self._text(item, "publicationNumber")
                or self._text(item, "registrationNumber")
                or ""
            )
            if pub_number and not pub_number.startswith("KR"):
                pub_number = f"KR{pub_number}"

            title = self._text(item, "inventionTitle") or self._text(item, "title") or ""
            abstract = self._text(item, "astrtCont") or self._text(item, "abstract") or ""
            filing_date = (
                self._text(item, "applicationDate") or self._text(item, "filingDate") or ""
            )
            applicant = self._text(item, "applicantName") or self._text(item, "applicant") or ""
            cpc = self._text(item, "cpcNumber") or self._text(item, "cpcCodes") or ""

            items.append(
                {
                    "publication_number": pub_number,
                    "title": title,
                    "abstract": abstract,
                    "filing_date": filing_date,
                    "assignees": [a.strip() for a in applicant.split("|") if a.strip()]
                    if applicant
                    else [],
                    "cpc_codes": [c.strip() for c in cpc.split("|") if c.strip()] if cpc else [],
                }
            )

        return items

    @staticmethod
    def _text(element: Element, tag: str) -> str | None:
        """Extract text from a child element, returning None if missing."""
        child = element.find(tag)
        if child is not None and child.text:
            return child.text.strip()
        return None

    async def search_patents(
        self, keywords: list[str], max_results: int | None = None
    ) -> list[dict]:
        """Search KIPRIS for patents by keywords.

        Args:
            keywords: List of search terms (space-joined for query).
            max_results: Max results to return. Falls back to config default.

        Returns:
            List of dicts with keys: publication_number, title, abstract,
            filing_date, assignees, cpc_codes.
        """
        if not self._api_key:
            logger.info("kipris_search_skipped")
            return []

        num_rows = max_results or self._max_results
        word = " ".join(keywords)

        logger.info(
            "kipris_search_patents",
            max_results=num_rows,
        )

        params = {
            "word": word,
            "numOfRows": str(num_rows),
            "pageNo": "1",
        }

        results = await self._get_and_parse(
            "/patUtiModInfoSearchSevice/getAdvancedSearch",
            params,
        )

        logger.info(
            "kipris_search_complete",
            results_count=len(results),
        )

        return results

    async def search_by_applicant(
        self, applicant: str, max_results: int | None = None
    ) -> list[dict]:
        """Search KIPRIS for patents by applicant name.

        Args:
            applicant: Applicant / assignee name to search.
            max_results: Max results to return. Falls back to config default.

        Returns:
            List of dicts with keys: publication_number, title, abstract,
            filing_date, assignees, cpc_codes.
        """
        if not self._api_key:
            logger.info("kipris_applicant_search_skipped")
            return []

        num_rows = max_results or self._max_results

        logger.info(
            "kipris_search_by_applicant",
            max_results=num_rows,
        )

        params = {
            "applicant": applicant,
            "numOfRows": str(num_rows),
            "pageNo": "1",
        }

        results = await self._get_and_parse(
            "/patUtiModInfoSearchSevice/getAdvancedSearch",
            params,
        )

        logger.info(
            "kipris_applicant_search_complete",
            results_count=len(results),
        )

        return results
