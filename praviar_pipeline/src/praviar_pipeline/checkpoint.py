"""Pipeline checkpoint save/load for resume-on-failure.

Saves pipeline state after each step so that a failed run can be resumed
from the last completed step instead of restarting from scratch.

Usage:
    # Save after each step:
    save_checkpoint(
        build_checkpoint(run_id, 3, compound=compound, ...),
        checkpoint_dir,
        integrity_keys=key_ring,
    )

    # Resume a failed run:
    ckpt = load_latest_checkpoint(checkpoint_dir, integrity_keys=key_ring)
    state = restore_from_checkpoint(ckpt)
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from re import fullmatch
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from praviar_pipeline.checkpoint_restoration import restore_checkpoint_state
from praviar_pipeline.checkpoint_serialization import (
    serialize_checkpoint_value,
    serialize_drawing_results,
)
from praviar_pipeline.utils.private_artifacts import (
    atomic_write_text,
    ensure_private_directory,
    private_file_for_read,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

logger = structlog.get_logger()

CHECKPOINT_INTEGRITY_SCHEMA_VERSION: Literal["checkpoint-integrity-v3"] = "checkpoint-integrity-v3"
CHECKPOINT_INTEGRITY_ALGORITHM: Literal["HMAC-SHA256"] = "HMAC-SHA256"
CHECKPOINT_INTEGRITY_DOMAIN = "praviar:pipeline-checkpoint:checkpoint-integrity-v2"
CHECKPOINT_INTEGRITY_MIN_KEY_BYTES = 32
DEV_CHECKPOINT_HMAC_KEYRING_SECRET = json.dumps(
    {
        "active_key_id": "dev-v1",
        "keys": {
            "dev-v1": "dev-pipeline-checkpoint-hmac-key-not-for-production-0001",
        },
    },
    sort_keys=True,
    separators=(",", ":"),
)


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def _validate_checkpoint_key_id(key_id: str) -> str:
    normalized = str(key_id or "").strip()
    if fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", normalized) is None:
        raise ValueError("checkpoint integrity key id is invalid")
    return normalized


@dataclass(frozen=True, repr=False)
class CheckpointIntegrityKeyRing:
    """Runtime-only checkpoint signing and verification keys.

    The serialized checkpoint and manifest contain only ``active_key_id``.
    Key bytes remain process-local and are deliberately omitted from repr.
    Keeping older keys in the ring permits deliberate key rotation while new
    checkpoints are always signed by the active key.
    """

    active_key_id: str
    _keys: Mapping[str, bytes] = field(repr=False)

    def __post_init__(self) -> None:
        active_key_id = _validate_checkpoint_key_id(self.active_key_id)
        validated: dict[str, bytes] = {}
        for raw_key_id, raw_secret in self._keys.items():
            key_id = _validate_checkpoint_key_id(raw_key_id)
            secret = bytes(raw_secret)
            if len(secret) < CHECKPOINT_INTEGRITY_MIN_KEY_BYTES:
                raise ValueError("checkpoint integrity keys must contain at least 32 bytes")
            validated[key_id] = secret
        if active_key_id not in validated:
            raise ValueError("active checkpoint integrity key is absent from key ring")
        object.__setattr__(self, "active_key_id", active_key_id)
        object.__setattr__(self, "_keys", MappingProxyType(validated))

    def __repr__(self) -> str:
        return (
            "CheckpointIntegrityKeyRing("
            f"active_key_id={self.active_key_id!r}, key_ids={sorted(self._keys)!r})"
        )

    @classmethod
    def from_secret(cls, serialized_secret: str) -> CheckpointIntegrityKeyRing:
        """Parse the dedicated JSON key-ring secret without retaining raw text."""
        if not str(serialized_secret or "").strip():
            raise ValueError("pipeline checkpoint integrity key is required")
        try:
            payload = json.loads(serialized_secret)
        except json.JSONDecodeError as exc:
            raise ValueError("pipeline checkpoint integrity key ring is malformed") from exc
        if not isinstance(payload, dict) or set(payload) != {"active_key_id", "keys"}:
            raise ValueError("pipeline checkpoint integrity key ring has invalid fields")
        raw_keys = payload.get("keys")
        if not isinstance(raw_keys, dict) or not raw_keys:
            raise ValueError("pipeline checkpoint integrity key ring must contain keys")
        keys: dict[str, bytes] = {}
        for key_id, secret in raw_keys.items():
            if not isinstance(key_id, str) or not isinstance(secret, str):
                raise ValueError("pipeline checkpoint integrity key ring entries are invalid")
            keys[key_id] = secret.encode("utf-8")
        return cls(active_key_id=str(payload.get("active_key_id") or ""), _keys=keys)

    def active_key(self) -> bytes:
        return self._keys[self.active_key_id]

    def verification_key(self, key_id: str) -> bytes:
        try:
            return self._keys[key_id]
        except KeyError as exc:
            raise ValueError("checkpoint integrity key id is unavailable") from exc


class CheckpointIntegrityManifest(BaseModel):
    """Content-addressed binding for one checkpoint payload and its patent hits."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["checkpoint-integrity-v3"] = CHECKPOINT_INTEGRITY_SCHEMA_VERSION
    algorithm: Literal["HMAC-SHA256"] = CHECKPOINT_INTEGRITY_ALGORITHM
    key_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    checkpoint_file: str
    run_id: str
    completed_step: int
    checkpoint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    patent_hits_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    trusted_claim_text_cassette_sha256: list[str] = Field(default_factory=list)
    trusted_legal_status_cassette_sha256: list[str] = Field(default_factory=list)
    hmac_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def _manifest_unsigned_fields(manifest: CheckpointIntegrityManifest | Mapping[str, object]) -> dict:
    payload = (
        manifest.model_dump(mode="json")
        if isinstance(manifest, CheckpointIntegrityManifest)
        else dict(manifest)
    )
    payload.pop("hmac_sha256", None)
    return payload


def _checkpoint_hmac_message(
    *,
    canonical_checkpoint_payload: object,
    unsigned_manifest: Mapping[str, object],
) -> bytes:
    return _canonical_json_bytes(
        {
            "domain": CHECKPOINT_INTEGRITY_DOMAIN,
            "canonical_checkpoint_payload": canonical_checkpoint_payload,
            "manifest": dict(unsigned_manifest),
        }
    )


def _checkpoint_hmac_sha256(
    *,
    key: bytes,
    canonical_checkpoint_payload: object,
    unsigned_manifest: Mapping[str, object],
) -> str:
    return hmac.new(
        key,
        _checkpoint_hmac_message(
            canonical_checkpoint_payload=canonical_checkpoint_payload,
            unsigned_manifest=unsigned_manifest,
        ),
        hashlib.sha256,
    ).hexdigest()


class PipelineCheckpoint(BaseModel):
    """Serializable snapshot of pipeline state after each completed step.

    Step numbering:
        1 = step1_resolve (compound)
        2 = step1b_expand (expanded queries)
        3 = step2_search (patent hits, source health, search funnel)
        4 = step2c_families (patent hits enriched with families)
        5 = claims and live-evidence enrichment
        6 = step3_triage (triage results + tokens)
        7 = post-triage drawing enrichment
        8 = step4_analyze (analyses, failures, traces)
        9 = step4b_critic (critic review)
       10 = step5_doe (DoE assessments + tokens)
       11 = step6_invalid (invalidity assessments + tokens)
       12 = step7_verify (verification result)
       13 = step8_report (final output written)
    """

    model_config = ConfigDict(extra="forbid")

    _restore_capability: object | None = PrivateAttr(default=None)
    _trusted_claim_text_cassette_sha256: frozenset[str] = PrivateAttr(default_factory=frozenset)
    _trusted_legal_status_cassette_sha256: frozenset[str] = PrivateAttr(default_factory=frozenset)

    run_id: str
    completed_step: int
    compound_input: str
    execution_profile: str = "world_class_adaptive"
    analysis_escalation_reasons: list[str] = Field(default_factory=list)
    started_at_epoch: float = 0.0
    deadline_epoch: float | None = None

    # Step 1 output
    compound: dict | None = None

    # Step 1.5 output
    expanded_queries: dict | None = None

    # Step 2 output
    patent_hits: list[dict] | None = None
    source_health: dict | None = None
    search_funnel: list[dict] | None = None
    matter_graph: dict | None = None
    matter_graph_summary: dict | None = None
    matter_store: dict | None = None
    evidence_artifacts: list[dict] | None = None
    evidence_adapter_results: list[dict] | None = None
    collector_runs: list[dict] | None = None

    # Step 2.75 output (drawing analysis)
    drawing_results: dict | None = None

    # Step 3 output
    triage_results: list[dict] | None = None
    all_triage_results: list[dict] | None = None
    triage_input_tokens: int = 0
    triage_output_tokens: int = 0
    triage_failed: int = 0

    # Step 4 output
    analyses: list[dict] | None = None
    analysis_failures: list[dict] | None = None
    prosecution_cache: dict | None = None
    reasoning_traces: list[dict] | None = None

    # Step 4.5 output (critic review)
    critic_report: dict | None = None
    critic_input_tokens: int = 0
    critic_output_tokens: int = 0

    # Search loop metadata
    search_loop_result: dict | None = None

    # Step 5 output
    doe_assessments: list[dict] | None = None
    doe_input_tokens: int = 0
    doe_output_tokens: int = 0

    # Step 6 output
    invalidity_assessments: list[dict] | None = None
    inv_input_tokens: int = 0
    inv_output_tokens: int = 0

    # Step 7 output
    verification: dict | None = None

    # Step 2.5 output (regulatory enrichment — persisted so resume skips re-querying paid sources)
    regulatory_exclusivity: dict | None = None

    # Timing data accumulated across steps
    timing_data: list[dict] | None = None


def save_checkpoint(
    checkpoint: PipelineCheckpoint,
    checkpoint_dir: Path,
    *,
    integrity_keys: CheckpointIntegrityKeyRing,
) -> None:
    """Persist checkpoint to disk after a step completes.

    Writes atomically: serialize to a sibling temp file, flush + fsync the file
    contents to stable storage, then ``os.replace`` it onto the final path
    (atomic on POSIX). This guarantees ``load_latest_checkpoint`` never observes
    a truncated/partial ``step_*.json`` if the process is killed mid-write.
    """
    ensure_private_directory(checkpoint_dir)
    path = checkpoint_dir / f"step_{checkpoint.completed_step}.json"
    manifest_path = path.with_suffix(".manifest.json")
    payload = checkpoint.model_dump_json(indent=2)
    payload_bytes = payload.encode("utf-8")
    canonical_checkpoint_payload = checkpoint.model_dump(mode="json")
    unsigned_manifest = {
        "schema_version": CHECKPOINT_INTEGRITY_SCHEMA_VERSION,
        "algorithm": CHECKPOINT_INTEGRITY_ALGORITHM,
        "key_id": integrity_keys.active_key_id,
        "checkpoint_file": path.name,
        "run_id": checkpoint.run_id,
        "completed_step": checkpoint.completed_step,
        "checkpoint_sha256": hashlib.sha256(payload_bytes).hexdigest(),
        "patent_hits_sha256": _canonical_sha256(checkpoint.patent_hits),
        "trusted_claim_text_cassette_sha256": sorted(
            checkpoint._trusted_claim_text_cassette_sha256
        ),
        "trusted_legal_status_cassette_sha256": sorted(
            checkpoint._trusted_legal_status_cassette_sha256
        ),
    }
    signature = _checkpoint_hmac_sha256(
        key=integrity_keys.active_key(),
        canonical_checkpoint_payload=canonical_checkpoint_payload,
        unsigned_manifest=unsigned_manifest,
    )
    manifest = CheckpointIntegrityManifest(
        schema_version=CHECKPOINT_INTEGRITY_SCHEMA_VERSION,
        algorithm=CHECKPOINT_INTEGRITY_ALGORITHM,
        key_id=integrity_keys.active_key_id,
        checkpoint_file=path.name,
        run_id=checkpoint.run_id,
        completed_step=checkpoint.completed_step,
        checkpoint_sha256=hashlib.sha256(payload_bytes).hexdigest(),
        patent_hits_sha256=_canonical_sha256(checkpoint.patent_hits),
        trusted_claim_text_cassette_sha256=sorted(checkpoint._trusted_claim_text_cassette_sha256),
        trusted_legal_status_cassette_sha256=sorted(
            checkpoint._trusted_legal_status_cassette_sha256
        ),
        hmac_sha256=signature,
    )
    manifest_payload = manifest.model_dump_json(indent=2)
    atomic_write_text(path, payload)
    atomic_write_text(manifest_path, manifest_payload)
    logger.info(
        "checkpoint_saved",
        step=checkpoint.completed_step,
    )


def _checkpoint_step_number(path: Path) -> int:
    """Extract the integer step from a ``step_<N>.json`` filename.

    Used as the sort key so the *latest* checkpoint is chosen by step number,
    not lexically (lexical order ranks ``step_9`` above ``step_12``).
    """
    try:
        return int(path.stem.split("_", 1)[1])
    except (IndexError, ValueError):
        return -1


def load_latest_checkpoint(
    checkpoint_dir: Path,
    *,
    integrity_keys: CheckpointIntegrityKeyRing,
) -> PipelineCheckpoint | None:
    """Load the most recent checkpoint from disk."""
    if not checkpoint_dir.exists():
        return None
    ensure_private_directory(checkpoint_dir)
    files = sorted(
        (
            path
            for path in checkpoint_dir.glob("step_*.json")
            if fullmatch(r"step_[0-9]+\.json", path.name)
        ),
        key=_checkpoint_step_number,
        reverse=True,
    )
    if not files:
        return None
    path = files[0]
    manifest_path = path.with_suffix(".manifest.json")
    if not manifest_path.exists():
        raise ValueError(f"checkpoint integrity manifest missing: {manifest_path.name}")
    payload_bytes = private_file_for_read(path).read_bytes()
    manifest = CheckpointIntegrityManifest.model_validate_json(
        private_file_for_read(manifest_path).read_text()
    )
    try:
        canonical_checkpoint_payload = json.loads(payload_bytes)
    except json.JSONDecodeError as exc:
        raise ValueError("checkpoint payload is malformed") from exc
    verification_key = integrity_keys.verification_key(manifest.key_id)
    expected_hmac = _checkpoint_hmac_sha256(
        key=verification_key,
        canonical_checkpoint_payload=canonical_checkpoint_payload,
        unsigned_manifest=_manifest_unsigned_fields(manifest),
    )
    if not hmac.compare_digest(manifest.hmac_sha256, expected_hmac):
        raise ValueError("checkpoint integrity authentication failed")
    observed_checkpoint_sha256 = hashlib.sha256(payload_bytes).hexdigest()
    if manifest.checkpoint_file != path.name:
        raise ValueError("checkpoint integrity manifest filename mismatch")
    if manifest.checkpoint_sha256 != observed_checkpoint_sha256:
        raise ValueError("checkpoint integrity hash mismatch")
    checkpoint = PipelineCheckpoint.model_validate_json(payload_bytes)
    if manifest.run_id != checkpoint.run_id or manifest.completed_step != checkpoint.completed_step:
        raise ValueError("checkpoint integrity identity mismatch")
    observed_patent_hits_sha256 = _canonical_sha256(checkpoint.patent_hits)
    if manifest.patent_hits_sha256 != observed_patent_hits_sha256:
        raise ValueError("checkpoint patent-hit integrity hash mismatch")
    observed_claim_text_cassettes: set[str] = set()
    observed_legal_status_cassettes: set[str] = set()
    for item in checkpoint.patent_hits or []:
        if not isinstance(item, dict):
            continue
        claims_text = item.get("claims_text_provenance")
        if isinstance(claims_text, dict):
            observed_claim_text_cassettes.add(str(claims_text.get("cassette_sha256") or ""))
        primary = item.get("legal_status_provenance")
        if isinstance(primary, dict):
            observed_legal_status_cassettes.add(str(primary.get("cassette_sha256") or ""))
        for observation in item.get("legal_status_observations") or []:
            if isinstance(observation, dict):
                observed_legal_status_cassettes.add(str(observation.get("cassette_sha256") or ""))
    trusted_claim_text_cassettes = frozenset(manifest.trusted_claim_text_cassette_sha256)
    if any(fullmatch(r"[0-9a-f]{64}", item) is None for item in trusted_claim_text_cassettes):
        raise ValueError("checkpoint trusted claim-text cassette hash is invalid")
    if not trusted_claim_text_cassettes <= observed_claim_text_cassettes:
        raise ValueError("checkpoint trusted claim-text cassette is absent from patent hits")
    trusted_legal_status_cassettes = frozenset(manifest.trusted_legal_status_cassette_sha256)
    if any(fullmatch(r"[0-9a-f]{64}", item) is None for item in trusted_legal_status_cassettes):
        raise ValueError("checkpoint trusted legal-status cassette hash is invalid")
    if not trusted_legal_status_cassettes <= observed_legal_status_cassettes:
        raise ValueError("checkpoint trusted legal-status cassette is absent from patent hits")
    from praviar_pipeline.models.patent import _issue_checkpoint_restore_capability

    checkpoint._trusted_claim_text_cassette_sha256 = trusted_claim_text_cassettes
    checkpoint._trusted_legal_status_cassette_sha256 = trusted_legal_status_cassettes
    checkpoint._restore_capability = _issue_checkpoint_restore_capability(
        checkpoint,
        checkpoint_sha256=observed_checkpoint_sha256,
        patent_hits_sha256=observed_patent_hits_sha256,
        trusted_claim_text_cassette_sha256=trusted_claim_text_cassettes,
        trusted_legal_status_cassette_sha256=trusted_legal_status_cassettes,
    )
    logger.info(
        "checkpoint_loaded",
        step=checkpoint.completed_step,
    )
    return checkpoint


def build_checkpoint(
    run_id: str,
    completed_step: int,
    compound_input: str,
    execution_profile: str = "world_class_adaptive",
    started_at_epoch: float = 0.0,
    deadline_epoch: float | None = None,
    *,
    analysis_escalation_reasons: list[str] | None = None,
    compound: Any = None,
    expanded_queries: Any = None,
    patent_hits: Any = None,
    source_health: Any = None,
    search_funnel: Any = None,
    matter_graph: Any = None,
    matter_graph_summary: Any = None,
    matter_store: Any = None,
    evidence_artifacts: Any = None,
    evidence_adapter_results: Any = None,
    collector_runs: Any = None,
    drawing_results: Any = None,
    triage_results: Any = None,
    all_triage_results: Any = None,
    triage_input_tokens: int = 0,
    triage_output_tokens: int = 0,
    triage_failed: int = 0,
    analyses: Any = None,
    analysis_failures: Any = None,
    prosecution_cache: Any = None,
    reasoning_traces: Any = None,
    critic_report: Any = None,
    critic_input_tokens: int = 0,
    critic_output_tokens: int = 0,
    search_loop_result: Any = None,
    doe_assessments: Any = None,
    doe_input_tokens: int = 0,
    doe_output_tokens: int = 0,
    invalidity_assessments: Any = None,
    inv_input_tokens: int = 0,
    inv_output_tokens: int = 0,
    verification: Any = None,
    regulatory_exclusivity: Any = None,
    timing_data: Any = None,
) -> PipelineCheckpoint:
    """Build a checkpoint from typed pipeline objects.

    Handles serialization of Pydantic models to dicts automatically.
    """
    checkpoint = PipelineCheckpoint(
        run_id=run_id,
        completed_step=completed_step,
        compound_input=compound_input,
        execution_profile=execution_profile,
        analysis_escalation_reasons=analysis_escalation_reasons or [],
        started_at_epoch=started_at_epoch,
        deadline_epoch=deadline_epoch,
        compound=serialize_checkpoint_value(compound),
        expanded_queries=serialize_checkpoint_value(expanded_queries),
        patent_hits=serialize_checkpoint_value(patent_hits),
        source_health=serialize_checkpoint_value(source_health),
        search_funnel=serialize_checkpoint_value(search_funnel),
        matter_graph=serialize_checkpoint_value(matter_graph),
        matter_graph_summary=serialize_checkpoint_value(matter_graph_summary),
        matter_store=serialize_checkpoint_value(matter_store),
        evidence_artifacts=serialize_checkpoint_value(evidence_artifacts),
        evidence_adapter_results=serialize_checkpoint_value(evidence_adapter_results),
        collector_runs=serialize_checkpoint_value(collector_runs),
        drawing_results=serialize_drawing_results(drawing_results),
        triage_results=serialize_checkpoint_value(triage_results),
        all_triage_results=serialize_checkpoint_value(all_triage_results),
        triage_input_tokens=triage_input_tokens,
        triage_output_tokens=triage_output_tokens,
        triage_failed=triage_failed,
        analyses=serialize_checkpoint_value(analyses),
        analysis_failures=serialize_checkpoint_value(analysis_failures),
        prosecution_cache=serialize_checkpoint_value(prosecution_cache),
        reasoning_traces=serialize_checkpoint_value(reasoning_traces),
        critic_report=serialize_checkpoint_value(critic_report),
        critic_input_tokens=critic_input_tokens,
        critic_output_tokens=critic_output_tokens,
        search_loop_result=serialize_checkpoint_value(search_loop_result),
        doe_assessments=serialize_checkpoint_value(doe_assessments),
        doe_input_tokens=doe_input_tokens,
        doe_output_tokens=doe_output_tokens,
        invalidity_assessments=serialize_checkpoint_value(invalidity_assessments),
        inv_input_tokens=inv_input_tokens,
        inv_output_tokens=inv_output_tokens,
        verification=serialize_checkpoint_value(verification),
        regulatory_exclusivity=serialize_checkpoint_value(regulatory_exclusivity),
        timing_data=serialize_checkpoint_value(timing_data),
    )
    from praviar_pipeline.models.patent import (
        trusted_claim_text_provenance,
        trusted_legal_status_observations,
    )

    checkpoint._trusted_claim_text_cassette_sha256 = frozenset(
        str(provenance.cassette_sha256)
        for hit in (patent_hits or [])
        if (provenance := trusted_claim_text_provenance(hit)) is not None
    )
    checkpoint._trusted_legal_status_cassette_sha256 = frozenset(
        str(observation.cassette_sha256)
        for hit in (patent_hits or [])
        for observation in trusted_legal_status_observations(hit)
    )
    return checkpoint


def restore_from_checkpoint(ckpt: PipelineCheckpoint) -> dict[str, Any]:
    """Deserialize checkpoint data back to typed Pydantic objects.

    Returns a dict of variable names → restored objects. Import models lazily
    to avoid circular imports.
    """
    return restore_checkpoint_state(
        ckpt,
        logger,
        checkpoint_restore_capability=ckpt._restore_capability,
    )
