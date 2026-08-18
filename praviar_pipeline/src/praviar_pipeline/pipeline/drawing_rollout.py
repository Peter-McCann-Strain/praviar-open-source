"""Rollout-state helpers for drawing-derived evidence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, cast

from praviar_pipeline.models.drawing import DrawingGovernanceProvenance
from praviar_pipeline.pipeline.drawings.preprocessing import jurisdiction_from_patent_id

LIVE_DRAWING_ROLLOUT_STATES = {"beta", "production"}
SHADOW_DRAWING_ROLLOUT_STATES = {"internal", "shadow"}
DrawingRolloutState = Literal["internal", "shadow", "beta", "production"]


def drawing_evidence_gate_passed(settings: Any) -> bool:
    """Whether reviewed evidence permits drawing output to affect decisions."""
    return bool(getattr(settings, "drawing_analysis_evidence_gate_passed", False))


def drawing_rollout_state(settings: Any) -> DrawingRolloutState:
    """Return the normalized drawing rollout state, failing closed to shadow."""
    state = str(getattr(settings, "drawing_analysis_rollout_state", "shadow") or "shadow")
    normalized = state.strip().lower()
    if normalized in LIVE_DRAWING_ROLLOUT_STATES | SHADOW_DRAWING_ROLLOUT_STATES:
        return cast("DrawingRolloutState", normalized)
    return "shadow"


def drawing_specialist_rollout_state(
    settings: Any,
    attr_name: str,
    *,
    default: str = "shadow",
) -> DrawingRolloutState:
    """Return a normalized specialist rollout state, failing closed to shadow."""
    state = str(getattr(settings, attr_name, default) or default)
    normalized = state.strip().lower()
    if normalized in LIVE_DRAWING_ROLLOUT_STATES | SHADOW_DRAWING_ROLLOUT_STATES:
        return cast("DrawingRolloutState", normalized)
    return "shadow"


def drawing_evidence_can_influence(settings: Any) -> bool:
    """Whether drawing evidence may influence triage, claims, or risk output."""
    live = drawing_rollout_state(settings) in LIVE_DRAWING_ROLLOUT_STATES
    if live:
        from praviar_pipeline.ocsr.calibration_contract import calibration_is_verified

        calibration_verified = calibration_is_verified(settings)
    else:
        calibration_verified = False
    return (
        live
        and drawing_evidence_gate_passed(settings)
        and bool(drawing_jurisdiction_allowlist(settings))
        and calibration_verified
    )


def drawing_failures_are_fatal(settings: Any) -> bool:
    """Whether drawing runtime/prerequisite failures must stop the run.

    A live rollout is fail-closed even when its evidence gate, calibration, or
    jurisdiction bindings are missing. Using ``drawing_evidence_can_influence``
    here would invert that safety boundary: the exact prerequisite failure that
    prevents influence could then be swallowed as a shadow-mode abstention.
    """

    return drawing_rollout_state(settings) in LIVE_DRAWING_ROLLOUT_STATES


def drawing_evidence_for_decisions(settings: Any, drawing_evidence: Any) -> Any | None:
    """Return drawing evidence only when rollout permits decision influence."""
    if drawing_evidence_can_influence(settings):
        return drawing_evidence
    return None


def build_drawing_governance_provenance(
    settings: Any,
    *,
    now: datetime | None = None,
) -> DrawingGovernanceProvenance:
    """Bind report-visible drawing output to verified runtime governance."""
    state = drawing_rollout_state(settings)
    jurisdictions = tuple(drawing_jurisdiction_allowlist(settings))
    if state in SHADOW_DRAWING_ROLLOUT_STATES:
        return DrawingGovernanceProvenance(
            rollout_state=state,
            influence_permitted=False,
            evidence_gate_passed=False,
            jurisdictions=jurisdictions,
        )

    if not drawing_evidence_gate_passed(settings) or not jurisdictions:
        raise RuntimeError("live drawing evidence governance is incomplete")

    from praviar_pipeline.ocsr.calibration_contract import require_verified_calibration

    verified = require_verified_calibration(settings, now=now)
    worker_image_digest = str(
        getattr(settings, "certification_worker_oci_image_digest", "") or ""
    ).strip()
    return DrawingGovernanceProvenance(
        rollout_state=state,
        influence_permitted=True,
        evidence_gate_passed=True,
        runtime_roster_sha256=verified.runtime_roster_sha256,
        ml_bom_sha256=verified.ml_bom_sha256,
        calibration_artifact_id=verified.artifact_id,
        calibration_artifact_revision=verified.artifact_revision,
        calibration_artifact_sha256=verified.artifact_sha256,
        worker_image_digest=worker_image_digest,
        jurisdictions=jurisdictions,
        verified_at=(now or datetime.now(UTC)).astimezone(UTC),
    )


def markush_scope_agent_can_run(settings: Any) -> bool:
    """Allow the experimental scope agent only in internal/shadow collection.

    The agent's bounded R-group enumeration is a research aid, not validated
    production claim construction. Production drawing evidence therefore
    cannot include its scope verdicts.
    """

    return bool(getattr(settings, "drawing_markush_scope_agent_enabled", False)) and (
        drawing_rollout_state(settings) in SHADOW_DRAWING_ROLLOUT_STATES
    )


def drawing_specialist_tool_can_emit(
    settings: Any,
    attr_name: str,
    *,
    default: str = "shadow",
) -> bool:
    """Whether a specialist drawing tool may emit into the aggregate evidence.

    Shadow/internal specialist tools may collect shadow evidence while the
    global drawing rollout is also shadow/internal. Once drawing evidence can
    influence customer decisions, each specialist path must be live too.
    """
    if not drawing_evidence_can_influence(settings):
        return True
    return (
        drawing_specialist_rollout_state(settings, attr_name, default=default)
        in LIVE_DRAWING_ROLLOUT_STATES
    )


def drawing_jurisdiction_allowlist(settings: Any) -> list[str]:
    """Return the normalized drawing-analysis jurisdiction allowlist."""
    values = getattr(settings, "drawing_analysis_jurisdictions", []) or []
    if not isinstance(values, (list, tuple, set, frozenset)):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        jurisdiction = str(value or "").strip().upper()
        if not jurisdiction or jurisdiction in seen:
            continue
        normalized.append(jurisdiction)
        seen.add(jurisdiction)
    return normalized


def filter_patents_by_drawing_jurisdiction(patents: list[Any], settings: Any) -> list[Any]:
    """Apply the staged drawing-analysis jurisdiction allowlist."""
    allowlist = set(drawing_jurisdiction_allowlist(settings))
    if not allowlist:
        return []
    return [
        patent
        for patent in patents
        if jurisdiction_from_patent_id(getattr(patent, "patent_id", str(patent))) in allowlist
    ]
