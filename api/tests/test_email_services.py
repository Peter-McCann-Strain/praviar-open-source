"""Focused tests for Postmark email service helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from api.services.email import PostmarkClient, get_email_client
from api.services.email_messages import (
    build_analysis_complete_message,
    build_monitor_alert_message,
    build_weekly_digest_message,
    build_welcome_message,
)
from api.services.email_models import DeliverySubmissionResult
from api.services.email_payloads import (
    build_postmark_email_payload,
    build_postmark_template_payload,
)
from api.templates.emails import (
    render_analysis_complete,
    render_monitor_alert,
    render_weekly_digest,
    render_welcome,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PALETTE = json.loads((REPO_ROOT / "brand/praviar-palette.json").read_text())
CANONICAL_MARK_PATHS = re.findall(
    r'<path d="([^"]+)"',
    (REPO_ROOT / "web/public/brand/praviar-mark.svg").read_text(),
)

PREMIUM_EMAIL_HEXES = [
    PALETTE["core"]["ink"],
    PALETTE["support"]["deepTeal"],
    PALETTE["core"]["forensicTeal"],
    PALETTE["core"]["clinicalMint"],
    PALETTE["core"]["clinicalCopper"],
    PALETTE["core"]["softMint"],
    PALETTE["core"]["paper"],
]

RETIRED_EMAIL_HEXES = [
    "#818CF8",
    "#A78BFA",
    "#6366F1",
    "#EEF2FF",
    "#1F4A7A",
    "#F4F4F7",
    "#F9FAFB",
    "#E8E8EB",
    "#FFFFFF",
    "#8B1F1B",
]


def _render_premium_email_templates() -> dict[str, str]:
    return {
        "analysis_complete": render_analysis_complete(
            user_name="Ada",
            compound_name="aspirin",
            risk_level="high",
            report_url="https://app.example.com/reports/1",
        ),
        "monitor_alert": render_monitor_alert(
            user_name="Ada",
            compound_name="aspirin",
            new_patent_count=2,
            monitor_url="https://app.example.com/monitors/1",
        ),
        "welcome": render_welcome(
            user_name="Ada",
            dashboard_url="https://app.example.com",
        ),
        "weekly_digest": render_weekly_digest(
            user_name="Ada",
            analyses_completed=3,
            alerts_count=2,
            top_risks=[{"compound_name": "aspirin", "risk_level": "medium"}],
            dashboard_url="https://app.example.com/dashboard",
        ),
    }


def test_build_postmark_email_payload_omits_optional_fields_when_empty():
    payload = build_postmark_email_payload(
        from_email="noreply@example.invalid",
        to="user@example.com",
        subject="Hello",
        html_body="<p>Hi</p>",
    )

    assert payload == {
        "From": "noreply@example.invalid",
        "To": "user@example.com",
        "Subject": "Hello",
        "HtmlBody": "<p>Hi</p>",
    }


def test_build_postmark_template_payload_includes_alias_and_model():
    payload = build_postmark_template_payload(
        from_email="noreply@example.invalid",
        to="user@example.com",
        template_alias="welcome",
        template_model={"name": "Ada"},
    )

    assert payload["TemplateAlias"] == "welcome"
    assert payload["TemplateModel"] == {"name": "Ada"}


def test_build_monitor_alert_message_pluralizes_subject():
    subject, _html, tag = build_monitor_alert_message(
        user_name="Ada",
        compound_name="aspirin",
        new_patent_count=2,
        monitor_url="https://app.example.com/monitors/1",
    )

    assert subject == "Patent Alert: 2 new patents for aspirin"
    assert tag == "monitor_alert"


def test_build_monitor_alert_message_describes_event_only_activity():
    subject, html, tag = build_monitor_alert_message(
        user_name="Ada",
        compound_name="aspirin",
        new_patent_count=0,
        new_event_ids=[
            "US12345678B2:assignment:2026-07-23",
            "US12345678B2:legal-status:2026-07-24",
        ],
        monitor_url="https://app.example.com/monitors/1",
    )

    assert subject == "Patent Alert: 2 new patent events for aspirin"
    assert "0 new patents" not in subject
    assert "2 new patent events" in html
    assert "US12345678B2:assignment:2026-07-23" in html
    assert "US12345678B2:legal-status:2026-07-24" in html
    assert "Review Patent Activity" in html
    assert tag == "monitor_alert"


def test_monitor_alert_event_references_are_escaped():
    _subject, html, _tag = build_monitor_alert_message(
        user_name="Ada",
        compound_name="aspirin",
        new_patent_count=0,
        new_event_ids=["<script>alert(1)</script>"],
        monitor_url="https://app.example.com/monitors/1",
    )

    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_monitor_alert_leads_with_affected_conclusions_and_reassessment_action():
    subject, html, tag = build_monitor_alert_message(
        user_name="Ada",
        compound_name="aspirin",
        new_patent_count=1,
        affected_conclusions=[
            {
                "conclusion_id": "clearance:US",
                "label": "US FTO clearance",
                "previous_outcome": "clear",
            }
        ],
        monitor_url="https://app.example.com/monitors/1",
    )

    assert subject == "Counsel reassessment required: 1 conclusion for aspirin"
    assert "Counsel reassessment required" in html
    assert "US FTO clearance" in html
    assert "previously clear" in html
    assert "Do not rely on the prior conclusion" in html
    assert "Review Affected Conclusions" in html
    assert tag == "monitor_alert"


def test_build_analysis_complete_message_sets_expected_subject_and_tag():
    subject, _html, tag = build_analysis_complete_message(
        user_name="Ada",
        compound_name="aspirin",
        risk_level="high",
        report_cta_label="View Full Report",
        report_url="https://app.example.com/reports/1",
        risk_restricted=False,
    )

    assert subject == "FTO Analysis Complete: aspirin"
    assert tag == "analysis_complete"


def test_build_analysis_complete_message_uses_generic_restricted_subject():
    subject, html, tag = build_analysis_complete_message(
        user_name="Scientist",
        compound_name="Governed analysis",
        risk_level="COUNSEL ONLY",
        report_cta_label="View Governed Summary",
        report_url="https://app.example.com/analyses/1/report/summary",
        risk_restricted=True,
    )

    assert subject == "Your Praviar analysis is ready"
    assert "Assessment access" in html
    assert "View Governed Summary" in html
    assert "Compound" not in html
    assert tag == "analysis_complete"


def test_message_builders_make_app_relative_ctas_absolute():
    settings = MagicMock(app_url="https://app.praviar.io/")
    with patch("api.services.email_messages.get_settings", return_value=settings):
        _subject, analysis_html, _tag = build_analysis_complete_message(
            user_name="Scientist",
            compound_name="Governed analysis",
            risk_level="COUNSEL ONLY",
            report_cta_label="View Governed Summary",
            report_url="/analyses/1/report/summary",
            risk_restricted=True,
        )
        _subject, monitor_html, _tag = build_monitor_alert_message(
            user_name="Ada",
            compound_name="aspirin",
            new_patent_count=1,
            monitor_url="/monitors",
        )
        _subject, welcome_html, _tag = build_welcome_message(
            user_name="Ada",
            role="attorney",
        )
        _subject, digest_html, _tag = build_weekly_digest_message(
            user_name="Ada",
            analyses_completed=2,
            alerts_count=1,
            top_risks=[],
            unsubscribe_token="signed.token",
        )

    assert 'href="https://app.praviar.io/analyses/1/report/summary"' in analysis_html
    assert 'href="https://app.praviar.io/monitors"' in monitor_html
    assert 'href="https://app.praviar.io/dashboard"' in welcome_html
    assert 'href="https://app.praviar.io/dashboard"' in digest_html
    assert 'href="https://app.praviar.io/unsubscribe/digest?token=signed.token"' in digest_html
    assert 'href="#"' not in welcome_html
    assert 'href="#"' not in digest_html


def test_restricted_analysis_template_overrides_unsafe_display_arguments():
    html = render_analysis_complete(
        user_name="Scientist",
        compound_name="Secret compound",
        risk_level="HIGH",
        report_cta_label="View Full Report",
        report_url="https://app.example.com/analyses/1/report/summary",
        risk_restricted=True,
    )

    assert "Secret compound" not in html
    assert ">HIGH<" not in html
    assert "Governed analysis" in html
    assert "COUNSEL ONLY" in html
    assert "View Governed Summary" in html


def test_weekly_digest_hides_risk_rows_for_restricted_recipients():
    html = render_weekly_digest(
        user_name="Scientist",
        analyses_completed=3,
        alerts_count=1,
        top_risks=[{"compound_name": "aspirin", "risk_level": "HIGH"}],
        risk_restricted=True,
    )

    assert ">Counsel<" in html
    assert ">Only<" in html
    assert "praviar-digest-metric" in html
    assert "Top Risks This Week" not in html
    assert ">aspirin<" not in html
    assert ">0<" not in html


def test_restricted_analysis_uses_neutral_counsel_only_badge():
    html = render_analysis_complete(
        user_name="Scientist",
        compound_name="Secret compound",
        risk_level="HIGH",
        report_url="https://app.example.com/analyses/1/report/summary",
        risk_restricted=True,
    )

    assert "background-color:#F1F3F2" in html
    assert "border:1px solid #9AAEA8" in html
    assert (
        "border:1px solid #9AAEA8;font-size:13px;font-weight:600;"
        "color:#516F68;background-color:#F1F3F2"
    ) in html


def test_client_welcome_omits_capability_inappropriate_actions():
    html = render_welcome(
        user_name="Client",
        role="client",
        dashboard_url="https://app.example.com/dashboard",
    )

    assert "Open shared analyses" in html
    assert "Review governed summaries" in html
    assert "Run your first analysis" not in html
    assert "Review patent risks" not in html
    assert "Set up monitoring" not in html


def test_transactional_email_templates_use_premium_palette():
    html = "\n".join(_render_premium_email_templates().values()).upper()

    for brand_hex in [
        *PREMIUM_EMAIL_HEXES,
        "#8A4F1F",
        "#7F1D1D",
        PALETTE["support"]["riskHighWash"],
        PALETTE["support"]["riskMediumWash"],
    ]:
        assert brand_hex in html

    for retired_hex in RETIRED_EMAIL_HEXES:
        assert retired_hex not in html


@pytest.mark.parametrize("template_name", sorted(_render_premium_email_templates()))
def test_each_email_template_inherits_premium_lockup_and_palette(template_name: str):
    html = _render_premium_email_templates()[template_name].upper()

    for brand_hex in PREMIUM_EMAIL_HEXES:
        assert brand_hex in html

    for retired_hex in RETIRED_EMAIL_HEXES:
        assert retired_hex not in html

    assert "FTO SCREENING" in html
    assert "EVIDENCE-LED PATENT RISK, READY FOR REVIEW." in html


def test_email_layout_uses_premium_brand_lockup():
    html = render_welcome(user_name="Ada", dashboard_url="https://app.example.com")

    assert "FTO Screening" in html
    assert "Evidence-led patent risk, ready for review." in html
    assert 'data-praviar-mark="praviar-evidence-mark"' in html
    assert 'aria-label="Praviar evidence mark"' in html
    assert "width:52px;height:52px" in html
    for path in CANONICAL_MARK_PATHS:
        assert path in html


def test_email_risk_badges_remain_visibly_badged():
    html = "\n".join(
        [
            render_analysis_complete(
                user_name="Ada",
                compound_name="aspirin",
                risk_level="high",
                report_url="https://app.example.com/reports/1",
            ),
            render_weekly_digest(
                user_name="Ada",
                analyses_completed=3,
                alerts_count=2,
                top_risks=[{"compound_name": "aspirin", "risk_level": "medium"}],
                dashboard_url="https://app.example.com/dashboard",
            ),
        ]
    )

    assert f"background-color:{PALETTE['support']['riskHighWash']}" in html
    assert f"background-color:{PALETTE['support']['riskMediumWash']}" in html
    assert f"border:1px solid {PALETTE['support']['clinicalRed']}" in html
    assert f"border:1px solid {PALETTE['core']['clinicalCopper']}" in html


@pytest.mark.asyncio
async def test_send_email_returns_error_when_postmark_not_configured():
    with patch("api.services.email.get_settings", return_value=MagicMock(postmark_api_token="")):
        client = PostmarkClient()

    result = await client.send_email(
        to="user@example.com",
        subject="Hello",
        html_body="<p>Hi</p>",
    )

    assert result.success is False
    assert result.error == "Postmark sender configuration is incomplete"


@pytest.mark.asyncio
async def test_send_email_fails_closed_when_token_has_no_explicit_sender():
    settings = MagicMock(
        postmark_api_token="pm_test",
        postmark_from_email="",
    )
    with patch("api.services.email.get_settings", return_value=settings):
        client = PostmarkClient()

    assert client.is_configured is False
    result = await client.send_email(
        to="user@example.com",
        subject="Hello",
        html_body="<p>Hi</p>",
    )

    assert result.success is False
    assert result.error == "Postmark sender configuration is incomplete"


@pytest.mark.asyncio
async def test_send_email_posts_payload_and_returns_message_id():
    settings = MagicMock(
        postmark_api_token="pm_test",
        postmark_from_email="noreply@example.invalid",
    )
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"MessageID": "msg_123"}
    http_client = AsyncMock()
    http_client.is_closed = False
    http_client.post = AsyncMock(return_value=response)

    with patch("api.services.email.get_settings", return_value=settings):
        client = PostmarkClient()
    client._client = http_client

    result = await client.send_email(
        to="user@example.com",
        subject="Hello",
        html_body="<p>Hi</p>",
        tag="welcome",
    )

    assert result.success is True
    assert result.message_id == "msg_123"
    http_client.post.assert_awaited_once()
    call_json = http_client.post.call_args.kwargs["json"]
    assert call_json["From"] == "noreply@example.invalid"
    assert call_json["To"] == "user@example.com"
    assert call_json["Subject"] == "Hello"
    assert call_json["HtmlBody"] == "<p>Hi</p>"
    assert call_json["Tag"] == "welcome"
    assert "send_id" in call_json.get("Metadata", {})


@pytest.mark.asyncio
async def test_weekly_digest_uses_broadcast_stream_multipart_and_one_click_headers():
    settings = MagicMock(
        app_url="https://app.praviar.io",
        postmark_api_token="pm_test",
        postmark_from_email="noreply@example.invalid",
    )
    with patch("api.services.email.get_settings", return_value=settings):
        client = PostmarkClient()

    with (
        patch("api.services.email_messages.get_settings", return_value=settings),
        patch.object(
            client,
            "submit_email_once",
            new=AsyncMock(
                return_value=DeliverySubmissionResult(
                    status="accepted",
                    message_id="digest-message",
                )
            ),
        ) as submit_email,
    ):
        await client.submit_weekly_digest_once(
            user_email="ada@example.com",
            user_name="Ada",
            analyses_completed=2,
            alerts_count=1,
            top_risks=[],
            unsubscribe_token="signed.token",
            submission_id="d" * 64,
        )

    kwargs = submit_email.await_args.kwargs
    assert kwargs["message_stream"] == "broadcasts"
    assert "Stop weekly digests:" in kwargs["text_body"]
    assert kwargs["headers"] == [
        {
            "Name": "List-Unsubscribe",
            "Value": ("<https://app.praviar.io/api/email/unsubscribe?token=signed.token>"),
        },
        {
            "Name": "List-Unsubscribe-Post",
            "Value": "List-Unsubscribe=One-Click",
        },
    ]
    assert kwargs["submission_id"] == "d" * 64


@pytest.mark.asyncio
async def test_send_template_email_returns_error_on_http_error():
    settings = MagicMock(
        postmark_api_token="pm_test",
        postmark_from_email="noreply@example.invalid",
    )
    request = httpx.Request("POST", "https://postmark.test/email/withTemplate")
    response = httpx.Response(status_code=500, request=request)
    http_client = AsyncMock()
    http_client.is_closed = False
    http_client.post = AsyncMock(
        side_effect=httpx.HTTPStatusError("boom", request=request, response=response)
    )

    with patch("api.services.email.get_settings", return_value=settings):
        client = PostmarkClient()
    client._client = http_client

    result = await client.send_template_email(
        to="user@example.com",
        template_alias="welcome",
        template_model={"name": "Ada"},
    )

    assert result.success is False
    assert result.error is not None
    assert "500" in result.error


@pytest.mark.asyncio
async def test_postmark_client_reuses_and_closes_http_client():
    settings = MagicMock(
        postmark_api_token="pm_test",
        postmark_from_email="noreply@example.invalid",
    )

    with patch("api.services.email.get_settings", return_value=settings):
        client = PostmarkClient()

    first = await client._get_client()
    second = await client._get_client()

    assert first is second
    assert first.headers["X-Postmark-Server-Token"] == "pm_test"

    await client.close()

    assert client._client is None


def test_get_email_client_returns_singleton():
    with patch("api.services.email.PostmarkClient") as client_cls:
        client_cls.return_value = MagicMock()
        from api.services import email as email_module

        email_module._client = None
        first = get_email_client()
        second = get_email_client()

    assert first is second
    client_cls.assert_called_once()


def _configured_postmark_client(http_client: AsyncMock) -> PostmarkClient:
    settings = MagicMock(
        postmark_api_token="pm_test",
        postmark_from_email="noreply@example.invalid",
    )
    with patch("api.services.email.get_settings", return_value=settings):
        client = PostmarkClient()
    client._client = http_client
    return client


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected_status"),
    [
        ({"ErrorCode": 0, "MessageID": "msg-accepted"}, "accepted"),
        ({"ErrorCode": 300, "MessageID": ""}, "rejected"),
        ({"ErrorCode": 0}, "outcome_unknown"),
        ({"ErrorCode": False, "MessageID": "msg-invalid"}, "outcome_unknown"),
        ([], "outcome_unknown"),
    ],
)
async def test_single_postmark_submission_requires_explicit_provider_acceptance(
    payload,
    expected_status: str,
) -> None:
    response = MagicMock(status_code=200)
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    http_client = AsyncMock()
    http_client.is_closed = False
    http_client.post = AsyncMock(return_value=response)
    client = _configured_postmark_client(http_client)

    result = await client.submit_email_once(
        to="counsel@example.com",
        subject="A Praviar report was shared with you",
        html_body="<p>Review</p>",
        text_body="Review",
        tag="external-report-grant",
        submission_id="d" * 64,
    )

    assert result.status == expected_status
    http_client.post.assert_awaited_once()
    posted = http_client.post.await_args.kwargs["json"]
    assert posted["Metadata"] == {"submission_id": "d" * 64}


@pytest.mark.asyncio
async def test_postmark_lookup_accepts_only_exact_official_outbound_identity() -> None:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "TotalCount": 1,
        "Messages": [
            {
                "MessageID": "msg-recovered",
                "To": [{"Email": "Counsel@Example.com", "Name": "Counsel"}],
                "Recipients": ["counsel@example.com"],
                "Cc": [],
                "Bcc": [],
                "Metadata": {"submission_id": "d" * 64},
                "Subject": "A Praviar report was shared with you",
                "Tag": "external-report-grant",
                "Status": "Sent",
            }
        ],
    }
    http_client = AsyncMock()
    http_client.is_closed = False
    http_client.get = AsyncMock(return_value=response)
    client = _configured_postmark_client(http_client)

    result = await client.lookup_outbound_submission(
        submission_id="d" * 64,
        expected_to="counsel@example.com",
        expected_subject="A Praviar report was shared with you",
        expected_tag="external-report-grant",
    )

    assert result.status == "found"
    assert result.message_id == "msg-recovered"
    assert http_client.get.await_args.kwargs["params"]["metadata_submission_id"] == "d" * 64


@pytest.mark.asyncio
async def test_weekly_digest_lookup_is_pinned_to_exact_broadcasts_stream() -> None:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "TotalCount": 1,
        "Messages": [
            {
                "MessageID": "digest-recovered",
                "To": [{"Email": "ada@example.com", "Name": "Ada"}],
                "Recipients": ["ada@example.com"],
                "Cc": [],
                "Bcc": [],
                "Metadata": {"submission_id": "d" * 64},
                "Subject": "Your Praviar Weekly Summary",
                "Tag": "weekly_digest",
                "MessageStream": "broadcasts",
                "Status": "Sent",
            }
        ],
    }
    http_client = AsyncMock()
    http_client.is_closed = False
    http_client.get = AsyncMock(return_value=response)
    client = _configured_postmark_client(http_client)

    result = await client.lookup_weekly_digest_submission(
        submission_id="d" * 64,
        expected_to="ada@example.com",
    )

    assert result.status == "found"
    assert result.message_id == "digest-recovered"
    assert http_client.get.await_args.kwargs["params"]["messagestream"] == "broadcasts"

    response.json.return_value["Messages"][0]["MessageStream"] = "outbound"
    result = await client.lookup_weekly_digest_submission(
        submission_id="d" * 64,
        expected_to="ada@example.com",
    )
    assert result.status == "alert"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        {"To": [{"Email": "attacker@example.com", "Name": ""}]},
        {"Recipients": ["attacker@example.com"]},
        {"Cc": [{"Email": "copy@example.com", "Name": ""}]},
        {"Bcc": [{"Email": "blind@example.com", "Name": ""}]},
        {"Metadata": {"submission_id": "e" * 64}},
        {"Subject": "Different subject"},
        {"Tag": "different-tag"},
        {"Status": "Failed"},
        {"MessageID": ""},
    ],
)
async def test_postmark_lookup_rejects_cross_delivery_or_malformed_identity(mutation) -> None:
    message = {
        "MessageID": "msg-recovered",
        "To": [{"Email": "counsel@example.com", "Name": "Counsel"}],
        "Recipients": ["counsel@example.com"],
        "Cc": [],
        "Bcc": [],
        "Metadata": {"submission_id": "d" * 64},
        "Subject": "A Praviar report was shared with you",
        "Tag": "external-report-grant",
        "Status": "Sent",
    }
    message.update(mutation)
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"TotalCount": 1, "Messages": [message]}
    http_client = AsyncMock()
    http_client.is_closed = False
    http_client.get = AsyncMock(return_value=response)
    client = _configured_postmark_client(http_client)

    result = await client.lookup_outbound_submission(
        submission_id="d" * 64,
        expected_to="counsel@example.com",
        expected_subject="A Praviar report was shared with you",
        expected_tag="external-report-grant",
    )

    assert result.status == "alert"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected_status"),
    [
        ({"TotalCount": 0, "Messages": []}, "not_found"),
        ({"TotalCount": 2, "Messages": [{}, {}]}, "alert"),
        ({"TotalCount": 1, "Messages": []}, "alert"),
    ],
)
async def test_postmark_lookup_requires_one_unique_search_result(
    payload,
    expected_status: str,
) -> None:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    http_client = AsyncMock()
    http_client.is_closed = False
    http_client.get = AsyncMock(return_value=response)
    client = _configured_postmark_client(http_client)

    result = await client.lookup_outbound_submission(
        submission_id="d" * 64,
        expected_to="counsel@example.com",
        expected_subject="A Praviar report was shared with you",
        expected_tag="external-report-grant",
    )

    assert result.status == expected_status
