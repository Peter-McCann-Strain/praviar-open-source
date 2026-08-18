"""Chart-building facade for Matplotlib-based renderers."""

from __future__ import annotations

from praviar_pipeline.rendering.charts_distribution import (
    render_funnel_chart,
    render_risk_distribution_chart,
)
from praviar_pipeline.rendering.charts_gauge import render_risk_gauge
from praviar_pipeline.rendering.charts_timeline import (
    render_assignee_chart,
    render_patent_timeline,
    render_source_health_chart,
    render_timing_waterfall,
)

__all__ = [
    "render_assignee_chart",
    "render_funnel_chart",
    "render_patent_timeline",
    "render_risk_distribution_chart",
    "render_risk_gauge",
    "render_source_health_chart",
    "render_timing_waterfall",
]
