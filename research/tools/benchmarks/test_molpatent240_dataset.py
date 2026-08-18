from __future__ import annotations

import json
from pathlib import Path

import pytest

from molpatent240_dataset import (
    DEFAULT_MOLPATENT240_PATH,
    KNOWN_PARTIAL_CACHE_SHA256,
    build_partial_diagnostic,
    load_molpatent240_audit,
)


def test_known_partial_cache_is_audited_without_default_labels() -> None:
    audit = load_molpatent240_audit()

    assert audit.source_sha256 == KNOWN_PARTIAL_CACHE_SHA256
    assert audit.raw_row_count == 240
    assert len(audit.pairs) == 195
    assert len(audit.quarantined_rows) == 45
    assert audit.positive_pair_count == 102
    assert audit.negative_pair_count == 93
    assert audit.patent_count == 70
    assert sum("missing_label" in row.reasons for row in audit.quarantined_rows) == 2


def test_diagnostic_is_pair_level_and_never_claims_fto_outcomes() -> None:
    diagnostic = build_partial_diagnostic(load_molpatent240_audit())
    serialized = json.dumps(diagnostic, sort_keys=True)

    assert diagnostic["schema_version"] == "markush_scope_benchmark/v2"
    assert diagnostic["dataset_status"] == "partial_cache_diagnostic"
    assert diagnostic["release_evidence_eligible"] is False
    assert len(diagnostic["pairs"]) == 195
    assert len(diagnostic["quarantine"]) == 45
    assert "_molpatent_test_molecules" not in serialized
    assert "overall_risk" not in serialized
    assert "blocking_patents" not in serialized
    assert "expected_risk_level" not in serialized


def test_diagnostic_conforms_to_dedicated_pair_schema() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "validation/benchmark-conversion/schemas/"
        "markush_scope_benchmark_v2.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    jsonschema.Draft202012Validator(schema).validate(
        build_partial_diagnostic(load_molpatent240_audit())
    )


def test_loader_fails_closed_when_cache_content_changes(tmp_path: Path) -> None:
    changed = tmp_path / "molpatent-240.json"
    changed.write_bytes(DEFAULT_MOLPATENT240_PATH.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="cache hash changed"):
        load_molpatent240_audit(changed)


def test_missing_label_pair_is_quarantined_not_inferred(tmp_path: Path) -> None:
    source = tmp_path / "fixture.json"
    source.write_text(
        json.dumps([{"patent_id": "US1", "target_smiles": "CC", "selection_type": 1}]),
        encoding="utf-8",
    )

    audit = load_molpatent240_audit(
        source,
        enforce_known_partial_cache=False,
    )

    assert audit.pairs == ()
    assert audit.quarantined_rows[0].reasons == ("missing_label",)
