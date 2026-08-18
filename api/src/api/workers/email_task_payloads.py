"""Deterministic payload helpers for email worker tasks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from api.services.risk_access import risk_ratings_restricted_for_role


def build_analysis_complete_send_kwargs(*, user, analysis, analysis_id: str) -> dict[str, Any]:
    """Build the analysis-complete email payload."""
    risk_restricted = risk_ratings_restricted_for_role(getattr(user, "role", None))
    compound_name = analysis.compound_name or analysis.compound_input[:50]
    return {
        "user_email": user.email,
        "user_name": user.full_name or user.email,
        "analysis_id": analysis_id,
        "compound_name": "Governed analysis" if risk_restricted else compound_name,
        "risk_level": "COUNSEL ONLY" if risk_restricted else analysis.overall_risk or "UNKNOWN",
        "report_cta_label": "View Governed Summary" if risk_restricted else "View Full Report",
        "report_url": (
            f"/analyses/{analysis_id}/report/summary"
            if risk_restricted
            else f"/analyses/{analysis_id}/report"
        ),
        "risk_restricted": risk_restricted,
    }


def build_monitor_alert_send_kwargs(*, user, monitor, alert) -> dict[str, Any]:
    """Build the monitor-alert email payload."""
    payload = {
        "user_email": user.email,
        "user_name": user.full_name or user.email,
        "compound_name": monitor.compound_name or monitor.compound_smiles[:30],
        "new_patent_count": alert.new_patent_count,
        "new_event_ids": list(getattr(alert, "new_event_ids", None) or []),
        "monitor_url": "/monitors",
    }
    affected_conclusions = list(getattr(alert, "affected_conclusions", None) or [])
    if affected_conclusions:
        payload["affected_conclusions"] = affected_conclusions
    return payload


def build_welcome_send_kwargs(*, user) -> dict[str, str]:
    """Build the welcome email payload."""
    raw_role = getattr(user, "role", None)
    role = getattr(raw_role, "value", raw_role)
    normalized_role = str(role or "").strip().lower()
    if normalized_role not in {"admin", "attorney", "scientist", "client"}:
        normalized_role = "client"
    return {
        "user_email": user.email,
        "user_name": user.full_name or user.email,
        "role": normalized_role,
    }


def build_weekly_digest_send_kwargs(
    *,
    user,
    analyses_completed: int,
    alerts_count: int,
    top_risks: list[dict[str, str]],
    unsubscribe_token: str,
    risk_restricted: bool = False,
) -> dict[str, Any]:
    """Build the weekly digest email payload."""
    return {
        "user_email": user.email,
        "user_name": user.full_name or user.email,
        "analyses_completed": analyses_completed,
        "alerts_count": alerts_count,
        "top_risks": [] if risk_restricted else top_risks,
        "risk_restricted": risk_restricted,
        "unsubscribe_token": unsubscribe_token,
    }


def weekly_digest_cutoff(now: datetime | None = None) -> datetime:
    """Return the previous Monday 09:00 UTC period start.

    The corresponding exclusive end is always ``cutoff + 7 days``. This avoids
    a rolling seven-day window and prevents events from the current, incomplete
    period entering a retry of the prior digest.
    """
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        raise ValueError("weekly digest time must be timezone-aware")
    current = current.astimezone(UTC)
    scheduled_end = current.replace(
        hour=9,
        minute=0,
        second=0,
        microsecond=0,
    ) - timedelta(days=current.weekday())
    if current < scheduled_end:
        scheduled_end -= timedelta(days=7)
    return scheduled_end - timedelta(days=7)


def map_email_task_result(result) -> dict[str, str | None]:
    """Normalize an email client send result into the worker return shape."""
    return {
        "status": "sent" if result.success else "failed",
        "message_id": result.message_id,
        "error": result.error,
    }
