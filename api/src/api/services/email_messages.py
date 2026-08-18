"""High-level message builders for transactional emails."""

from __future__ import annotations

from urllib.parse import quote

from api.config import get_settings
from api.templates.emails import (
    render_analysis_complete,
    render_monitor_alert,
    render_weekly_digest,
    render_welcome,
)


def _app_url_for_path(url: str) -> str:
    """Return an email-safe absolute app URL when given an app-relative path."""
    normalized_url = url.strip()
    if not normalized_url.startswith("/"):
        return normalized_url

    app_url = (getattr(get_settings(), "app_url", "") or "").rstrip("/")
    return f"{app_url}{normalized_url}" if app_url else normalized_url


def _email_footer_urls() -> dict[str, str]:
    """Resolve absolute unsubscribe + preferences URLs for email footers.

    Both point at the authenticated notification-preferences screen so the
    CAN-SPAM/GDPR-required unsubscribe link is always live (previously the
    footer rendered a dead ``#`` anchor). Falls back to the bare path when
    ``app_url`` is unset so the link is at least same-origin in local dev.
    """
    app_url = (getattr(get_settings(), "app_url", "") or "").rstrip("/")
    preferences_path = "/settings/notifications"
    unsubscribe_path = "/settings/notifications?unsubscribe=1"
    return {
        "preferences_url": f"{app_url}{preferences_path}" if app_url else preferences_path,
        "unsubscribe_url": f"{app_url}{unsubscribe_path}" if app_url else unsubscribe_path,
    }


def weekly_digest_unsubscribe_urls(unsubscribe_token: str) -> dict[str, str]:
    """Return confirmation-page and RFC 8058 one-click URLs for a digest."""
    encoded_token = quote(unsubscribe_token, safe="")
    return {
        "unsubscribe_url": _app_url_for_path(f"/unsubscribe/digest?token={encoded_token}"),
        "one_click_url": _app_url_for_path(f"/api/email/unsubscribe?token={encoded_token}"),
    }


def build_analysis_complete_message(
    *,
    user_name: str,
    compound_name: str,
    risk_level: str,
    report_cta_label: str,
    report_url: str,
    risk_restricted: bool,
) -> tuple[str, str, str]:
    """Build subject, HTML, and tag for an analysis-complete email."""
    html = render_analysis_complete(
        user_name=user_name,
        compound_name=compound_name,
        risk_level=risk_level,
        report_cta_label=report_cta_label,
        report_url=_app_url_for_path(report_url),
        risk_restricted=risk_restricted,
        **_email_footer_urls(),
    )
    subject = (
        "Your Praviar analysis is ready"
        if risk_restricted
        else f"FTO Analysis Complete: {compound_name}"
    )
    return (subject, html, "analysis_complete")


def build_monitor_alert_message(
    *,
    user_name: str,
    compound_name: str,
    new_patent_count: int,
    monitor_url: str,
    new_event_ids: list[str] | None = None,
    affected_conclusions: list[dict] | None = None,
) -> tuple[str, str, str]:
    """Build subject, HTML, and tag for a monitor alert email."""
    normalized_event_ids = list(
        dict.fromkeys(
            event_id.strip()
            for event_id in new_event_ids or []
            if isinstance(event_id, str) and event_id.strip()
        )
    )
    html = render_monitor_alert(
        user_name=user_name,
        compound_name=compound_name,
        new_patent_count=new_patent_count,
        new_event_ids=normalized_event_ids,
        affected_conclusions=affected_conclusions,
        monitor_url=_app_url_for_path(monitor_url),
        **_email_footer_urls(),
    )
    patent_count = max(int(new_patent_count), 0)
    event_count = len(normalized_event_ids)
    patent_summary = (
        f"{patent_count} new patent{'s' if patent_count != 1 else ''}" if patent_count else ""
    )
    event_summary = (
        f"{event_count} new patent event{'s' if event_count != 1 else ''}" if event_count else ""
    )
    activity_summary = (
        " and ".join(summary for summary in (patent_summary, event_summary) if summary)
        or "patent activity update"
    )
    conclusion_count = len(
        [
            item
            for item in affected_conclusions or []
            if isinstance(item, dict) and str(item.get("conclusion_id") or "").strip()
        ]
    )
    if conclusion_count:
        return (
            "Counsel reassessment required: "
            f"{conclusion_count} conclusion{'' if conclusion_count == 1 else 's'} "
            f"for {compound_name}",
            html,
            "monitor_alert",
        )
    return (
        f"Patent Alert: {activity_summary} for {compound_name}",
        html,
        "monitor_alert",
    )


def build_welcome_message(*, user_name: str, role: str) -> tuple[str, str, str]:
    """Build subject, HTML, and tag for a welcome email."""
    return (
        "Welcome to Praviar",
        render_welcome(
            user_name=user_name,
            role=role,
            dashboard_url=_app_url_for_path("/dashboard"),
            **_email_footer_urls(),
        ),
        "welcome",
    )


def build_weekly_digest_message(
    *,
    user_name: str,
    analyses_completed: int,
    alerts_count: int,
    top_risks: list[dict[str, str]],
    risk_restricted: bool = False,
    unsubscribe_token: str,
) -> tuple[str, str, str]:
    """Build subject, HTML, and tag for a weekly digest email."""
    unsubscribe_urls = weekly_digest_unsubscribe_urls(unsubscribe_token)
    footer_urls = _email_footer_urls()
    html = render_weekly_digest(
        user_name=user_name,
        analyses_completed=analyses_completed,
        alerts_count=alerts_count,
        top_risks=top_risks,
        risk_restricted=risk_restricted,
        dashboard_url=_app_url_for_path("/dashboard"),
        unsubscribe_url=unsubscribe_urls["unsubscribe_url"],
        preferences_url=footer_urls["preferences_url"],
    )
    return ("Your Praviar Weekly Summary", html, "weekly_digest")


def build_weekly_digest_text(
    *,
    user_name: str,
    analyses_completed: int,
    alerts_count: int,
    top_risks: list[dict[str, str]],
    risk_restricted: bool,
    unsubscribe_token: str,
) -> str:
    """Build a multipart plain-text companion for the recurring digest."""
    unsubscribe_url = weekly_digest_unsubscribe_urls(unsubscribe_token)["unsubscribe_url"]
    lines = [
        f"Hi {user_name},",
        "",
        "Your Praviar weekly summary",
        f"Analyses completed: {analyses_completed}",
        f"Alerts: {alerts_count}",
    ]
    if risk_restricted:
        lines.append("Risk details: Counsel only")
    else:
        high_risk_count = sum(
            1 for risk in top_risks if str(risk.get("risk_level", "")).upper() == "HIGH"
        )
        lines.append(f"High-risk analyses: {high_risk_count}")
    lines.extend(
        [
            "",
            f"View dashboard: {_app_url_for_path('/dashboard')}",
            f"Stop weekly digests: {unsubscribe_url}",
            (f"Notification preferences: {_email_footer_urls()['preferences_url']}"),
        ]
    )
    return "\n".join(lines)
