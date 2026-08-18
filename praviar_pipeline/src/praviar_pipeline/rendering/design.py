"""Design system constants - single source of truth for export styling.

Praviar's premium export system uses Forensic Teal + Clinical Copper: an
evidence-led palette for clinical trust, decisive judgment, and high-contrast
reader confidence across PDF, DOCX, PPTX, and chart renderers.
"""

from __future__ import annotations

from praviar_pipeline.models.analysis import RiskLevel

# ── Brand Palette ────────────────────────────────────────────────────────────

BRAND_INK = "#0B1F24"
BRAND_TEAL = "#0E6F68"
BRAND_MINT = "#5FB7A6"
BRAND_COPPER = "#B87333"
BRAND_PAPER = "#F6F4EF"
BRAND_ON_INK_MUTED = "#D7ECE5"
BRAND_CHART_MINT = "#8ED7C9"
BRAND_DEEP_TEAL = "#0B4F4C"
BRAND_ACCENT = BRAND_TEAL
BRAND_BORDER = "#C8D8D2"
BRAND_BODY_TEXT = BRAND_INK
BRAND_SECONDARY_TEXT = "#516F68"

# ── Risk Colors ──────────────────────────────────────────────────────────────
# Rule: color must NEVER be the sole means of conveying risk.
# Every indicator must combine color + icon shape + text label.

RISK_FILL = {
    RiskLevel.HIGH: "#C2413A",
    RiskLevel.MEDIUM: BRAND_COPPER,
    RiskLevel.LOW: BRAND_TEAL,
    RiskLevel.CLEAR: BRAND_MINT,
}

RISK_TEXT = {
    RiskLevel.HIGH: "#7F1D1D",
    RiskLevel.MEDIUM: "#8A4F1F",
    RiskLevel.LOW: "#0B4F4C",
    RiskLevel.CLEAR: BRAND_TEAL,
}

RISK_BG = {
    RiskLevel.HIGH: "#FDECEC",
    RiskLevel.MEDIUM: "#F7EEE5",
    RiskLevel.LOW: "#D7ECE5",
    RiskLevel.CLEAR: "#EAF6F2",
}

RISK_LABEL = {
    RiskLevel.HIGH: "HIGH",
    RiskLevel.MEDIUM: "MODERATE",
    RiskLevel.LOW: "LOW",
    RiskLevel.CLEAR: "CLEAR",
}

# Sort order for risk levels (highest risk first)
RISK_SORT_KEY = {
    RiskLevel.HIGH: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.LOW: 2,
    RiskLevel.CLEAR: 3,
}

# ── Chart Palette ────────────────────────────────────────────────────────────

OKABE_ITO = [
    BRAND_TEAL,
    BRAND_COPPER,
    BRAND_MINT,
    "#C2413A",
    "#516F68",
    BRAND_CHART_MINT,
    "#D7ECE5",
    BRAND_INK,
]

# ── Chart Style (matplotlib rcParams) ────────────────────────────────────────

CHART_STYLE: dict[str, object] = {
    "figure.facecolor": BRAND_PAPER,
    "axes.facecolor": BRAND_PAPER,
    "axes.edgecolor": BRAND_BORDER,
    "axes.labelcolor": BRAND_BODY_TEXT,
    "axes.titlesize": 13,
    "axes.labelsize": 10,
    "axes.grid": True,
    "grid.color": "#D9E3DE",
    "grid.linewidth": 0.5,
    "xtick.color": BRAND_SECONDARY_TEXT,
    "ytick.color": BRAND_SECONDARY_TEXT,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "text.color": BRAND_BODY_TEXT,
    "font.family": "sans-serif",
    "font.sans-serif": ["Calibri", "Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 10,
    "legend.fontsize": 9,
    "legend.frameon": False,
    "figure.dpi": 200,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.1,
}

# ── Claim Element Status Colors ──────────────────────────────────────────────

ELEMENT_STATUS_COLORS = {
    "met": "#C2413A",
    "partially_met": BRAND_COPPER,
    "not_met": BRAND_TEAL,
    "unclear": "#516F68",
}

# ── DOCX Style Specifications ────────────────────────────────────────────────

DOCX_FONTS = {
    "heading": "Calibri",
    "body": "Palatino Linotype",
    "table": "Calibri",
    "code": "Consolas",
}

DOCX_SIZES = {
    "title": 28,
    "heading1": 16,
    "heading2": 13,
    "heading3": 11,
    "body": 11,
    "table_header": 9.5,
    "table_body": 9.5,
    "caption": 8,
    "disclaimer": 8,
    "code": 9,
}

# ── Helpers ──────────────────────────────────────────────────────────────────


def risk_display(risk_level: RiskLevel) -> str:
    """Human-readable risk label."""
    return RISK_LABEL.get(risk_level, risk_level.value.upper())


def risk_sort_key(risk_level: RiskLevel) -> int:
    """Sort key for risk levels (highest first)."""
    return RISK_SORT_KEY.get(risk_level, 99)


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert '#RRGGBB' hex string to (R, G, B) tuple."""
    if not hex_color or len(hex_color) != 7 or not hex_color.startswith("#"):
        raise ValueError(f"Expected 7-char hex color (e.g. '#0B1F24'), got '{hex_color}'")
    return int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
