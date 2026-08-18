"""Static chart generation using Matplotlib (Agg backend).

All public functions return base64-encoded PNG strings. Run in
``asyncio.to_thread()`` when called from an async context.

This module is a thin facade over the chart data, builder, and export
helpers in ``praviar_pipeline.rendering.charts_*`` so the public API stays
stable while the implementation stays composable.
"""

from __future__ import annotations

from praviar_pipeline.rendering.charts_builders import (
    render_assignee_chart,
    render_funnel_chart,
    render_patent_timeline,
    render_risk_distribution_chart,
    render_risk_gauge,
    render_source_health_chart,
    render_timing_waterfall,
)
from praviar_pipeline.rendering.charts_data import fmt_duration as _fmt_duration

__all__ = [
    "_fmt_duration",
    "render_assignee_chart",
    "render_funnel_chart",
    "render_patent_timeline",
    "render_risk_distribution_chart",
    "render_risk_gauge",
    "render_source_health_chart",
    "render_timing_waterfall",
]
