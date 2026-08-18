"""Stable import surface for email template renderers."""

from __future__ import annotations

from api.templates.email_templates_digest import render_weekly_digest
from api.templates.email_templates_transactional import (
    render_analysis_complete,
    render_monitor_alert,
    render_welcome,
)

__all__ = [
    "render_analysis_complete",
    "render_monitor_alert",
    "render_weekly_digest",
    "render_welcome",
]
