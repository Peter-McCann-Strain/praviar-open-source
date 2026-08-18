"""Compatibility facade for matter evidence index record builders."""

from __future__ import annotations

from praviar_pipeline.pipeline.report.evidence_index_families import (
    build_family_gate_failures,
    build_family_record,
)
from praviar_pipeline.pipeline.report.evidence_index_patents import build_patent_record
from praviar_pipeline.pipeline.report.evidence_index_shared import (
    collect_material_patent_ids,
    unique_strings,
)

__all__ = [
    "build_family_gate_failures",
    "build_family_record",
    "build_patent_record",
    "collect_material_patent_ids",
    "unique_strings",
]
