"""Persistence helpers for pipeline worker tasks."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Literal, cast

import structlog
from sqlalchemy.orm import Session

from api.services.report_access import validate_report_publishability

logger = structlog.get_logger()

PROMPT_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
INCHI_KEY_RE = re.compile(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")

CompoundType = Literal["small_molecule", "biologic", "peptide"]
SUPPORTED_COMPOUND_TYPES = frozenset({"small_molecule", "biologic", "peptide"})


class CompoundIdentityMode(Enum):
    """How a completed analysis may participate in the global compound library."""

    INCHI_KEY = "inchi_key"
    EXISTING_SMILES = "existing_smiles"
    NOT_INDEXABLE = "not_indexable"


@dataclass(frozen=True)
class CompoundIdentityDecision:
    compound_type: CompoundType
    mode: CompoundIdentityMode
    inchi_key: str
    canonical_smiles: str


def _compound_identity_decision(compound: Mapping[str, object]) -> CompoundIdentityDecision:
    """Apply the type-aware global identity policy for a completed compound."""
    raw_compound_type = str(compound.get("compound_type", "small_molecule")).strip()
    if raw_compound_type not in SUPPORTED_COMPOUND_TYPES:
        raise ValueError(f"unsupported completed compound_type: {raw_compound_type!r}")
    compound_type = cast(CompoundType, raw_compound_type)

    inchi_key = str(compound.get("inchi_key", "") or "").strip()
    canonical_smiles = str(compound.get("canonical_smiles", "") or "").strip()
    if inchi_key:
        if not INCHI_KEY_RE.fullmatch(inchi_key):
            raise ValueError("completed compound has an invalid inchi_key")
        return CompoundIdentityDecision(
            compound_type=compound_type,
            mode=CompoundIdentityMode.INCHI_KEY,
            inchi_key=inchi_key,
            canonical_smiles=canonical_smiles,
        )

    if compound_type in {"biologic", "peptide"}:
        return CompoundIdentityDecision(
            compound_type=compound_type,
            mode=CompoundIdentityMode.NOT_INDEXABLE,
            inchi_key="",
            canonical_smiles=canonical_smiles,
        )

    if not canonical_smiles:
        raise ValueError("small-molecule compound is missing global identity fields")
    return CompoundIdentityDecision(
        compound_type=compound_type,
        mode=CompoundIdentityMode.EXISTING_SMILES,
        inchi_key="",
        canonical_smiles=canonical_smiles,
    )


def _extract_sha256_mapping(
    value: object,
    *,
    field_name: str,
    require_non_empty: bool = True,
) -> dict[str, str]:
    if not isinstance(value, Mapping) or (require_non_empty and not value):
        raise ValueError(f"{field_name} must be a non-empty mapping")

    validated: dict[str, str] = {}
    for name, digest in value.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{field_name} keys must be non-empty strings")
        if not isinstance(digest, str) or not PROMPT_HASH_RE.fullmatch(digest):
            raise ValueError(
                f"{field_name} hash for {name!r} must be a lowercase SHA-256 hex digest"
            )
        validated[name] = digest

    return validated


def _extract_prompt_hashes(report_data: object) -> dict[str, str]:
    if not isinstance(report_data, Mapping):
        raise ValueError("report_data must be a mapping with audit_trail.prompt_hashes")

    audit_trail = report_data.get("audit_trail")
    if not isinstance(audit_trail, Mapping):
        raise ValueError("audit_trail.prompt_hashes is required for completed analyses")

    prompt_hashes = audit_trail.get("prompt_hashes")
    return _extract_sha256_mapping(prompt_hashes, field_name="audit_trail.prompt_hashes")


def _extract_manifest_provenance(
    report_data: Mapping[str, object],
    prompt_hashes: Mapping[str, str],
) -> dict[str, Any]:
    manifest = report_data.get("manifest")
    if not isinstance(manifest, Mapping):
        raise ValueError("report_data.manifest is required for completed analyses")

    manifest_prompt_hashes = _extract_sha256_mapping(
        manifest.get("prompt_hashes"),
        field_name="manifest.prompt_hashes",
    )
    if manifest_prompt_hashes != dict(prompt_hashes):
        raise ValueError("manifest.prompt_hashes must match audit_trail.prompt_hashes")

    pipeline_version = str(manifest.get("pipeline_version", "")).strip()
    if not GIT_SHA_RE.fullmatch(pipeline_version):
        raise ValueError("manifest.pipeline_version must be a lowercase 40-character git SHA")

    model_versions = manifest.get("model_versions")
    if not isinstance(model_versions, Mapping) or not model_versions:
        raise ValueError("manifest.model_versions must be a non-empty mapping")
    validated_models: dict[str, str] = {}
    for role, model_id in model_versions.items():
        if not isinstance(role, str) or not role.strip():
            raise ValueError("manifest.model_versions keys must be non-empty strings")
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError(f"manifest.model_versions[{role!r}] must be non-empty")
        validated_models[role] = model_id

    tool_trace_digest = manifest.get("tool_trace_digest")
    if not isinstance(tool_trace_digest, str) or not PROMPT_HASH_RE.fullmatch(tool_trace_digest):
        raise ValueError("manifest.tool_trace_digest must be a lowercase SHA-256 hex digest")

    tool_call_count = manifest.get("tool_call_count")
    if type(tool_call_count) is not int or tool_call_count < 0:
        raise ValueError("manifest.tool_call_count must be a non-negative integer")

    tool_definition_hashes = _extract_sha256_mapping(
        manifest.get("tool_definition_hashes", {}),
        field_name="manifest.tool_definition_hashes",
        require_non_empty=tool_call_count > 0,
    )

    source_snapshots = manifest.get("source_snapshots")
    if not isinstance(source_snapshots, Mapping):
        raise ValueError("manifest.source_snapshots must be a mapping")
    validated_snapshots: dict[str, str] = {}
    for source_name, snapshot_id in source_snapshots.items():
        if not isinstance(source_name, str) or not source_name.strip():
            raise ValueError("manifest.source_snapshots keys must be non-empty strings")
        if not isinstance(snapshot_id, str) or not snapshot_id.strip():
            raise ValueError(f"manifest.source_snapshots[{source_name!r}] must be non-empty")
        validated_snapshots[source_name] = snapshot_id

    return {
        "pipeline_version": pipeline_version,
        "model_versions": validated_models,
        "tool_definition_hashes": tool_definition_hashes,
        "tool_trace_digest": tool_trace_digest,
        "tool_call_count": tool_call_count,
        "source_snapshots": validated_snapshots,
    }


def _extract_report_publishability_summary(report_data: Mapping[str, object]) -> dict[str, Any]:
    return validate_report_publishability(report_data)


def _extract_completed_report_provenance(report_data: object) -> dict[str, Any]:
    prompt_hashes = _extract_prompt_hashes(report_data)
    if not isinstance(report_data, Mapping):
        raise ValueError("report_data must be a mapping with completed-report provenance")

    manifest = _extract_manifest_provenance(report_data, prompt_hashes)
    publishability = _extract_report_publishability_summary(report_data)
    return {
        "prompt_hashes": prompt_hashes,
        **manifest,
        **publishability,
    }


def write_analysis_completed_audit_impl(db: Session, analysis) -> None:
    """Write an ``analysis.completed`` audit-log entry with prompt provenance.

    Extracts the provenance bundle from the persisted ``report_data`` JSONB
    field and records the audit-critical fields in the ``details`` column so
    every completed analysis retains prompt, model, tool and claim-span proof.

    Audit/provenance failure is fatal for completion: if this write fails, the
    pipeline must not be marked completed without its report provenance trail.
    """
    try:
        from api.db.models_operations import AuditLog

        report_data = analysis.report_data
        provenance = _extract_completed_report_provenance(report_data)
        prompt_hashes = provenance["prompt_hashes"]
        report_mapping = report_data if isinstance(report_data, Mapping) else {}

        log = AuditLog(
            org_id=analysis.org_id,
            user_id=None,
            analysis_id=analysis.id,
            action="analysis.completed",
            details={
                "prompt_hashes": prompt_hashes,
                "manifest_pipeline_version": provenance["pipeline_version"],
                "model_versions": provenance["model_versions"],
                "tool_definition_hashes": provenance["tool_definition_hashes"],
                "tool_trace_digest": provenance["tool_trace_digest"],
                "tool_call_count": provenance["tool_call_count"],
                "source_snapshot_count": len(provenance["source_snapshots"]),
                "claim_source_span_entry_count": provenance["claim_source_span_entry_count"],
                "claim_source_span_count": provenance["claim_source_span_count"],
                "needs_review_count": provenance["needs_review_count"],
                "unsupported_customer_visible_claim_count": provenance[
                    "unsupported_customer_visible_claim_count"
                ],
                "material_patent_support_count": provenance["material_patent_support_count"],
                "decisive_reference_count": provenance["decisive_reference_count"],
                "verification_check_count": provenance["verification_check_count"],
                "factual_accuracy_rate": provenance["factual_accuracy_rate"],
                "overall_assessment": provenance["overall_assessment"],
                "execution_profile": report_mapping.get("execution_profile", ""),
                "overall_risk": analysis.overall_risk or "",
                "estimated_cost_usd": analysis.estimated_cost_usd or 0.0,
            },
            ip_address="worker",
        )
        db.add(log)
        logger.info(
            "analysis_completed_audit_written",
            analysis_id=str(analysis.id),
            prompt_file_count=len(prompt_hashes),
        )
    except Exception as exc:
        logger.error(
            "analysis_completed_audit_failed",
            analysis_id=str(analysis.id) if analysis else "unknown",
            error=str(exc),
            error_type=type(exc).__name__,
            exc_info=True,
        )
        raise


def store_pipeline_results_impl(analysis, report_dict: dict, duration: float) -> None:
    """Extract summary fields from the pipeline report onto the Analysis row."""
    previous_report_data = getattr(analysis, "report_data", None)
    report_replaced = (
        isinstance(previous_report_data, dict)
        and bool(previous_report_data)
        and previous_report_data != report_dict
    )
    analysis.report_data = report_dict
    analysis.progress_pct = 100.0
    analysis.current_step = 8
    analysis.pipeline_duration_seconds = duration
    if report_replaced:
        analysis.flagged_for_review = True
        analysis.share_active_grant_count = 0
        analysis.share_active_until = None

    risk_summary = report_dict.get("risk_summary", {})
    analysis.overall_risk = risk_summary.get("overall_risk", "")
    analysis.blocking_patents_count = risk_summary.get("blocking_patents_count", 0)
    analysis.total_patents_found = report_dict.get("total_patents_found", 0)
    analysis.executive_summary = risk_summary.get("executive_summary", "")
    analysis.total_input_tokens = report_dict.get("total_input_tokens", 0)
    analysis.total_output_tokens = report_dict.get("total_output_tokens", 0)
    analysis.estimated_cost_usd = report_dict.get("estimated_cost_usd", 0.0)

    compound = report_dict.get("compound", {})
    analysis.compound_name = compound.get("name", "")
    analysis.compound_smiles = compound.get("canonical_smiles", "")
    analysis.compound_cid = compound.get("pubchem_cid")


def upsert_compound_impl(
    db: Session,
    compound: dict,
    *,
    org_id,
    completed_at: datetime,
) -> None:
    """Persist global identity and organization-local usage in one transaction."""
    if completed_at is None:
        raise ValueError("completed compound usage requires completed_at")
    identity = _compound_identity_decision(compound)
    if identity.mode is CompoundIdentityMode.NOT_INDEXABLE:
        logger.info(
            "compound_global_identity_skipped",
            compound_type=identity.compound_type,
            reason="no_inchi_key",
        )
        return

    from sqlalchemy import func as sa_func
    from sqlalchemy import select, update
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from api.db.models import Compound, OrganizationCompound

    display_name = str(compound.get("name", "") or "").strip()[:500]
    if identity.mode is CompoundIdentityMode.INCHI_KEY:
        insert_stmt = pg_insert(Compound).values(
            canonical_smiles=identity.canonical_smiles,
            inchi_key=identity.inchi_key,
            # Tenant-local labels belong only on OrganizationCompound. A
            # project codename must never enter the globally shared identity.
            name="",
            molecular_formula=compound.get("molecular_formula", ""),
            molecular_weight=compound.get("molecular_weight"),
            functional_groups=compound.get("functional_groups", []),
            pubchem_cid=compound.get("pubchem_cid"),
            analysis_count=1,
        )
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=["inchi_key"],
            set_={
                "analysis_count": Compound.analysis_count + 1,
                "name": "",
                "pubchem_cid": sa_func.coalesce(
                    Compound.pubchem_cid,
                    insert_stmt.excluded.pubchem_cid,
                ),
            },
        ).returning(Compound.id)
        compound_id = db.execute(upsert_stmt).scalar_one()
    else:
        matched_ids = (
            db.execute(
                select(Compound.id)
                .where(Compound.canonical_smiles == identity.canonical_smiles)
                .limit(2)
            )
            .scalars()
            .all()
        )
        if len(matched_ids) != 1:
            raise ValueError("small-molecule compound identity is ambiguous without inchi_key")
        update_stmt = (
            update(Compound)
            .where(Compound.id == matched_ids[0])
            .values(
                analysis_count=Compound.analysis_count + 1,
                name="",
                pubchem_cid=sa_func.coalesce(
                    Compound.pubchem_cid,
                    compound.get("pubchem_cid"),
                ),
            )
            .returning(Compound.id)
        )
        compound_id = db.execute(update_stmt).scalar_one()

    usage_stmt = pg_insert(OrganizationCompound).values(
        org_id=org_id,
        compound_id=compound_id,
        display_name=display_name,
        first_analyzed_at=completed_at,
        analysis_count=1,
    )
    usage_stmt = usage_stmt.on_conflict_do_update(
        index_elements=["org_id", "compound_id"],
        set_={
            "analysis_count": OrganizationCompound.analysis_count + 1,
            "display_name": sa_func.coalesce(
                sa_func.nullif(usage_stmt.excluded.display_name, ""),
                OrganizationCompound.display_name,
            ),
            "first_analyzed_at": sa_func.least(
                OrganizationCompound.first_analyzed_at,
                usage_stmt.excluded.first_analyzed_at,
            ),
        },
    )
    db.execute(usage_stmt)
