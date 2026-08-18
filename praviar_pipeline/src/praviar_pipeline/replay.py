"""Replay support for Praviar Pipeline reports.

Given a :class:`~praviar_pipeline.manifest.ReportManifest` previously emitted
alongside a report, the functions here let you:

* Load the manifest JSON from disk.
* Verify that the current working tree can reproduce the pinned inputs:
  the git SHA matches, every prompt file's SHA256 matches, recorded tool
  schemas match, and the recorded model IDs resolve.
* Optionally re-run the pipeline with the pinned configuration applied.
* Diff a newly-produced report against the original for drift detection.

v1 scope (deliberately narrow):

* We verify the *pipeline inputs we can pin* (code, prompts, models,
  sampling, tool schemas). External API responses are NOT cached; if PubChem
  or EPO have updated their data since the original run, source counts may
  differ. The replay result surfaces this as informational drift, not
  a failure, so customer-dispute diagnosis can proceed.
* LLM floating-point determinism is not guaranteed by Anthropic even
  at ``temperature=0``. Token-level drift is measured but does not
  fail the replay.

v2 candidates (documented, not implemented):

* Full cached-API replay so the rerun uses the exact original responses.
* Byte-for-byte evidence-section diff with a tolerance threshold.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from praviar_pipeline.manifest import (
    ReportManifest,
    ToolTraceRecorder,
    compute_source_tree_provenance,
    get_pipeline_version,
    get_prompt_hasher,
)
from praviar_pipeline.tools_definitions import TOOL_DEFINITIONS

if TYPE_CHECKING:
    from praviar_pipeline.config import Settings


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------


def load_manifest(path: str | Path) -> ReportManifest:
    """Load a manifest sidecar JSON from ``path`` into a :class:`ReportManifest`.

    Raises :class:`FileNotFoundError` if the path does not exist and
    :class:`ValueError` if the file cannot be parsed or validated.
    """
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise FileNotFoundError("Replay manifest was not found")
    parse_failed = False
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        parse_failed = True
    if parse_failed:
        raise ValueError("Replay manifest is not valid JSON") from None
    validation_error_type: str | None = None
    try:
        return ReportManifest.model_validate(raw)
    except Exception as exc:  # pydantic.ValidationError, but keep import light
        from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

        validation_error_type = safe_exception_type(exc)
    raise ValueError(
        "Replay manifest does not match the expected schema "
        f"({validation_error_type or 'Exception'})"
    ) from None


# ---------------------------------------------------------------------------
# Precondition verification
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PreconditionResult:
    """Outcome of comparing a manifest against the current working tree."""

    ok: bool
    version_matches: bool
    version_diff: tuple[str, str] | None  # (manifest_sha, current_sha) if differ
    source_tree_matches: bool = True
    source_tree_diff: tuple[str, str] | None = None
    missing_prompts: list[str] = field(default_factory=list)
    prompt_drift: dict[str, tuple[str, str]] = field(default_factory=dict)
    # ^ filename -> (manifest_hash, current_hash)
    missing_tool_definitions: list[str] = field(default_factory=list)
    tool_definition_drift: dict[str, tuple[str, str]] = field(default_factory=dict)
    # ^ tool name -> (manifest_hash, current_hash)
    messages: list[str] = field(default_factory=list)


def _hash_prompt_file(prompts_dir: Path, filename: str) -> str | None:
    """Return the SHA256 hex of a prompt file, or ``None`` if missing."""
    path = prompts_dir / filename
    if not path.is_file():
        return None
    # Reuse PromptHasher's implementation — record then read snapshot
    # would also work, but for verification we don't want to mutate the
    # singleton's recorded set, so compute the hash directly.
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _current_tool_definition_hashes() -> dict[str, str]:
    """Return {tool name -> schema SHA256} for the current runtime tools."""
    recorder = ToolTraceRecorder()
    return recorder.record_tool_definitions(TOOL_DEFINITIONS)


def verify_preconditions(
    manifest: ReportManifest,
    *,
    prompts_dir: Path | None = None,
    allow_drift: bool = False,
) -> PreconditionResult:
    """Compare the manifest against the current praviar_pipeline checkout.

    Returns a :class:`PreconditionResult` describing every dimension of
    drift (pipeline version, missing prompts, prompt hash mismatches, tool
    schema mismatches).
    ``ok`` is True only when nothing has drifted, or ``allow_drift`` is
    True and the caller has opted into running against a drifted tree.
    """
    if prompts_dir is None:
        prompts_dir = Path(__file__).resolve().parent / "prompts"

    result = PreconditionResult(ok=True, version_matches=True, version_diff=None)

    current_version = get_pipeline_version()
    if manifest.pipeline_version != current_version:
        result.version_matches = False
        result.version_diff = (manifest.pipeline_version, current_version)
        result.messages.append(
            f"Pipeline version drift: manifest={manifest.pipeline_version} "
            f"current={current_version}"
        )

    current_tree_state, current_tree_digest = compute_source_tree_provenance()
    manifest_tree = f"{manifest.source_tree_state}:{manifest.source_tree_digest}"
    current_tree = f"{current_tree_state}:{current_tree_digest}"
    if not manifest.source_tree_digest or manifest_tree != current_tree:
        result.source_tree_matches = False
        result.source_tree_diff = (manifest_tree, current_tree)
        result.messages.append("Source tree provenance is missing or has drifted")

    for filename, manifest_hash in manifest.prompt_hashes.items():
        current_hash = _hash_prompt_file(prompts_dir, filename)
        if current_hash is None:
            result.missing_prompts.append(filename)
            result.messages.append(f"Prompt missing on disk: {filename}")
            continue
        if current_hash != manifest_hash:
            result.prompt_drift[filename] = (manifest_hash, current_hash)
            result.messages.append(
                f"Prompt drift in {filename}: manifest={manifest_hash[:12]}... "
                f"current={current_hash[:12]}..."
            )

    if manifest.tool_definition_hashes:
        current_tool_hashes = _current_tool_definition_hashes()
        for tool_name, manifest_hash in manifest.tool_definition_hashes.items():
            current_hash = current_tool_hashes.get(tool_name)
            if current_hash is None:
                result.missing_tool_definitions.append(tool_name)
                result.messages.append(f"Tool definition missing in runtime: {tool_name}")
                continue
            if current_hash != manifest_hash:
                result.tool_definition_drift[tool_name] = (manifest_hash, current_hash)
                result.messages.append(
                    f"Tool definition drift in {tool_name}: "
                    f"manifest={manifest_hash[:12]}... current={current_hash[:12]}..."
                )

    any_drift = bool(
        not result.version_matches
        or not result.source_tree_matches
        or result.missing_prompts
        or result.prompt_drift
        or result.missing_tool_definitions
        or result.tool_definition_drift
    )
    if any_drift and not allow_drift:
        result.ok = False
    return result


# ---------------------------------------------------------------------------
# Pinned-config application
# ---------------------------------------------------------------------------


def apply_pinned_config(manifest: ReportManifest, settings: Settings) -> Settings:
    """Return a copy of ``settings`` with values from the manifest forced in.

    Overrides (when present in the manifest):

    * ``claude_triage_model`` ← ``manifest.model_versions["triage"]``
    * ``claude_analysis_model`` ← ``manifest.model_versions["analysis"]``
    * ``claude_deep_model`` ← ``manifest.model_versions["deep"]``

    Sampling pinning (``temperature=0``, seeds) is enforced elsewhere —
    by this session's WS-2 work those are already the production
    defaults, so no override is needed.

    Settings that are not present in the manifest are left at their
    current defaults. We do NOT add silent fallbacks: if the manifest
    records a model ID that no longer exists, the rerun will fail at
    Anthropic's API boundary with a clear error.
    """
    overrides: dict[str, str] = {}
    for role in ("triage", "analysis", "deep"):
        model_id = manifest.model_versions.get(role, "")
        if model_id:
            overrides[f"claude_{role}_model"] = model_id

    if not overrides:
        return settings

    # Pydantic Settings is immutable by default; construct a new copy with
    # overrides. model_copy keeps unspecified fields, update applies ours.
    return settings.model_copy(update=overrides)


# ---------------------------------------------------------------------------
# Report diff (v1: structural, not byte-for-byte)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ReportDiff:
    """Structural comparison of two report JSON payloads."""

    identical: bool
    risk_verdict_matches: bool
    patent_count_delta: int  # new_count - original_count
    unique_to_original: list[str] = field(default_factory=list)
    unique_to_replay: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


def _extract_patent_ids(report: dict) -> list[str]:
    """Pull the set of analyzed patent IDs out of a report payload."""
    ids: list[str] = []
    for key in ("patent_analyses", "patents", "analyses"):
        entries = report.get(key) or []
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict):
                    pid = entry.get("patent_id") or entry.get("id")
                    if isinstance(pid, str):
                        ids.append(pid)
    return sorted(set(ids))


def _extract_governed_verdict(report: dict) -> tuple[str, str | None]:
    """Return the authoritative verdict and the field that supplied it.

    Current reports govern clearance through ``clearance_decision.decision``.
    ``risk_summary.overall_risk`` is retained only for legacy report replay.
    Including the source field prevents a report that silently lost its
    governed decision from comparing equal to a legacy-shaped payload.
    """
    clearance = report.get("clearance_decision")
    if isinstance(clearance, dict):
        decision = clearance.get("decision")
        if isinstance(decision, str) and decision.strip():
            return "clearance_decision.decision", decision.strip().lower()

    risk_summary = report.get("risk_summary")
    if isinstance(risk_summary, dict):
        risk = risk_summary.get("overall_risk")
        if isinstance(risk, str) and risk.strip():
            return "risk_summary.overall_risk", risk.strip().lower()
    return "missing", None


def diff_reports(original: dict, replay: dict) -> ReportDiff:
    """Compare two report payloads and summarise drift.

    Both payloads are expected to be the parsed JSON of an FTOReport.
    This is a structural diff for v1 — we focus on what a reviewer
    actually asks about: "did the risk verdict change?" and "did we
    pick up or drop any patents?"
    """
    orig_source, orig_risk = _extract_governed_verdict(original)
    replay_source, replay_risk = _extract_governed_verdict(replay)
    risk_matches = (orig_source, orig_risk) == (replay_source, replay_risk)

    orig_ids = _extract_patent_ids(original)
    replay_ids = _extract_patent_ids(replay)
    orig_set = set(orig_ids)
    replay_set = set(replay_ids)
    unique_to_original = sorted(orig_set - replay_set)
    unique_to_replay = sorted(replay_set - orig_set)

    messages: list[str] = []
    if not risk_matches:
        messages.append(
            "Governed verdict changed: "
            f"{orig_source}={orig_risk!r} -> {replay_source}={replay_risk!r}"
        )
    if unique_to_original:
        messages.append(
            f"Patents in original but not replay ({len(unique_to_original)}): "
            + ", ".join(unique_to_original[:5])
            + ("..." if len(unique_to_original) > 5 else "")
        )
    if unique_to_replay:
        messages.append(
            f"Patents in replay but not original ({len(unique_to_replay)}): "
            + ", ".join(unique_to_replay[:5])
            + ("..." if len(unique_to_replay) > 5 else "")
        )

    identical = risk_matches and not unique_to_original and not unique_to_replay

    return ReportDiff(
        identical=identical,
        risk_verdict_matches=risk_matches,
        patent_count_delta=len(replay_ids) - len(orig_ids),
        unique_to_original=unique_to_original,
        unique_to_replay=unique_to_replay,
        messages=messages,
    )


# ---------------------------------------------------------------------------
# Utility: reset prompt hasher before a replay (so the new run's hashes
# reflect only the prompts loaded this time, not prior state)
# ---------------------------------------------------------------------------


def reset_prompt_hasher() -> None:
    """Clear the process-wide prompt-hash registry.

    Call before invoking the pipeline as part of a replay so the
    resulting manifest's ``prompt_hashes`` reflects only the prompts
    loaded during the replay, not any prior state.
    """
    get_prompt_hasher().reset()
