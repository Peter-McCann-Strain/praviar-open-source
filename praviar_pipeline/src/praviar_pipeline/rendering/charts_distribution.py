"""Funnel and risk-distribution chart helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from praviar_pipeline.rendering.charts_data import (
    build_funnel_chart_data,
    build_risk_distribution_series,
)
from praviar_pipeline.rendering.charts_export import fig_to_base64, get_plt
from praviar_pipeline.rendering.design import (
    BRAND_ACCENT,
    BRAND_PAPER,
    BRAND_SECONDARY_TEXT,
    OKABE_ITO,
    RISK_FILL,
)

if TYPE_CHECKING:
    from praviar_pipeline.models.analysis import PatentAnalysis
    from praviar_pipeline.models.audit import PipelineAuditTrail


def render_funnel_chart(audit_trail: PipelineAuditTrail) -> str:
    """Render patent funnel as horizontal bar chart. Returns base64 PNG."""
    plt = get_plt()
    stages, counts = build_funnel_chart_data(audit_trail)

    fig, ax = plt.subplots(figsize=(8, 4))
    try:
        colors = [OKABE_ITO[i % len(OKABE_ITO)] for i in range(len(stages))]
        bars = ax.barh(
            stages,
            counts,
            color=colors,
            edgecolor=BRAND_PAPER,
            linewidth=0.5,
        )

        ax.set_xlabel("Number of Patents")
        ax.set_title("Patent Search Funnel")
        ax.invert_yaxis()

        max_count = max(counts) if counts else 0
        axis_max = max(max_count, 1)
        for bar, count in zip(bars, counts, strict=False):
            offset = axis_max * 0.02
            ax.text(
                bar.get_width() + offset,
                bar.get_y() + bar.get_height() / 2,
                f"{count:,}",
                va="center",
                fontsize=10,
                fontweight="bold",
                color=BRAND_SECONDARY_TEXT,
            )

        ax.set_xlim(0, axis_max * 1.15)
        ax.grid(axis="y", visible=False)
        plt.tight_layout()
        return fig_to_base64(fig)
    except Exception:
        plt.close(fig)
        raise


def render_risk_distribution_chart(analyses: list[PatentAnalysis]) -> str:
    """Render risk-level distribution as a donut chart. Returns base64 PNG."""
    plt = get_plt()
    series = build_risk_distribution_series(analyses)

    labels = [label for _level, label, _count in series]
    sizes = [count for _level, _label, count in series]
    colors = [RISK_FILL[level] for level, _label, _count in series]

    fig, ax = plt.subplots(figsize=(6, 5))
    try:
        if sizes:
            _wedges, texts, autotexts = ax.pie(
                sizes,
                labels=labels,
                colors=colors,
                autopct="%1.0f%%",
                startangle=90,
                pctdistance=0.78,
                wedgeprops={
                    "width": 0.45,
                    "edgecolor": BRAND_PAPER,
                    "linewidth": 1.5,
                },
            )
            for text in autotexts:
                text.set_fontsize(10)
                text.set_fontweight("bold")
            for text in texts:
                text.set_fontsize(10)

            total = sum(sizes)
            ax.text(
                0,
                0,
                f"{total}\nPatents",
                ha="center",
                va="center",
                fontsize=14,
                fontweight="bold",
                color=BRAND_ACCENT,
            )
            ax.set_title("Risk Level Distribution")
        else:
            ax.text(
                0.5,
                0.5,
                "No patents analyzed",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=12,
                color=BRAND_SECONDARY_TEXT,
            )
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis("off")

        plt.tight_layout()
        return fig_to_base64(fig)
    except Exception:
        plt.close(fig)
        raise
