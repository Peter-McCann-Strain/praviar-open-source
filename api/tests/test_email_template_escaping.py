"""Regression tests for HTML-escaping of user/DB-controlled values in emails.

Locks in the Wave 46 (compound name / URL escaping) and Wave 47 (risk-level
badge escaping) hardening so an attacker-controlled compound name or a
non-standard ``analyses.overall_risk`` value cannot inject active content into a
rendered HTML email.
"""

from __future__ import annotations

from api.templates.email_layout import esc_url, risk_badge, wrap_email
from api.templates.email_templates_digest import render_weekly_digest
from api.templates.email_templates_transactional import (
    render_analysis_complete,
    render_monitor_alert,
)

_XSS = "<img src=x onerror=alert(1)>"


def test_analysis_complete_escapes_compound_and_user_name():
    html = render_analysis_complete(
        user_name=_XSS,
        compound_name=_XSS,
        risk_level="HIGH",
        report_url="https://example.com/r/1",
    )
    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;img" in html


def test_analysis_complete_neutralizes_javascript_report_url():
    html = render_analysis_complete(
        user_name="Dr Smith",
        compound_name="caffeine",
        risk_level="LOW",
        report_url="javascript:alert(1)",
    )
    assert "javascript:alert(1)" not in html


def test_risk_badge_escapes_non_enum_risk_level():
    # overall_risk is an unconstrained String(20) column, so a crafted value
    # must not break out of the badge span.
    badge = risk_badge('"><script>alert(1)</script>')
    assert "<script>" not in badge
    assert "&lt;" in badge


def test_weekly_digest_escapes_compound_name_in_rows():
    html = render_weekly_digest(
        user_name="Dr Smith",
        analyses_completed=2,
        alerts_count=1,
        top_risks=[{"compound_name": _XSS, "risk_level": "HIGH"}],
    )
    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;img" in html


def test_monitor_alert_escapes_compound_and_neutralizes_url():
    html = render_monitor_alert(
        user_name="Dr Smith",
        compound_name=_XSS,
        new_patent_count=3,
        monitor_url="javascript:alert(1)",
    )
    assert "<img src=x onerror=alert(1)>" not in html
    assert "javascript:alert(1)" not in html


def test_wrap_email_escapes_footer_urls_and_title():
    html = wrap_email(
        title=_XSS,
        body_rows="<tr><td>body</td></tr>",
        unsubscribe_url="javascript:alert(1)",
        preferences_url="https://example.com/prefs",
    )
    assert "<img src=x onerror=alert(1)>" not in html
    assert "javascript:alert(1)" not in html


def test_wrap_email_uses_praviar_artifact_lockup():
    html = wrap_email(
        title="Analysis complete",
        body_rows="<tr><td>body</td></tr>",
    )

    assert 'data-praviar-mark="praviar-evidence-mark"' in html
    assert "FTO screening intelligence" in html
    assert "Evidence-led patent risk, ready for counsel review." in html
    assert "background-color:#0B1F24;border-bottom:4px" not in html


def test_esc_url_allows_safe_schemes_and_rejects_active_content():
    assert esc_url("https://example.com") == "https://example.com"
    assert esc_url("/dashboard") == "/dashboard"
    assert esc_url("vbscript:msgbox(1)") == "#"
    assert esc_url("data:text/html,<script>") == "#"
