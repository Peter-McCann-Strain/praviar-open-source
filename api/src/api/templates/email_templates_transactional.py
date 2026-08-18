# ruff: noqa: E501

"""Transactional email template renderers."""

from __future__ import annotations

from api.templates.email_layout import esc, esc_url, risk_badge, wrap_email

ANALYSIS_COMPLETE_HTML = """\
<tr><td style="padding:32px 32px 0;">
  <p style="margin:0 0 4px;font-size:14px;color:#0E6F68;">Hi {user_name},</p>
  <h2 style="margin:0 0 20px;font-size:20px;font-weight:600;color:#0B1F24;">Your FTO analysis is complete</h2>
</td></tr>
<tr><td style="padding:0 32px;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#D7ECE5;border-radius:8px;border:1px solid #5FB7A6;">
    <tr><td style="padding:20px 24px;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
        <tr>
          <td style="font-size:13px;color:#0E6F68;padding-bottom:6px;">{analysis_label}</td>
          <td style="font-size:13px;color:#0E6F68;padding-bottom:6px;text-align:right;">{risk_label}</td>
        </tr>
        <tr>
          <td style="font-size:16px;font-weight:600;color:#0B1F24;">{compound_name}</td>
          <td style="text-align:right;">{risk_badge}</td>
        </tr>
      </table>
    </td></tr>
  </table>
</td></tr>
<tr><td style="padding:24px 32px 32px;text-align:center;">
  <a href="{report_url}" style="display:inline-block;padding:12px 28px;background-color:#0E6F68;color:#F6F4EF;font-size:14px;font-weight:600;text-decoration:none;border-radius:8px;">{report_cta_label}</a>
</td></tr>
"""

MONITOR_ALERT_HTML = """\
<tr><td style="padding:32px 32px 0;">
  <p style="margin:0 0 4px;font-size:14px;color:#0E6F68;">Hi {user_name},</p>
  <h2 style="margin:0 0 20px;font-size:20px;font-weight:600;color:#0B1F24;">{alert_heading}</h2>
</td></tr>
<tr><td style="padding:0 32px;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#F6F4EF;border-radius:8px;border:1px solid #B87333;">
    <tr><td style="padding:20px 24px;">
      <p style="margin:0 0 8px;font-size:15px;font-weight:600;color:#8A4F1F;">{compound_name}</p>
      {conclusion_detail}
      <p style="margin:0;font-size:14px;color:#0B1F24;">
        <strong>{activity_summary}</strong> since your last scan.
      </p>
      {event_detail}
    </td></tr>
  </table>
</td></tr>
<tr><td style="padding:24px 32px 32px;text-align:center;">
  <a href="{monitor_url}" style="display:inline-block;padding:12px 28px;background-color:#0E6F68;color:#F6F4EF;font-size:14px;font-weight:600;text-decoration:none;border-radius:8px;">{cta_label}</a>
</td></tr>
"""

WELCOME_HTML = """\
<tr><td style="padding:32px 32px 0;">
  <h2 style="margin:0 0 8px;font-size:20px;font-weight:600;color:#0B1F24;">Welcome to Praviar, {user_name}!</h2>
  <p style="margin:0 0 24px;font-size:14px;color:#0E6F68;line-height:1.6;">
    {welcome_intro}
  </p>
</td></tr>
<tr><td style="padding:0 32px;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
    <tr><td style="padding:16px 0;border-bottom:1px solid #D7ECE5;">
      <table role="presentation" cellspacing="0" cellpadding="0">
        <tr>
          <td style="width:36px;height:36px;background-color:#D7ECE5;border-radius:50%;text-align:center;vertical-align:middle;font-size:15px;font-weight:700;color:#0E6F68;">1</td>
          <td style="padding-left:16px;">
            <p style="margin:0 0 2px;font-size:14px;font-weight:600;color:#0B1F24;">{step_1_title}</p>
            <p style="margin:0;font-size:13px;color:#0E6F68;">{step_1_body}</p>
          </td>
        </tr>
      </table>
    </td></tr>
    <tr><td style="padding:16px 0;border-bottom:1px solid #D7ECE5;">
      <table role="presentation" cellspacing="0" cellpadding="0">
        <tr>
          <td style="width:36px;height:36px;background-color:#D7ECE5;border-radius:50%;text-align:center;vertical-align:middle;font-size:15px;font-weight:700;color:#0E6F68;">2</td>
          <td style="padding-left:16px;">
            <p style="margin:0 0 2px;font-size:14px;font-weight:600;color:#0B1F24;">{step_2_title}</p>
            <p style="margin:0;font-size:13px;color:#0E6F68;">{step_2_body}</p>
          </td>
        </tr>
      </table>
    </td></tr>
    <tr><td style="padding:16px 0;">
      <table role="presentation" cellspacing="0" cellpadding="0">
        <tr>
          <td style="width:36px;height:36px;background-color:#D7ECE5;border-radius:50%;text-align:center;vertical-align:middle;font-size:15px;font-weight:700;color:#0E6F68;">3</td>
          <td style="padding-left:16px;">
            <p style="margin:0 0 2px;font-size:14px;font-weight:600;color:#0B1F24;">{step_3_title}</p>
            <p style="margin:0;font-size:13px;color:#0E6F68;">{step_3_body}</p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</td></tr>
<tr><td style="padding:28px 32px 32px;text-align:center;">
  <a href="{dashboard_url}" style="display:inline-block;padding:12px 28px;background-color:#0E6F68;color:#F6F4EF;font-size:14px;font-weight:600;text-decoration:none;border-radius:8px;">{dashboard_label}</a>
</td></tr>
"""


def render_analysis_complete(
    user_name: str,
    compound_name: str,
    risk_level: str,
    report_url: str,
    report_cta_label: str = "View Full Report",
    risk_restricted: bool = False,
    unsubscribe_url: str = "#",
    preferences_url: str = "#",
) -> str:
    """Render the analysis-complete email HTML.

    ``user_name`` and ``compound_name`` are user-controlled and are HTML-escaped
    before interpolation; ``report_url`` is escaped for href-attribute context.
    """
    visible_compound_name = "Governed analysis" if risk_restricted else compound_name
    visible_risk_level = "COUNSEL ONLY" if risk_restricted else risk_level
    visible_cta_label = "View Governed Summary" if risk_restricted else report_cta_label
    body = ANALYSIS_COMPLETE_HTML.format(
        user_name=esc(user_name),
        compound_name=esc(visible_compound_name),
        risk_badge=risk_badge(visible_risk_level),
        analysis_label="Analysis" if risk_restricted else "Compound",
        risk_label="Assessment access" if risk_restricted else "Risk Level",
        report_cta_label=esc(visible_cta_label),
        report_url=esc_url(report_url),
    )
    return wrap_email(
        "FTO Analysis Complete",
        body,
        unsubscribe_url=unsubscribe_url,
        preferences_url=preferences_url,
    )


def render_monitor_alert(
    user_name: str,
    compound_name: str,
    new_patent_count: int,
    monitor_url: str,
    new_event_ids: list[str] | None = None,
    affected_conclusions: list[dict] | None = None,
    unsubscribe_url: str = "#",
    preferences_url: str = "#",
) -> str:
    """Render the monitor-alert email HTML.

    ``user_name`` and ``compound_name`` are user-controlled and are HTML-escaped
    before interpolation; ``monitor_url`` is escaped for href-attribute context.
    """
    patent_count = max(int(new_patent_count), 0)
    event_ids = list(
        dict.fromkeys(
            event_id.strip()
            for event_id in new_event_ids or []
            if isinstance(event_id, str) and event_id.strip()
        )
    )
    patent_summary = (
        f"{patent_count} new patent{'s' if patent_count != 1 else ''}" if patent_count else ""
    )
    event_summary = (
        f"{len(event_ids)} new patent event{'s' if len(event_ids) != 1 else ''}"
        if event_ids
        else ""
    )
    activity_summary = (
        " and ".join(summary for summary in (patent_summary, event_summary) if summary)
        or "Patent activity changed"
    )
    visible_event_ids = event_ids[:10]
    remaining_event_count = len(event_ids) - len(visible_event_ids)
    event_reference_text = ", ".join(visible_event_ids)
    if remaining_event_count:
        event_reference_text = f"{event_reference_text} (+{remaining_event_count} more)"
    event_detail = (
        '<p style="margin:10px 0 0;font-size:12px;color:#516F68;'
        'overflow-wrap:anywhere;">Event references: '
        f"{esc(event_reference_text)}</p>"
        if event_reference_text
        else ""
    )
    conclusions = [
        item
        for item in affected_conclusions or []
        if isinstance(item, dict) and str(item.get("conclusion_id") or "").strip()
    ]
    visible_conclusions = conclusions[:5]
    conclusion_items = "".join(
        (
            '<li style="margin:0 0 6px;">'
            f"<strong>{esc(str(item.get('label') or item.get('conclusion_id') or 'Conclusion'))}</strong>"
            f" — previously {esc(str(item.get('previous_outcome') or 'recorded'))}"
            "</li>"
        )
        for item in visible_conclusions
    )
    remaining_conclusions = len(conclusions) - len(visible_conclusions)
    if remaining_conclusions:
        conclusion_items += (
            f'<li style="margin:0;">+{remaining_conclusions} more affected '
            f"conclusion{'' if remaining_conclusions == 1 else 's'}</li>"
        )
    conclusion_detail = (
        '<div style="margin:0 0 14px;padding:12px 14px;background-color:#FFF7ED;'
        'border-left:3px solid #B87333;">'
        f'<p style="margin:0 0 8px;font-size:14px;font-weight:700;color:#8A4F1F;">'
        f"{len(conclusions)} prior report conclusion"
        f"{'' if len(conclusions) == 1 else 's'} require counsel reassessment"
        "</p>"
        '<ul style="margin:0;padding-left:18px;font-size:13px;line-height:1.5;color:#0B1F24;">'
        f"{conclusion_items}</ul>"
        '<p style="margin:9px 0 0;font-size:12px;line-height:1.5;color:#516F68;">'
        "Do not rely on the prior conclusion until an attorney records a reassessment."
        "</p></div>"
        if conclusions
        else ""
    )
    body = MONITOR_ALERT_HTML.format(
        user_name=esc(user_name),
        compound_name=esc(compound_name),
        alert_heading=(
            "Counsel reassessment required"
            if conclusions
            else "New patent activity detected for your compound"
        ),
        conclusion_detail=conclusion_detail,
        activity_summary=esc(activity_summary),
        event_detail=event_detail,
        monitor_url=esc_url(monitor_url),
        cta_label=("Review Affected Conclusions" if conclusions else "Review Patent Activity"),
    )
    return wrap_email(
        "Patent Monitor Alert",
        body,
        unsubscribe_url=unsubscribe_url,
        preferences_url=preferences_url,
    )


def render_welcome(
    user_name: str,
    role: str = "admin",
    dashboard_url: str = "#",
    unsubscribe_url: str = "#",
    preferences_url: str = "#",
) -> str:
    """Render the welcome email HTML (``user_name`` is HTML-escaped)."""
    normalized_role = role.strip().lower()
    if normalized_role in {"admin", "attorney"}:
        content = {
            "welcome_intro": (
                "You now have access to AI-assisted Freedom-to-Operate "
                "screening built for qualified counsel review. Here's how to get started:"
            ),
            "step_1_title": "Run your first analysis",
            "step_1_body": (
                "Enter a compound name or SMILES string to start an evidence-led FTO screen."
            ),
            "step_2_title": "Review governed patent evidence",
            "step_2_body": (
                "Inspect claims, sources, risk conclusions, and reviewer-ready caveats."
            ),
            "step_3_title": "Set up monitoring",
            "step_3_body": (
                "Enable patent watch and keep counsel review connected to new activity."
            ),
            "dashboard_label": "Go to Dashboard",
        }
    elif normalized_role == "scientist":
        content = {
            "welcome_intro": (
                "You can start evidence-led FTO screening while counsel-controlled "
                "risk conclusions remain governed by your workspace role."
            ),
            "step_1_title": "Start an evidence-led analysis",
            "step_1_body": (
                "Enter a compound name or SMILES string to build the patent evidence packet."
            ),
            "step_2_title": "Inspect permitted evidence",
            "step_2_body": (
                "Review sources, coverage, and scientific context available to your role."
            ),
            "step_3_title": "Hand off to counsel",
            "step_3_body": ("Use the governed summary and review workflow for counsel assessment."),
            "dashboard_label": "Open Workspace",
        }
    else:
        content = {
            "welcome_intro": (
                "You have secure access to counsel-approved summaries and shared "
                "evidence made available by your workspace."
            ),
            "step_1_title": "Open shared analyses",
            "step_1_body": ("Use your workspace dashboard to find reports shared with your role."),
            "step_2_title": "Review governed summaries",
            "step_2_body": (
                "Read the approved scope, evidence caveats, and counsel-provided next steps."
            ),
            "step_3_title": "Contact your workspace team",
            "step_3_body": (
                "Ask the report owner or counsel contact when additional access is required."
            ),
            "dashboard_label": "Open Shared Workspace",
        }

    body = WELCOME_HTML.format(
        user_name=esc(user_name),
        dashboard_url=esc_url(dashboard_url),
        **{key: esc(value) for key, value in content.items()},
    )
    return wrap_email(
        "Welcome to Praviar",
        body,
        unsubscribe_url=unsubscribe_url,
        preferences_url=preferences_url,
    )
