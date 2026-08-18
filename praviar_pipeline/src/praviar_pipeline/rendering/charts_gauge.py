"""Risk gauge chart helper."""

from __future__ import annotations

import math

from praviar_pipeline.models.analysis import RiskLevel
from praviar_pipeline.rendering.charts_export import fig_to_base64, get_plt
from praviar_pipeline.rendering.design import (
    BRAND_ACCENT,
    BRAND_INK,
    BRAND_PAPER,
    BRAND_SECONDARY_TEXT,
    RISK_FILL,
)


def render_risk_gauge(
    overall_risk: RiskLevel,
    blocking_count: int,
    total_analyzed: int,
) -> str:
    """Render a semicircular risk gauge. Returns base64 PNG."""
    if not isinstance(blocking_count, int) or blocking_count < 0:
        blocking_count = 0
    if not isinstance(total_analyzed, int) or total_analyzed < 0:
        total_analyzed = 0

    plt = get_plt()
    from matplotlib.patches import Wedge

    risk_value_map = {
        RiskLevel.CLEAR: 15,
        RiskLevel.LOW: 35,
        RiskLevel.MEDIUM: 65,
        RiskLevel.HIGH: 85,
    }
    value = risk_value_map.get(overall_risk, 50)

    fig, ax = plt.subplots(figsize=(6, 3.5), subplot_kw={"aspect": "equal"})
    try:
        segments = [
            (0, 25, RISK_FILL[RiskLevel.CLEAR]),
            (25, 50, RISK_FILL[RiskLevel.LOW]),
            (50, 75, RISK_FILL[RiskLevel.MEDIUM]),
            (75, 100, RISK_FILL[RiskLevel.HIGH]),
        ]

        for seg_start, seg_end, color in segments:
            theta1 = 180 - (seg_end / 100) * 180
            theta2 = 180 - (seg_start / 100) * 180
            wedge = Wedge(
                center=(0, 0),
                r=1.0,
                theta1=theta1,
                theta2=theta2,
                width=0.3,
                facecolor=color,
                edgecolor=BRAND_PAPER,
                linewidth=1,
                alpha=0.8,
            )
            ax.add_patch(wedge)

        needle_angle = math.radians(180 - (value / 100) * 180)
        needle_len = 0.75
        nx = needle_len * math.cos(needle_angle)
        ny = needle_len * math.sin(needle_angle)
        ax.annotate(
            "",
            xy=(nx, ny),
            xytext=(0, 0),
            arrowprops={
                "arrowstyle": "-|>",
                "color": BRAND_INK,
                "lw": 2.5,
                "mutation_scale": 15,
            },
        )
        ax.plot(0, 0, "o", color=BRAND_INK, markersize=8, zorder=10)

        ax.text(
            0,
            -0.25,
            f"{blocking_count}/{total_analyzed}",
            ha="center",
            va="center",
            fontsize=18,
            fontweight="bold",
            color=RISK_FILL.get(overall_risk, BRAND_ACCENT),
        )
        ax.text(
            0,
            -0.45,
            "blocking patents",
            ha="center",
            va="center",
            fontsize=10,
            color=BRAND_SECONDARY_TEXT,
        )

        risk_label = overall_risk.value.upper()
        ax.text(
            0,
            1.15,
            f"Overall Risk: {risk_label}",
            ha="center",
            va="center",
            fontsize=13,
            fontweight="bold",
            color=RISK_FILL.get(overall_risk, BRAND_ACCENT),
        )

        for pos, label in [(0, "CLEAR"), (25, ""), (50, ""), (75, ""), (100, "HIGH")]:
            angle = math.radians(180 - (pos / 100) * 180)
            lx = 1.15 * math.cos(angle)
            ly = 1.15 * math.sin(angle)
            ax.text(lx, ly, label, ha="center", va="center", fontsize=8, color=BRAND_SECONDARY_TEXT)

        ax.set_xlim(-1.5, 1.5)
        ax.set_ylim(-0.6, 1.4)
        ax.axis("off")
        plt.tight_layout()
        return fig_to_base64(fig)
    except Exception:
        plt.close(fig)
        raise
