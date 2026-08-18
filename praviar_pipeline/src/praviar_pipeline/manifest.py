"""Report manifest — provenance sidecar for every FTO run.

The manifest pins down exactly how a report was produced so it can be audited
and replayed. It records:

* ``pipeline_version``  — git SHA of praviar_pipeline at runtime (cached at import).
* ``generated_at``      — UTC timestamp of manifest construction.
* ``compound_query``    — exact user input (SMILES / name / CAS).
* ``prompt_hashes``     — SHA256 of every prompt file loaded during the run.
* ``model_versions``    — model IDs for triage / analysis / deep roles.
* ``sampling``          — sampling parameters per role (temperature, top_p).
* ``source_snapshots``  — immutable per-source snapshot identifiers, when a
  collector provides one.
* ``source_observations`` — timestamped live-source coverage observations;
  these are explicitly not represented as replayable snapshots.
* ``tool_definition_hashes`` — SHA256 per allowed tool schema/name.
* ``tool_trace_digest`` — SHA256 of an ordered, value-bound tool-call log;
  sanitized traces retain only type and cryptographic digest, never plaintext.
* ``tool_call_count``   — number of tool calls attempted during the run.

This module is intentionally side-effect light: ``PromptHasher`` and
``ToolTraceRecorder`` are context-local per run and mutated only by
prompt/tool boundaries.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import subprocess
from contextvars import ContextVar
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from praviar_pipeline.config import Settings
    from praviar_pipeline.models.report_common import SourceHealth


# ---------------------------------------------------------------------------
# Pipeline version (cached once at module import)
# ---------------------------------------------------------------------------


def _looks_like_git_sha(value: str) -> bool:
    return len(value) == 40 and all(c in "0123456789abcdef" for c in value.lower())


def _compute_pipeline_version() -> str:
    """Resolve the Praviar pipeline git SHA from env or the checkout."""
    env_sha = (
        os.environ.get("PRAVIAR_PIPELINE_VERSION")
        or os.environ.get("GIT_COMMIT_SHA")
        or os.environ.get("VERCEL_GIT_COMMIT_SHA")
        or ""
    ).strip()
    if env_sha:
        return env_sha

    repo_root = Path(__file__).resolve().parents[3]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return "unknown"
    if result.returncode != 0:
        return "unknown"
    sha = result.stdout.strip()
    if not sha or not _looks_like_git_sha(sha):
        return "unknown"
    return sha


_PIPELINE_VERSION: str = _compute_pipeline_version()

_SOURCE_TREE_PATHS = (
    "api",
    "ops",
    "packages",
    "praviar_pipeline",
    "research",
    "scripts",
    "web",
    "Dockerfile",
    "package.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    "pyproject.toml",
    "uv.lock",
)


def get_pipeline_version() -> str:
    """Return the cached pipeline (praviar_pipeline) git SHA, or ``"unknown"``."""
    return _PIPELINE_VERSION


def require_pipeline_version() -> str:
    """Return the pipeline SHA, failing if provenance cannot be pinned."""
    version = get_pipeline_version()
    if not _looks_like_git_sha(version):
        raise RuntimeError(
            "Praviar pipeline version is unavailable; set PRAVIAR_PIPELINE_VERSION "
            "to the 40-character build commit SHA before generating reports."
        )
    return version


def compute_source_tree_provenance() -> tuple[str, str]:
    """Return ``(state, digest)`` for the exact local source tree.

    A commit SHA alone is insufficient when a report is produced from a dirty
    checkout. The digest binds tracked, staged, and untracked workspace
    changes without serializing filenames or source content into the manifest.
    CI builds pinned by an explicit version environment variable are labeled
    ``build`` because their deployment substrate, not a writable checkout,
    supplies the source contract.
    """
    version = get_pipeline_version()
    if any(
        os.environ.get(name)
        for name in ("PRAVIAR_PIPELINE_VERSION", "GIT_COMMIT_SHA", "VERCEL_GIT_COMMIT_SHA")
    ):
        return "build", _canonical_json_digest({"state": "build", "version": version})

    repo_root = Path(__file__).resolve().parents[3]
    try:
        status = subprocess.run(
            [
                "git",
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "-z",
                "--",
                *_SOURCE_TREE_PATHS,
            ],
            cwd=repo_root,
            capture_output=True,
            timeout=10,
            check=False,
        )
        if status.returncode != 0:
            return "unknown", ""
        if not status.stdout:
            return "clean", _canonical_json_digest({"state": "clean", "version": version})

        tracked_diff = subprocess.run(
            ["git", "diff", "--binary", "HEAD", "--", *_SOURCE_TREE_PATHS],
            cwd=repo_root,
            capture_output=True,
            timeout=20,
            check=False,
        )
        if tracked_diff.returncode != 0:
            return "unknown", ""

        digest = hashlib.sha256()
        digest.update(b"praviar-source-tree-v1\0")
        digest.update(version.encode("utf-8"))
        digest.update(b"\0")
        digest.update(tracked_diff.stdout)
        for record in status.stdout.split(b"\0"):
            if not record.startswith(b"?? "):
                continue
            relative = os.fsdecode(record[3:])
            path = (repo_root / relative).resolve()
            try:
                path.relative_to(repo_root.resolve())
            except ValueError:
                return "unknown", ""
            if not path.is_file():
                continue
            digest.update(b"\0untracked\0")
            digest.update(relative.encode("utf-8", errors="surrogateescape"))
            digest.update(b"\0")
            with path.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    digest.update(chunk)
        return "dirty", digest.hexdigest()
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return "unknown", ""


# ---------------------------------------------------------------------------
# Prompt hash tracking
# ---------------------------------------------------------------------------


class PromptHasher:
    """Process-wide registry of {prompt filename -> sha256 hex} loaded this run.

    Hooked into ``load_prompt`` in :mod:`praviar_pipeline.clients.claude_prompting`.
    Thread-safe against concurrent prompt loads.
    """

    def __init__(self) -> None:
        self._hashes: dict[str, str] = {}
        self._lock = Lock()

    def record(self, filename: str, content: str | bytes) -> str:
        """Record a prompt load and return its SHA256 hex digest."""
        data = content.encode("utf-8") if isinstance(content, str) else content
        digest = hashlib.sha256(data).hexdigest()
        with self._lock:
            self._hashes[filename] = digest
        return digest

    def snapshot(self) -> dict[str, str]:
        """Return a copy of the current {filename: sha256} mapping."""
        with self._lock:
            return dict(self._hashes)

    def reset(self) -> None:
        """Clear all recorded hashes — used between test runs / new pipelines."""
        with self._lock:
            self._hashes.clear()


_PROMPT_HASHER: ContextVar[PromptHasher | None] = ContextVar(
    "praviar_prompt_hasher",
    default=None,
)


def get_prompt_hasher() -> PromptHasher:
    """Return the current run's context-local :class:`PromptHasher`."""
    hasher = _PROMPT_HASHER.get()
    if hasher is None:
        hasher = PromptHasher()
        _PROMPT_HASHER.set(hasher)
    return hasher


# ---------------------------------------------------------------------------
# Tool-call trace digest / recorder
# ---------------------------------------------------------------------------


def _canonical_json_digest(payload: Any) -> str:
    """Return SHA256 of a canonical JSON representation."""
    blob = json_dumps(payload).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def json_dumps(payload: Any) -> str:
    """Dump JSON deterministically while tolerating non-JSON leaf values."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def sanitize_tool_arguments(arguments: Any, *, hmac_key: bytes) -> dict[str, Any]:
    """Return a plaintext-free, value-bound representation of tool arguments.

    The digest binds keys, values, nested structure, list order, and types while
    avoiding storage of patent IDs, queries, user text, or compound identifiers.
    """
    return {
        "_format": "hmac-sha256-bound-v1",
        "_type": type(arguments).__name__,
        "_hmac_sha256": hmac.new(
            hmac_key,
            b"praviar-tool-arguments-v1\0" + json_dumps(arguments).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest(),
    }


class ToolTraceRecorder:
    """Process-wide sanitized tool provenance recorder for the active run."""

    def __init__(
        self,
        *,
        hmac_key: bytes | None = None,
        key_id: str = "ephemeral",
    ) -> None:
        self._calls: list[dict[str, Any]] = []
        self._definition_hashes: dict[str, str] = {}
        self._hmac_key = bytes(hmac_key) if hmac_key is not None else secrets.token_bytes(32)
        self.key_id = key_id
        self._lock = Lock()

    def record_tool_definitions(self, tool_definitions: list[dict[str, Any]]) -> dict[str, str]:
        """Record SHA256 hashes for the allowed tool interface set.

        Reusing the same tool name with a different definition inside one run
        is treated as a provenance error instead of silently overwriting the
        hash; the report could otherwise be impossible to replay safely.
        """
        recorded: dict[str, str] = {}
        for index, definition in enumerate(tool_definitions):
            name = str(definition.get("name") or f"unnamed_tool_{index}")
            digest = _canonical_json_digest(definition)
            existing_in_batch = recorded.get(name)
            if existing_in_batch is not None and existing_in_batch != digest:
                raise RuntimeError(f"tool definition hash changed during run: {name}")
            recorded[name] = digest

        with self._lock:
            for name, digest in recorded.items():
                existing = self._definition_hashes.get(name)
                if existing is not None and existing != digest:
                    raise RuntimeError(f"tool definition hash changed during run: {name}")
                self._definition_hashes[name] = digest
            return dict(self._definition_hashes)

    def record_call(self, tool_name: str, arguments: Any) -> None:
        """Record a sanitized attempted tool call."""
        call = {
            "name": str(tool_name),
            "arguments": sanitize_tool_arguments(arguments, hmac_key=self._hmac_key),
        }
        with self._lock:
            self._calls.append(call)

    def snapshot_calls(self) -> list[dict[str, Any]]:
        """Return the sanitized call log captured so far."""
        with self._lock:
            return deepcopy(self._calls)

    def snapshot_definition_hashes(self) -> dict[str, str]:
        """Return the recorded {tool name -> definition SHA256} mapping."""
        with self._lock:
            return dict(self._definition_hashes)

    def reset(self) -> None:
        """Clear recorded tool definitions and calls for a new run."""
        with self._lock:
            self._calls.clear()
            self._definition_hashes.clear()


_TOOL_TRACE_RECORDER: ContextVar[ToolTraceRecorder | None] = ContextVar(
    "praviar_tool_trace_recorder",
    default=None,
)


def get_tool_trace_recorder() -> ToolTraceRecorder:
    """Return the current run's context-local tool trace recorder."""
    recorder = _TOOL_TRACE_RECORDER.get()
    if recorder is None:
        recorder = ToolTraceRecorder()
        _TOOL_TRACE_RECORDER.set(recorder)
    return recorder


def start_provenance_context(
    *,
    tool_trace_key: bytes | None = None,
    tool_trace_key_id: str = "ephemeral",
) -> tuple[PromptHasher, ToolTraceRecorder]:
    """Install fresh provenance collectors for the current async context."""
    hasher = PromptHasher()
    recorder = ToolTraceRecorder(hmac_key=tool_trace_key, key_id=tool_trace_key_id)
    _PROMPT_HASHER.set(hasher)
    _TOOL_TRACE_RECORDER.set(recorder)
    return hasher, recorder


def compute_tool_trace_digest(
    tool_calls: list[dict[str, Any]] | None,
    *,
    hmac_key: bytes | None = None,
) -> str:
    """Return SHA256 of the ordered, value-bound tool-call sequence."""
    if not tool_calls:
        return hashlib.sha256(b"").hexdigest()

    normalized_calls: list[dict[str, Any]] = []
    for call in tool_calls:
        if not isinstance(call, dict):
            if hmac_key is None:
                raise ValueError("tool trace HMAC key is required for raw calls")
            normalized_calls.append(
                {
                    "name": "",
                    "arguments": sanitize_tool_arguments(call, hmac_key=hmac_key),
                }
            )
            continue
        name = str(call.get("name", call.get("tool", "")))
        args = call.get("arguments") or call.get("args") or {}
        if not (
            isinstance(args, dict)
            and args.get("_format") == "hmac-sha256-bound-v1"
            and isinstance(args.get("_hmac_sha256"), str)
        ):
            if hmac_key is None:
                raise ValueError("tool trace HMAC key is required for raw calls")
            args = sanitize_tool_arguments(args, hmac_key=hmac_key)
        normalized_calls.append({"name": name, "arguments": args})
    return _canonical_json_digest(normalized_calls)


# ---------------------------------------------------------------------------
# Manifest model
# ---------------------------------------------------------------------------


class ReportManifest(BaseModel):
    """Provenance manifest emitted alongside every FTO report.

    Immutable (``frozen=True``) and strict (``extra="forbid"``) so we can
    diff manifests across runs without ambiguity.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    pipeline_version: str = Field(
        description="Praviar pipeline git SHA at runtime.",
    )
    source_tree_state: str = Field(
        default="unknown",
        description="Source checkout state: clean, dirty, build, or unknown.",
    )
    source_tree_digest: str = Field(
        default="",
        description="Digest binding the exact source tree, including local changes.",
    )
    generated_at: datetime = Field(description="UTC timestamp the manifest was built.")
    compound_query: str = Field(description="Raw user input for this run.")
    prompt_hashes: dict[str, str] = Field(
        default_factory=dict,
        description="Map of prompt filename -> SHA256 hex of file contents at load time.",
    )
    model_versions: dict[str, str] = Field(
        default_factory=dict,
        description="Map of pipeline role (triage/analysis/deep) -> model ID.",
    )
    sampling: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Per-role sampling parameters, e.g. {'triage': {'temperature': 0}}.",
    )
    source_snapshots: dict[str, str] = Field(
        default_factory=dict,
        description="Map of source name -> immutable replayable snapshot identifier.",
    )
    source_observations: dict[str, str] = Field(
        default_factory=dict,
        description="Map of live source name -> non-replayable observation metadata.",
    )
    tool_definition_hashes: dict[str, str] = Field(
        default_factory=dict,
        description="Map of allowed tool name -> SHA256 hex of its tool schema.",
    )
    tool_trace_digest: str = Field(
        description="SHA256 hex of the deterministic tool-call summary log.",
    )
    tool_trace_key_id: str = Field(
        default="",
        description="Non-secret key ID used for domain-separated tool-argument HMACs.",
    )
    tool_call_count: int = Field(
        default=0,
        description="Number of sanitized tool calls included in tool_trace_digest.",
    )
    response_cache_reference: str = Field(
        default="",
        description="Owner-only relative reference to retained exact source responses.",
    )
    response_cache_digest: str = Field(
        default="",
        description="Digest binding the complete retained response cache.",
    )
    response_cache_hmac_sha256: str = Field(
        default="",
        description="HMAC authenticating response_cache_digest.",
    )
    response_cache_key_id: str = Field(
        default="",
        description="Non-secret audit key ID used to authenticate the response cache.",
    )
    response_cache_entry_count: int = Field(
        default=0,
        ge=0,
        description="Number of retained exact external response entries.",
    )
    cost_breakdown: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description=(
            "Per-role LLM cost aggregates for the run, keyed by role "
            "(triage/analysis/deep/report/verification/critic/doe/invalidity/unknown). "
            "Each value contains input_tokens, output_tokens, cache_read_tokens, "
            "cache_creation_tokens, estimated_usd, call_count, and models (map of "
            "model-id -> call count)."
        ),
    )
    total_cost_usd: float = Field(
        default=0.0,
        description="Sum of estimated_usd across all roles for this run.",
    )


# ---------------------------------------------------------------------------
# Default sampling defaults
# ---------------------------------------------------------------------------

# Mirrors the production sampling defaults (temperature=0.0 across all stages),
# duplicated from clients/claude_runtime.py so the manifest stays accurate even
# if runtime defaults drift. Update both files together if the contract changes.
_DEFAULT_SAMPLING: dict[str, dict[str, Any]] = {
    "triage": {"temperature": 0.0, "top_p": 1.0},
    "analysis": {"temperature": 0.0, "top_p": 1.0},
    "deep": {"temperature": 0.0, "top_p": 1.0},
}


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_manifest(
    *,
    compound_query: str,
    source_health: SourceHealth | None,
    settings: Settings,
    tool_calls: list[dict[str, Any]] | None = None,
    prompt_hasher: PromptHasher | None = None,
    tool_trace_recorder: ToolTraceRecorder | None = None,
) -> ReportManifest:
    """Assemble a :class:`ReportManifest` for the just-finished pipeline run."""
    from praviar_pipeline.cost_tracker import get_current_tracker
    from praviar_pipeline.response_cache import CacheMode, get_current_cache

    hasher = prompt_hasher if prompt_hasher is not None else get_prompt_hasher()
    recorder = tool_trace_recorder if tool_trace_recorder is not None else get_tool_trace_recorder()

    model_versions: dict[str, str] = {
        "triage": getattr(settings, "claude_triage_model", ""),
        "analysis": getattr(settings, "claude_analysis_model", ""),
        "deep": getattr(settings, "claude_deep_model", ""),
    }

    snapshots: dict[str, str] = {}
    observations: dict[str, str] = {}
    if source_health is not None:
        now_iso = datetime.now(UTC).isoformat()
        for entry in source_health.entries:
            # Status check is by string value to avoid importing the enum.
            if str(getattr(entry.status, "value", entry.status)) == "ok":
                observations[entry.source] = (
                    f"observed_at={now_iso};patent_count={entry.patent_count};"
                    f"attempted_count={entry.attempted_count};covered_count={entry.covered_count}"
                )

    tracker = get_current_tracker()
    if tracker is not None:
        cost_breakdown = tracker.snapshot()
        total_cost_usd = tracker.total_usd()
    else:
        cost_breakdown = {}
        total_cost_usd = 0.0
    effective_tool_calls = tool_calls if tool_calls is not None else recorder.snapshot_calls()
    integrity_keys = getattr(settings, "checkpoint_integrity_keys", None)
    trace_hmac_key = integrity_keys.active_key() if integrity_keys is not None else None
    trace_key_id = (
        integrity_keys.active_key_id
        if tool_calls is not None and integrity_keys is not None
        else recorder.key_id
    )
    source_tree_state, source_tree_digest = compute_source_tree_provenance()
    response_cache = get_current_cache()
    if (
        response_cache is not None
        and response_cache.mode
        in {
            CacheMode.RECORD,
            CacheMode.REPLAY,
            CacheMode.REPLAY_THEN_RECORD,
        }
        and integrity_keys is not None
    ):
        response_cache_reference = response_cache.manifest_reference
        response_cache_digest = response_cache.digest()
        response_cache_hmac = response_cache.authenticated_digest(key=integrity_keys.active_key())
        response_cache_key_id = integrity_keys.active_key_id
        response_cache_entry_count = len(response_cache)
    else:
        response_cache_reference = ""
        response_cache_digest = ""
        response_cache_hmac = ""
        response_cache_key_id = ""
        response_cache_entry_count = 0

    return ReportManifest(
        pipeline_version=require_pipeline_version(),
        source_tree_state=source_tree_state,
        source_tree_digest=source_tree_digest,
        generated_at=datetime.now(UTC),
        compound_query=compound_query,
        prompt_hashes=hasher.snapshot(),
        model_versions=model_versions,
        sampling=dict(_DEFAULT_SAMPLING),
        source_snapshots=snapshots,
        source_observations=observations,
        tool_definition_hashes=recorder.snapshot_definition_hashes(),
        tool_trace_digest=compute_tool_trace_digest(
            effective_tool_calls,
            hmac_key=trace_hmac_key,
        ),
        tool_trace_key_id=trace_key_id,
        tool_call_count=len(effective_tool_calls),
        response_cache_reference=response_cache_reference,
        response_cache_digest=response_cache_digest,
        response_cache_hmac_sha256=response_cache_hmac,
        response_cache_key_id=response_cache_key_id,
        response_cache_entry_count=response_cache_entry_count,
        cost_breakdown=cost_breakdown,
        total_cost_usd=total_cost_usd,
    )
