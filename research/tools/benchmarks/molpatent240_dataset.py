"""Strict loader for the cached MolPatent-240 partial diagnostic corpus.

The repository cache contains 240 JSON rows, but only 195 rows are complete
labelled molecule-patent pairs. This module preserves that distinction and
never maps a reported pair-level scope label to an overall FTO risk.

This is research tooling only. The cached corpus is not production release
evidence: the authoritative source, licence, and source patent claims must be
reacquired and verified before a release gate can consume its results.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MOLPATENT240_PATH = (
    REPO_ROOT
    / "research"
    / "validation"
    / "external-datasets"
    / "molpatent-240"
    / "molpatent-240.json"
)
AUTHORITATIVE_SOURCE_URL = (
    "https://figshare.com/articles/dataset/molpatent-240_json/28191983"
)

# This identifies the repository's known partial cache. It is deliberately not
# described as the authoritative dataset hash.
KNOWN_PARTIAL_CACHE_SHA256 = (
    "a5dde3ff685476f54b31791b1c811ab83fca80b87a93e670d95c066e588bb296"
)
KNOWN_RAW_ROWS = 240
KNOWN_COMPLETE_PAIRS = 195
KNOWN_QUARANTINED_ROWS = 45
KNOWN_POSITIVE_PAIRS = 102
KNOWN_NEGATIVE_PAIRS = 93
KNOWN_PATENTS = 70

ReportedScopeLabel = Literal["reported_in_scope", "reported_out_of_scope"]


@dataclass(frozen=True)
class MolPatentPair:
    """One complete source row, retaining its original zero-based index."""

    source_index: int
    patent_id: str
    target_smiles: str
    reported_scope_label: ReportedScopeLabel
    selection_type: int


@dataclass(frozen=True)
class QuarantinedMolPatentRow:
    """An incomplete source row that must not be inferred or scored."""

    source_index: int
    reasons: tuple[str, ...]
    record_sha256: str
    selection_type: int | None


@dataclass(frozen=True)
class MolPatentCorpusAudit:
    """Audited view of the cache, including every usable and quarantined row."""

    source_path: Path
    source_sha256: str
    raw_row_count: int
    pairs: tuple[MolPatentPair, ...]
    quarantined_rows: tuple[QuarantinedMolPatentRow, ...]

    @property
    def positive_pair_count(self) -> int:
        return sum(
            pair.reported_scope_label == "reported_in_scope" for pair in self.pairs
        )

    @property
    def negative_pair_count(self) -> int:
        return sum(
            pair.reported_scope_label == "reported_out_of_scope" for pair in self.pairs
        )

    @property
    def patent_count(self) -> int:
        return len({pair.patent_id for pair in self.pairs})


def _record_digest(record: Any) -> str:
    encoded = json.dumps(
        record,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _quarantine_reasons(record: Any) -> tuple[str, ...]:
    if not isinstance(record, dict):
        return ("row_not_object",)

    reasons: list[str] = []
    patent_id = record.get("patent_id")
    if not isinstance(patent_id, str) or not patent_id.strip():
        reasons.append("missing_patent_id")

    smiles = record.get("target_smiles")
    if not isinstance(smiles, str) or not smiles.strip():
        reasons.append("missing_target_smiles")

    if "label" not in record:
        reasons.append("missing_label")
    elif not isinstance(record["label"], bool):
        reasons.append("label_not_boolean")

    selection_type = record.get("selection_type")
    if not isinstance(selection_type, int) or isinstance(selection_type, bool):
        reasons.append("selection_type_not_integer")

    return tuple(reasons)


def load_molpatent240_audit(
    source_path: Path = DEFAULT_MOLPATENT240_PATH,
    *,
    enforce_known_partial_cache: bool = True,
) -> MolPatentCorpusAudit:
    """Load the cached corpus and fail closed on unreviewed content drift."""

    raw_bytes = source_path.read_bytes()
    source_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    if enforce_known_partial_cache and source_sha256 != KNOWN_PARTIAL_CACHE_SHA256:
        raise ValueError(
            "MolPatent-240 cache hash changed; reacquire and review the source "
            "before updating KNOWN_PARTIAL_CACHE_SHA256"
        )

    payload = json.loads(raw_bytes)
    if not isinstance(payload, list):
        raise ValueError("MolPatent-240 cache must be a top-level JSON array")

    pairs: list[MolPatentPair] = []
    quarantined: list[QuarantinedMolPatentRow] = []
    for source_index, record in enumerate(payload):
        reasons = _quarantine_reasons(record)
        if reasons:
            selection_type = (
                record.get("selection_type") if isinstance(record, dict) else None
            )
            quarantined.append(
                QuarantinedMolPatentRow(
                    source_index=source_index,
                    reasons=reasons,
                    record_sha256=_record_digest(record),
                    selection_type=(
                        selection_type
                        if isinstance(selection_type, int)
                        and not isinstance(selection_type, bool)
                        else None
                    ),
                )
            )
            continue

        assert isinstance(record, dict)
        label = record["label"]
        pairs.append(
            MolPatentPair(
                source_index=source_index,
                patent_id=record["patent_id"].strip(),
                target_smiles=record["target_smiles"].strip(),
                reported_scope_label=(
                    "reported_in_scope" if label else "reported_out_of_scope"
                ),
                selection_type=record["selection_type"],
            )
        )

    audit = MolPatentCorpusAudit(
        source_path=source_path,
        source_sha256=source_sha256,
        raw_row_count=len(payload),
        pairs=tuple(pairs),
        quarantined_rows=tuple(quarantined),
    )
    if enforce_known_partial_cache:
        assert_known_partial_cache_shape(audit)
    return audit


def assert_known_partial_cache_shape(audit: MolPatentCorpusAudit) -> None:
    """Reject silent row loss, default labels, or unexpected cache expansion."""

    observed = {
        "raw_rows": audit.raw_row_count,
        "complete_pairs": len(audit.pairs),
        "quarantined_rows": len(audit.quarantined_rows),
        "positive_pairs": audit.positive_pair_count,
        "negative_pairs": audit.negative_pair_count,
        "patents": audit.patent_count,
    }
    expected = {
        "raw_rows": KNOWN_RAW_ROWS,
        "complete_pairs": KNOWN_COMPLETE_PAIRS,
        "quarantined_rows": KNOWN_QUARANTINED_ROWS,
        "positive_pairs": KNOWN_POSITIVE_PAIRS,
        "negative_pairs": KNOWN_NEGATIVE_PAIRS,
        "patents": KNOWN_PATENTS,
    }
    if observed != expected:
        raise ValueError(
            f"MolPatent-240 partial cache shape changed: "
            f"observed={observed}, expected={expected}"
        )


def build_partial_diagnostic(audit: MolPatentCorpusAudit) -> dict[str, Any]:
    """Build the dedicated pair-level diagnostic payload.

    No field in this payload represents infringement, blocking status, or an
    overall FTO risk. Those conclusions require legal claim construction and
    current jurisdiction-specific evidence that the cache does not contain.
    """

    return {
        "schema_version": "markush_scope_benchmark/v2",
        "dataset_id": "molpatent-240",
        "dataset_status": "partial_cache_diagnostic",
        "release_evidence_eligible": False,
        "authoritative_source_url": AUTHORITATIVE_SOURCE_URL,
        "source_cache_sha256": f"sha256:{audit.source_sha256}",
        "licence_status": "requires_reverification",
        "task_definition": (
            "Pair-level reproduction of the source dataset's reported molecule "
            "scope label. It is not an infringement, blocker, or overall FTO label."
        ),
        "limitations": [
            "45 of 240 cached rows are incomplete and quarantined.",
            "The authoritative source file and licence have not been reverified.",
            "Source patent PDFs, claim text, family scope, legal status, and jurisdiction are absent.",
            "Results must not be mapped to an overall FTO risk or production release claim.",
        ],
        "statistics": {
            "raw_rows": audit.raw_row_count,
            "complete_pairs": len(audit.pairs),
            "quarantined_rows": len(audit.quarantined_rows),
            "reported_in_scope": audit.positive_pair_count,
            "reported_out_of_scope": audit.negative_pair_count,
            "unique_patents": audit.patent_count,
        },
        "pairs": [
            {
                "id": f"MOLPATENT-PAIR-{pair.source_index:03d}",
                "source_index": pair.source_index,
                "patent_id": pair.patent_id,
                "target_smiles": pair.target_smiles,
                "reported_scope_label": pair.reported_scope_label,
                "selection_type": pair.selection_type,
            }
            for pair in audit.pairs
        ],
        "quarantine": [
            {
                "source_index": row.source_index,
                "reasons": list(row.reasons),
                "record_sha256": f"sha256:{row.record_sha256}",
                "selection_type": row.selection_type,
            }
            for row in audit.quarantined_rows
        ],
    }
