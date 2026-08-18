# ruff: noqa: E501

"""Digest email template renderers."""

from __future__ import annotations

from api.templates.email_layout import esc, esc_url, risk_badge, wrap_email

WEEKLY_DIGEST_HTML = """\
<tr><td style="padding:32px 32px 0;">
  <p style="margin:0 0 4px;font-size:14px;color:#0E6F68;">Hi {user_name},</p>
  <h2 style="margin:0 0 20px;font-size:20px;font-weight:600;color:#0B1F24;">Your Weekly Summary</h2>
</td></tr>
<tr><td style="padding:0 32px;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
    <tr class="praviar-digest-metric-row">
      <td class="praviar-digest-metric" style="width:33%;text-align:center;padding:20px 8px;background-color:#D7ECE5;border-radius:8px 0 0 8px;border:1px solid #5FB7A6;border-right:none;">
        <p style="margin:0 0 4px;font-size:28px;font-weight:700;color:#0E6F68;">{analyses_completed}</p>
        <p style="margin:0;font-size:12px;color:#0B1F24;">Analyses</p>
      </td>
      <td class="praviar-digest-metric" style="width:33%;text-align:center;padding:20px 8px;background-color:#D7ECE5;border-top:1px solid #5FB7A6;border-bottom:1px solid #5FB7A6;">
        <p style="margin:0 0 4px;font-size:28px;font-weight:700;color:#B87333;">{alerts_count}</p>
        <p style="margin:0;font-size:12px;color:#0B1F24;">Alerts</p>
      </td>
      <td class="praviar-digest-metric" style="width:33%;text-align:center;padding:20px 8px;background-color:#D7ECE5;border-radius:0 8px 8px 0;border:1px solid #5FB7A6;border-left:none;">
        <p style="margin:0 0 4px;font-size:{risk_metric_font_size};line-height:1.2;font-weight:700;color:{risk_metric_color};word-break:break-word;">{risk_metric_value}</p>
        <p style="margin:0;font-size:12px;color:#0B1F24;">{risk_metric_label}</p>
      </td>
    </tr>
  </table>
</td></tr>
{top_risks_section}
<tr><td style="padding:24px 32px 32px;text-align:center;">
  <a href="{dashboard_url}" style="display:inline-block;padding:12px 28px;background-color:#0E6F68;color:#F6F4EF;font-size:14px;font-weight:600;text-decoration:none;border-radius:8px;">View Dashboard</a>
</td></tr>
"""

_DIGEST_RISK_ROW = """\
    <tr>
      <td style="padding:10px 0;border-bottom:1px solid #D7ECE5;font-size:14px;color:#0B1F24;">{compound_name}</td>
      <td style="padding:10px 0;border-bottom:1px solid #D7ECE5;text-align:right;">{risk_badge}</td>
    </tr>
"""

_DIGEST_RISKS_SECTION = """\
<tr><td style="padding:20px 32px 0;">
  <p style="margin:0 0 12px;font-size:14px;font-weight:600;color:#0B1F24;">Top Risks This Week</p>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
{rows}
  </table>
</td></tr>
"""


def render_weekly_digest(
    user_name: str,
    analyses_completed: int,
    alerts_count: int,
    top_risks: list[dict[str, str]],
    risk_restricted: bool = False,
    dashboard_url: str = "#",
    unsubscribe_url: str = "#",
    preferences_url: str = "#",
) -> str:
    """Render the weekly digest email HTML.

    ``user_name`` and each row's ``compound_name`` are user-controlled and are
    HTML-escaped before interpolation.
    """
    visible_top_risks = [] if risk_restricted else top_risks
    high_risk_count = sum(
        1 for risk in visible_top_risks if risk.get("risk_level", "").upper() == "HIGH"
    )

    if visible_top_risks:
        rows = "".join(
            _DIGEST_RISK_ROW.format(
                compound_name=esc(risk["compound_name"]),
                risk_badge=risk_badge(risk["risk_level"]),
            )
            for risk in visible_top_risks[:5]
        )
        top_risks_section = _DIGEST_RISKS_SECTION.format(rows=rows)
    else:
        top_risks_section = ""

    body = WEEKLY_DIGEST_HTML.format(
        user_name=esc(user_name),
        analyses_completed=int(analyses_completed),
        alerts_count=int(alerts_count),
        risk_metric_value="Counsel" if risk_restricted else high_risk_count,
        risk_metric_label="Only" if risk_restricted else "High Risk",
        risk_metric_color="#516F68" if risk_restricted else "#7F1D1D",
        risk_metric_font_size="16px" if risk_restricted else "28px",
        top_risks_section=top_risks_section,
        dashboard_url=esc_url(dashboard_url),
    )
    return wrap_email(
        "Weekly Digest",
        body,
        unsubscribe_url=unsubscribe_url,
        preferences_url=preferences_url,
    )
