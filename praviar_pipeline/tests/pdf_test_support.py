from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from praviar_pipeline.manifest import ReportManifest


def make_test_report_manifest(compound_query: str) -> ReportManifest:
    """Return explicit persisted-run provenance for PDF rendering fixtures."""
    empty_digest = hashlib.sha256(b"").hexdigest()
    return ReportManifest(
        pipeline_version="test-fixture",
        source_tree_state="test",
        source_tree_digest=hashlib.sha256(b"pdf-test-source-tree").hexdigest(),
        generated_at=datetime.now(UTC),
        compound_query=compound_query,
        prompt_hashes={},
        model_versions={},
        sampling={},
        source_snapshots={"fixture": "immutable:test"},
        source_observations={},
        tool_definition_hashes={},
        tool_trace_digest=empty_digest,
        tool_trace_key_id="test-fixture",
    )
