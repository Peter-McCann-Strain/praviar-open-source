"""Postmark email service facade for transactional emails."""

from __future__ import annotations

from typing import Any, Literal

import httpx
import structlog

from api.config import get_settings
from api.services.email_delivery import (
    send_email_impl,
    send_template_email_impl,
)
from api.services.email_messages import (
    build_analysis_complete_message,
    build_monitor_alert_message,
    build_weekly_digest_message,
    build_weekly_digest_text,
    build_welcome_message,
    weekly_digest_unsubscribe_urls,
)
from api.services.email_models import DeliveryLookupResult, DeliveryResult, DeliverySubmissionResult
from api.services.email_payloads import build_postmark_email_payload

logger = structlog.get_logger()

POSTMARK_API_URL = "https://api.postmarkapp.com"
POSTMARK_DIGEST_MESSAGE_STREAM = "broadcasts"


class PostmarkClient:
    """Thin async wrapper around the Postmark HTTP API."""

    def __init__(self) -> None:
        settings = get_settings()
        raw_api_token = getattr(settings, "postmark_api_token", "")
        raw_from_email = getattr(settings, "postmark_from_email", "")
        self._api_token = raw_api_token.strip() if isinstance(raw_api_token, str) else ""
        self._from_email = raw_from_email.strip() if isinstance(raw_from_email, str) else ""
        self._client: httpx.AsyncClient | None = None

    @property
    def is_configured(self) -> bool:
        """Return true only when the token and explicit verified sender are set."""
        return bool(self._api_token and self._from_email)

    async def _get_client(self) -> httpx.AsyncClient:
        """Return a reusable httpx client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=POSTMARK_API_URL,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-Postmark-Server-Token": self._api_token,
                },
                timeout=httpx.Timeout(10.0, connect=5.0),
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying httpx client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ── Core send methods ───────────────────────────────────────────────────

    async def send_email(
        self,
        to: str,
        subject: str,
        html_body: str,
        text_body: str | None = None,
        tag: str | None = None,
        message_stream: str | None = None,
        headers: list[dict[str, str]] | None = None,
    ) -> DeliveryResult:
        """Send a single email via Postmark.

        Returns a DeliveryResult with success status and message ID.
        Gracefully handles an incomplete token/sender pair by logging and skipping.
        """
        return await send_email_impl(
            is_configured=self.is_configured,
            from_email=self._from_email,
            to=to,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            tag=tag,
            message_stream=message_stream,
            headers=headers,
            get_client_fn=self._get_client,
            logger=logger,
        )

    async def submit_email_once(
        self,
        *,
        to: str,
        subject: str,
        html_body: str,
        text_body: str | None = None,
        tag: str | None = None,
        message_stream: str | None = None,
        headers: list[dict[str, str]] | None = None,
        submission_id: str,
    ) -> DeliverySubmissionResult:
        """Submit exactly once and classify ambiguous transport outcomes.

        Postmark does not expose a send idempotency key. A network error or 5xx
        must not be resent; the metadata lookup path reconciles it later.
        """
        if not self.is_configured:
            return DeliverySubmissionResult(
                status="rejected",
                error="Postmark sender configuration is incomplete",
            )
        payload = build_postmark_email_payload(
            from_email=self._from_email,
            to=to,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            tag=tag,
            message_stream=message_stream,
            headers=headers,
        )
        try:
            client = await self._get_client()
            response = await client.post(
                "/email",
                json={**payload, "Metadata": {"submission_id": submission_id}},
            )
            if 400 <= response.status_code < 500:
                logger.warning(
                    "email_submission_rejected",
                    recipient_domain=to.rpartition("@")[2].casefold(),
                    status_code=response.status_code,
                    tag=tag,
                )
                return DeliverySubmissionResult(
                    status="rejected",
                    error=f"Postmark rejected submission ({response.status_code})",
                )
            if response.status_code >= 500:
                logger.error(
                    "email_submission_outcome_unknown",
                    recipient_domain=to.rpartition("@")[2].casefold(),
                    status_code=response.status_code,
                    tag=tag,
                )
                return DeliverySubmissionResult(
                    status="outcome_unknown",
                    error="Postmark submission outcome is unknown",
                )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                return DeliverySubmissionResult(
                    status="outcome_unknown",
                    error="Postmark submission response could not be confirmed",
                )
            error_code = data.get("ErrorCode")
            if isinstance(error_code, bool) or not isinstance(error_code, int):
                return DeliverySubmissionResult(
                    status="outcome_unknown",
                    error="Postmark submission response could not be confirmed",
                )
            if error_code != 0:
                return DeliverySubmissionResult(
                    status="rejected",
                    error=f"Postmark rejected submission ({error_code})",
                )
            raw_message_id = data.get("MessageID")
            message_id = raw_message_id.strip() if isinstance(raw_message_id, str) else ""
            if not message_id:
                return DeliverySubmissionResult(
                    status="outcome_unknown",
                    error="Postmark submission response could not be confirmed",
                )
            logger.info(
                "email_submission_accepted",
                recipient_domain=to.rpartition("@")[2].casefold(),
                tag=tag,
                message_id=message_id,
            )
            return DeliverySubmissionResult(status="accepted", message_id=message_id)
        except httpx.HTTPStatusError as exc:
            # Defensive classification for unusual non-2xx responses not
            # covered above. A response exists, but 5xx remains ambiguous.
            status_code = exc.response.status_code
            status: Literal["rejected", "outcome_unknown"] = (
                "rejected" if 400 <= status_code < 500 else "outcome_unknown"
            )
            return DeliverySubmissionResult(
                status=status,
                error=f"Postmark submission failed ({status_code})",
            )
        except httpx.HTTPError as exc:
            logger.error(
                "email_submission_outcome_unknown",
                recipient_domain=to.rpartition("@")[2].casefold(),
                error_type=type(exc).__name__,
                tag=tag,
                exc_info=True,
            )
            return DeliverySubmissionResult(
                status="outcome_unknown",
                error="Postmark submission outcome is unknown",
            )
        except (TypeError, ValueError) as exc:
            logger.error(
                "email_submission_outcome_unknown",
                recipient_domain=to.rpartition("@")[2].casefold(),
                error_type=type(exc).__name__,
                tag=tag,
                exc_info=True,
            )
            return DeliverySubmissionResult(
                status="outcome_unknown",
                error="Postmark submission response could not be confirmed",
            )

    async def lookup_outbound_submission(
        self,
        *,
        submission_id: str,
        expected_to: str,
        expected_subject: str,
        expected_tag: str,
        message_stream: str | None = None,
    ) -> DeliveryLookupResult:
        """Resolve an ambiguous submit through Postmark's metadata search."""
        if not self.is_configured:
            return DeliveryLookupResult(status="unavailable", detail="provider not configured")
        try:
            client = await self._get_client()
            params: dict[str, str | int] = {
                "count": 10,
                "offset": 0,
                "metadata_submission_id": submission_id,
            }
            if message_stream is not None:
                params["messagestream"] = message_stream
            response = await client.get("/messages/outbound", params=params)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError:
            logger.error("email_submission_lookup_unavailable", exc_info=True)
            return DeliveryLookupResult(status="unavailable", detail="provider lookup failed")
        except (TypeError, ValueError):
            logger.error("email_submission_lookup_malformed", exc_info=True)
            return DeliveryLookupResult(status="alert", detail="provider lookup was malformed")

        if not isinstance(payload, dict):
            return DeliveryLookupResult(status="alert", detail="provider lookup was malformed")
        total = payload.get("TotalCount")
        messages = payload.get("Messages")
        if isinstance(total, bool) or not isinstance(total, int) or not isinstance(messages, list):
            return DeliveryLookupResult(status="alert", detail="provider lookup was malformed")
        if total == 0 and messages == []:
            return DeliveryLookupResult(status="not_found")
        if total != 1 or len(messages) != 1 or not isinstance(messages[0], dict):
            return DeliveryLookupResult(status="alert", detail="provider lookup was not unique")

        message = messages[0]
        metadata = message.get("Metadata")
        message_id = message.get("MessageID")
        to_entries = message.get("To")
        recipients = message.get("Recipients")
        cc_entries = message.get("Cc", [])
        bcc_entries = message.get("Bcc", [])
        exact_to = (
            isinstance(to_entries, list)
            and len(to_entries) == 1
            and isinstance(to_entries[0], dict)
            and isinstance(to_entries[0].get("Email"), str)
            and to_entries[0]["Email"].casefold() == expected_to.casefold()
        )
        exact_recipients = (
            isinstance(recipients, list)
            and len(recipients) == 1
            and isinstance(recipients[0], str)
            and recipients[0].casefold() == expected_to.casefold()
        )
        status_value = message.get("Status")
        exact = (
            isinstance(metadata, dict)
            and metadata == {"submission_id": submission_id}
            and exact_to
            and exact_recipients
            and cc_entries == []
            and bcc_entries == []
            and message.get("Subject") == expected_subject
            and message.get("Tag") == expected_tag
            and (message_stream is None or message.get("MessageStream") == message_stream)
            and isinstance(status_value, str)
            and status_value.casefold() in {"queued", "sent", "processed"}
            and isinstance(message_id, str)
            and bool(message_id.strip())
        )
        if not exact:
            return DeliveryLookupResult(
                status="alert",
                detail="provider lookup identity did not match the delivery",
            )
        assert isinstance(message_id, str)
        return DeliveryLookupResult(status="found", message_id=message_id.strip())

    async def send_template_email(
        self,
        to: str,
        template_alias: str,
        template_model: dict[str, Any],
    ) -> DeliveryResult:
        """Send a templated email via Postmark server-side templates.

        Uses Postmark's template API for emails managed in the Postmark dashboard.
        """
        return await send_template_email_impl(
            is_configured=self.is_configured,
            from_email=self._from_email,
            to=to,
            template_alias=template_alias,
            template_model=template_model,
            get_client_fn=self._get_client,
            logger=logger,
        )

    # ── Convenience methods ─────────────────────────────────────────────────

    async def send_analysis_complete(
        self,
        user_email: str,
        user_name: str,
        analysis_id: str,
        compound_name: str,
        risk_level: str,
        report_cta_label: str,
        report_url: str,
        risk_restricted: bool,
    ) -> DeliveryResult:
        """Send analysis-complete notification email."""
        subject, html, tag = build_analysis_complete_message(
            user_name=user_name,
            compound_name=compound_name,
            risk_level=risk_level,
            report_cta_label=report_cta_label,
            report_url=report_url,
            risk_restricted=risk_restricted,
        )
        return await self.send_email(
            to=user_email,
            subject=subject,
            html_body=html,
            tag=tag,
        )

    async def send_monitor_alert(
        self,
        user_email: str,
        user_name: str,
        compound_name: str,
        new_patent_count: int,
        monitor_url: str,
        new_event_ids: list[str] | None = None,
        affected_conclusions: list[dict] | None = None,
    ) -> DeliveryResult:
        """Send a patent or patent-event monitor alert email."""
        subject, html, tag = build_monitor_alert_message(
            user_name=user_name,
            compound_name=compound_name,
            new_patent_count=new_patent_count,
            monitor_url=monitor_url,
            new_event_ids=new_event_ids,
            affected_conclusions=affected_conclusions,
        )
        return await self.send_email(
            to=user_email,
            subject=subject,
            html_body=html,
            tag=tag,
        )

    async def send_welcome(
        self,
        user_email: str,
        user_name: str,
        role: str,
    ) -> DeliveryResult:
        """Send welcome email to new users."""
        subject, html, tag = build_welcome_message(
            user_name=user_name,
            role=role,
        )
        return await self.send_email(
            to=user_email,
            subject=subject,
            html_body=html,
            tag=tag,
        )

    async def submit_weekly_digest_once(
        self,
        *,
        user_email: str,
        user_name: str,
        analyses_completed: int,
        alerts_count: int,
        top_risks: list[dict[str, str]],
        unsubscribe_token: str,
        submission_id: str,
        risk_restricted: bool = False,
    ) -> DeliverySubmissionResult:
        """Submit one weekly digest without transport-level resubmission."""
        subject, html, tag = build_weekly_digest_message(
            user_name=user_name,
            analyses_completed=analyses_completed,
            alerts_count=alerts_count,
            top_risks=top_risks,
            risk_restricted=risk_restricted,
            unsubscribe_token=unsubscribe_token,
        )
        text = build_weekly_digest_text(
            user_name=user_name,
            analyses_completed=analyses_completed,
            alerts_count=alerts_count,
            top_risks=top_risks,
            risk_restricted=risk_restricted,
            unsubscribe_token=unsubscribe_token,
        )
        one_click_url = weekly_digest_unsubscribe_urls(unsubscribe_token)["one_click_url"]
        return await self.submit_email_once(
            to=user_email,
            subject=subject,
            html_body=html,
            text_body=text,
            tag=tag,
            message_stream=POSTMARK_DIGEST_MESSAGE_STREAM,
            headers=[
                {
                    "Name": "List-Unsubscribe",
                    "Value": f"<{one_click_url}>",
                },
                {
                    "Name": "List-Unsubscribe-Post",
                    "Value": "List-Unsubscribe=One-Click",
                },
            ],
            submission_id=submission_id,
        )

    async def lookup_weekly_digest_submission(
        self,
        *,
        submission_id: str,
        expected_to: str,
    ) -> DeliveryLookupResult:
        """Reconcile one deterministic weekly digest submission."""
        return await self.lookup_outbound_submission(
            submission_id=submission_id,
            expected_to=expected_to,
            expected_subject="Your Praviar Weekly Summary",
            expected_tag="weekly_digest",
            message_stream=POSTMARK_DIGEST_MESSAGE_STREAM,
        )


# Module-level singleton — reused across the application
_client: PostmarkClient | None = None


def get_email_client() -> PostmarkClient:
    """Return a module-level PostmarkClient singleton."""
    global _client  # noqa: PLW0603
    if _client is None:
        _client = PostmarkClient()
    return _client
