"""Timeline, assignee, timing, and source-health chart helpers."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from praviar_pipeline.models.analysis import PatentAnalysis, RiskLevel
from praviar_pipeline.rendering.charts_data import (
    build_assignee_series,
    build_patent_timeline_entries,
    build_timing_series,
    fmt_duration,
    normalize_source_entries,
)
from praviar_pipeline.rendering.charts_export import fig_to_base64, get_plt
from praviar_pipeline.rendering.design import (
    BRAND_COPPER,
    BRAND_PAPER,
    BRAND_SECONDARY_TEXT,
    BRAND_TEAL,
    OKABE_ITO,
    RISK_FILL,
    RISK_LABEL,
)

if TYPE_CHECKING:
    from praviar_pipeline.models.audit import PipelineAuditTrail


def _render_empty_chart(message: str, *, figsize: tuple[float, float]) -> str:
    plt = get_plt()
    fig, ax = plt.subplots(figsize=figsize)
    try:
        ax.text(
            0.5,
            0.5,
            message,
            ha="center",
            va="center",
            transform=ax.transAxes,
            fontsize=12,
            color=BRAND_SECONDARY_TEXT,
        )
        ax.axis("off")
        plt.tight_layout()
        return fig_to_base64(fig)
    except Exception:
        plt.close(fig)
        raise


def render_patent_timeline(
    analyses: list[PatentAnalysis],
    patent_details: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Render a horizontal Gantt chart of patent lifespans coloured by risk."""
    plt = get_plt()
    today = date.today()
    entries = build_patent_timeline_entries(analyses, patent_details)

    if not entries:
        return _render_empty_chart("No patent timeline data available", figsize=(10, 3))

    labels = [entry[0] for entry in entries]
    fig_height = max(3, 0.5 * len(entries) + 1.5)
    fig, ax = plt.subplots(figsize=(10, fig_height))
    try:
        from matplotlib.dates import DateFormatter, YearLocator, date2num
        from matplotlib.patches import Patch

        for idx, (_label, filing, expiry, risk) in enumerate(entries):
            color = RISK_FILL.get(risk, OKABE_ITO[0])
            start = date2num(filing)
            end = date2num(expiry)
            ax.barh(
                idx,
                end - start,
                left=start,
                color=color,
                edgecolor=BRAND_PAPER,
                linewidth=0.5,
                height=0.6,
                alpha=0.85,
            )

        today_num = date2num(today)
        ax.axvline(
            x=today_num,
            color=BRAND_COPPER,
            linestyle="--",
            linewidth=1.5,
            zorder=5,
        )
        ax.text(
            today_num,
            -0.5,
            " Today",
            va="top",
            ha="left",
            fontsize=9,
            color=BRAND_COPPER,
            fontweight="bold",
        )

        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels, fontsize=9)
        ax.set_title("Patent Expiry Timeline")
        ax.set_xlabel("Year")
        ax.xaxis.set_major_locator(YearLocator(5))
        ax.xaxis.set_major_formatter(DateFormatter("%Y"))

        all_dates = [entry[1] for entry in entries] + [entry[2] for entry in entries] + [today]
        min_date = min(all_dates)
        max_date = max(all_dates)
        margin_days = max(365, int((max_date - min_date).days * 0.05))
        ax.set_xlim(
            date2num(min_date - timedelta(days=margin_days)),
            date2num(max_date + timedelta(days=margin_days)),
        )
        ax.grid(axis="y", visible=False)
        ax.invert_yaxis()

        legend_elements = [
            Patch(facecolor=RISK_FILL[rl], label=RISK_LABEL[rl])
            for rl in [RiskLevel.HIGH, RiskLevel.MEDIUM, RiskLevel.LOW, RiskLevel.CLEAR]
        ]
        ax.legend(handles=legend_elements, loc="lower right", fontsize=8)

        plt.tight_layout()
        return fig_to_base64(fig)
    except Exception:
        plt.close(fig)
        raise


def render_assignee_chart(analyses: list[PatentAnalysis]) -> str:
    """Render top-10 assignee patent counts as horizontal bar chart."""
    plt = get_plt()
    top_10 = build_assignee_series(analyses)

    if not top_10:
        return _render_empty_chart("No assignee data available", figsize=(8, 4))

    names = [item[0] for item in top_10]
    counts = [item[1] for item in top_10]
    colors = [OKABE_ITO[i % len(OKABE_ITO)] for i in range(len(names))]

    fig_height = max(3.5, 0.45 * len(names) + 1.5)
    fig, ax = plt.subplots(figsize=(8, fig_height))
    try:
        bars = ax.barh(names, counts, color=colors, edgecolor=BRAND_PAPER, linewidth=0.5)

        ax.set_xlabel("Number of Patents")
        ax.set_title("Top Patent Assignees")
        ax.grid(axis="y", visible=False)

        max_count = max(counts) if counts else 1
        for bar, count in zip(bars, counts, strict=False):
            ax.text(
                bar.get_width() + max_count * 0.02,
                bar.get_y() + bar.get_height() / 2,
                str(count),
                va="center",
                fontsize=10,
                fontweight="bold",
                color=BRAND_SECONDARY_TEXT,
            )

        ax.set_xlim(0, max_count * 1.15)
        truncated = [n[:40] + "..." if len(n) > 40 else n for n in names]
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(truncated, fontsize=9)

        plt.tight_layout()
        return fig_to_base64(fig)
    except Exception:
        plt.close(fig)
        raise


def render_timing_waterfall(audit_trail: PipelineAuditTrail) -> str:
    """Render pipeline step durations as horizontal bar chart."""
    plt = get_plt()
    steps = build_timing_series(audit_trail)

    if not steps:
        return _render_empty_chart("No timing data available", figsize=(8, 3))

    names = [name for name, _duration in steps]
    durations = [duration for _name, duration in steps]
    colors = [OKABE_ITO[i % len(OKABE_ITO)] for i in range(len(names))]

    fig_height = max(3, 0.45 * len(names) + 1.5)
    fig, ax = plt.subplots(figsize=(8, fig_height))
    try:
        bars = ax.barh(names, durations, color=colors, edgecolor=BRAND_PAPER, linewidth=0.5)

        ax.set_xlabel("Duration")
        ax.set_title("Pipeline Step Timing")
        ax.grid(axis="y", visible=False)
        ax.invert_yaxis()

        max_dur = max(durations) if durations else 1
        for bar, dur in zip(bars, durations, strict=False):
            label = fmt_duration(dur)
            ax.text(
                bar.get_width() + max_dur * 0.02,
                bar.get_y() + bar.get_height() / 2,
                label,
                va="center",
                fontsize=10,
                fontweight="bold",
                color=BRAND_SECONDARY_TEXT,
            )

        ax.set_xlim(0, max_dur * 1.2)

        from matplotlib.ticker import FuncFormatter

        ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: fmt_duration(max(0, x))))

        plt.tight_layout()
        return fig_to_base64(fig)
    except Exception:
        plt.close(fig)
        raise


def render_source_health_chart(source_entries: list[Any]) -> str:
    """Render patent count per source with status colouring. Returns base64 PNG."""
    plt = get_plt()

    if not source_entries:
        return _render_empty_chart("No source data available", figsize=(8, 3))

    status_colors = {
        "OK": BRAND_TEAL,
        "FAILED": RISK_FILL[RiskLevel.HIGH],
        "SKIPPED": BRAND_SECONDARY_TEXT,
    }

    normalized = normalize_source_entries(source_entries)
    names = [item[0] for item in normalized]
    counts = [item[2] for item in normalized]
    colors = [status_colors.get(item[1], BRAND_SECONDARY_TEXT) for item in normalized]

    fig_height = max(3, 0.45 * len(names) + 1.5)
    fig, ax = plt.subplots(figsize=(8, fig_height))
    try:
        bars = ax.barh(names, counts, color=colors, edgecolor=BRAND_PAPER, linewidth=0.5)

        ax.set_xlabel("Patents Found")
        ax.set_title("Source Health")
        ax.grid(axis="y", visible=False)

        max_count = max(counts) if counts else 1
        for bar, count in zip(bars, counts, strict=False):
            ax.text(
                bar.get_width() + max_count * 0.02,
                bar.get_y() + bar.get_height() / 2,
                str(count),
                va="center",
                fontsize=10,
                fontweight="bold",
                color=BRAND_SECONDARY_TEXT,
            )

        ax.set_xlim(0, max(max_count * 1.15, 1))

        from matplotlib.patches import Patch

        legend_elements = [
            Patch(facecolor=color, label=status) for status, color in status_colors.items()
        ]
        ax.legend(handles=legend_elements, loc="lower right", fontsize=8)

        plt.tight_layout()
        return fig_to_base64(fig)
    except Exception:
        plt.close(fig)
        raise
