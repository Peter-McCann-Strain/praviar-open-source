# ruff: noqa: E501

"""Shared HTML layout and styling helpers for transactional emails."""

from __future__ import annotations

from markupsafe import escape

# URL schemes permitted in email link attributes. Anything else (javascript:,
# data:, vbscript:, …) is replaced with a safe placeholder so a user-controlled
# value smuggled into report_url/monitor_url cannot produce an active-content
# link inside the rendered HTML email.
_SAFE_URL_SCHEMES = ("https://", "http://", "mailto:", "/", "#")


def esc(value: object) -> str:
    """HTML-escape a value for safe interpolation into email text content.

    User-controlled strings (compound names, display names) flow into these
    templates via ``str.format``; without escaping a value such as
    ``<img src=x onerror=...>`` would be injected verbatim into the email body.
    """
    return str(escape("" if value is None else str(value)))


def esc_url(value: object) -> str:
    """Escape a URL for safe interpolation into an ``href`` attribute.

    Rejects non-navigational schemes (e.g. ``javascript:``) and HTML-escapes the
    result so a crafted value cannot break out of the attribute or smuggle in
    active content.
    """
    raw = ("" if value is None else str(value)).strip()
    lowered = raw.lower()
    if not raw or not lowered.startswith(_SAFE_URL_SCHEMES):
        raw = "#"
    return str(escape(raw))


_LAYOUT_HEAD = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
@media only screen and (max-width:480px) {{
  .praviar-digest-metric-row {{
    display:block !important;
  }}
  .praviar-digest-metric {{
    box-sizing:border-box !important;
    display:block !important;
    width:100% !important;
    margin-bottom:8px !important;
    border:1px solid #5FB7A6 !important;
    border-radius:8px !important;
  }}
}}
</style>
</head>
<body style="margin:0;padding:0;background-color:#F6F4EF;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;color:#0B1F24;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#F6F4EF;">
<tr><td align="center" style="padding:24px 16px;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;background-color:#F6F4EF;border:1px solid #D7ECE5;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(11,31,36,0.08);">
"""

_EMAIL_MARK_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" width="52" height="52" viewBox="0 0 230 230" role="img" aria-label="Praviar evidence mark" data-praviar-mark="praviar-evidence-mark" style="display:block;width:52px;height:52px;">
  <path d="M48 34H156C187 34 207 51 211 79V211H109C74 211 48 185 48 150V34Z" fill="#F6F4EF"/>
  <path d="M93 60C122 85 158 101 210 80V118C174 142 137 148 103 139C123 157 132 179 121 195C108 214 79 224 45 224C78 209 98 190 100 166C102 142 83 117 52 91L69 96C59 84 57 72 62 59C95 86 128 101 170 100C137 96 111 84 93 60Z" fill="#0B1F24"/>
  <path d="M126 116C157 111 184 101 211 85V101C184 116 157 127 126 132Z" fill="#5FB7A6"/>
  <path d="M120 145C154 141 184 128 211 113V132C183 148 153 159 120 161Z" fill="#0E6F68"/>
  <path d="M128 177C158 172 185 158 211 142V164C184 180 159 190 134 194Z" fill="#B87333"/>
  <path d="M151 209C174 205 194 195 211 185V211H154Z" fill="#D7ECE5"/>
</svg>
"""

_LAYOUT_HEADER = f"""\
<tr><td style="background-color:#F6F4EF;border-bottom:1px solid #D7ECE5;padding:24px 32px;">
  <table role="presentation" cellspacing="0" cellpadding="0" align="center" style="margin:0 auto;">
    <tr>
      <td style="width:52px;height:52px;padding:0;vertical-align:middle;">
        {_EMAIL_MARK_SVG}
      </td>
      <td style="padding-left:14px;text-align:left;vertical-align:middle;">
        <h1 style="margin:0;font-family:Georgia,'Times New Roman',serif;font-size:26px;font-weight:700;color:#0B4F4C;letter-spacing:0;line-height:1.05;">Praviar</h1>
        <p aria-label="FTO Screening" style="margin:6px 0 0;font-size:11px;font-weight:700;letter-spacing:0.18em;text-transform:uppercase;color:#0E6F68;">FTO screening intelligence</p>
        <p aria-label="Evidence-led patent risk, ready for review." style="margin:7px 0 0;font-size:12px;line-height:1.45;color:#516F68;">Evidence-led patent risk, ready for counsel review.</p>
      </td>
    </tr>
  </table>
</td></tr>
"""

_LAYOUT_FOOTER = """\
<tr><td style="padding:24px 32px;border-top:1px solid #D7ECE5;text-align:center;">
  <p style="margin:0 0 8px;font-size:12px;color:#0B1F24;">Praviar &mdash; AI-assisted FTO screening for counsel review</p>
  <p style="margin:0;font-size:11px;color:#0E6F68;">
    <a href="{unsubscribe_url}" style="color:#0E6F68;text-decoration:underline;">Unsubscribe</a>
    &nbsp;&middot;&nbsp;
    <a href="{preferences_url}" style="color:#0E6F68;text-decoration:underline;">Notification Preferences</a>
  </p>
</td></tr>
"""

_LAYOUT_TAIL = """\
</table>
</td></tr>
</table>
</body>
</html>
"""

_RISK_COLORS: dict[str, tuple[str, str, str]] = {
    # Premium Praviar email palette — (foreground, background, border)
    "HIGH": ("#7F1D1D", "#FDECEC", "#C2413A"),
    "MEDIUM": ("#8A4F1F", "#F7EEE5", "#B87333"),
    "LOW": ("#0E6F68", "#D7ECE5", "#5FB7A6"),
    "MINIMAL": ("#0B1F24", "#D7ECE5", "#5FB7A6"),
    "CLEAR": ("#0B1F24", "#D7ECE5", "#5FB7A6"),
    "COUNSEL ONLY": ("#516F68", "#F1F3F2", "#9AAEA8"),
}


def wrap_email(
    title: str,
    body_rows: str,
    unsubscribe_url: str = "#",
    preferences_url: str = "#",
) -> str:
    """Wrap body rows in the shared email layout.

    ``title`` and the footer URLs are escaped here so callers cannot break out
    of the document head or the footer ``href`` attributes. ``body_rows`` is
    assembled by the per-template renderers, which are responsible for escaping
    their own interpolated values via :func:`esc` / :func:`esc_url`.
    """
    return (
        _LAYOUT_HEAD.format(title=esc(title))
        + _LAYOUT_HEADER
        + body_rows
        + _LAYOUT_FOOTER.format(
            unsubscribe_url=esc_url(unsubscribe_url),
            preferences_url=esc_url(preferences_url),
        )
        + _LAYOUT_TAIL
    )


def risk_badge(risk_level: str) -> str:
    """Return an inline-styled risk badge span.

    ``risk_level`` originates from ``analyses.overall_risk`` — an unconstrained
    ``String(20)`` column, not a DB-enforced enum — so the rendered label is
    HTML-escaped before interpolation. The colour lookup uses the normalised
    value but never trusts it inside the markup.
    """
    label = risk_level.upper()
    fg, bg, border = _RISK_COLORS.get(label, ("#0B1F24", "#D7ECE5", "#5FB7A6"))
    return (
        f'<span style="display:inline-block;padding:4px 14px;border-radius:20px;'
        f"border:1px solid {border};font-size:13px;font-weight:600;color:{fg};background-color:{bg};"
        f'letter-spacing:0.03em;">{esc(label)}</span>'
    )
