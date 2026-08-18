"""Shared dataset loaders for research benchmark tooling.

Consolidates the previously duplicated `_load_all_gt()` helper across:
  - research/tools/benchmarks/score_all_reports.py
  - research/tools/benchmarks/judge_report_sections.py
  - research/tools/benchmarks/validate_report_scorer.py (indirectly via report_scorer)

And the benchmark-case loader from:
  - research/tools/benchmarks/benchmark_runner.py

This module is research-only; do not import from praviar_pipeline runtime.

Public API:
    load_benchmark_cases(benchmarks_dir)            -> list[dict[str, Any]]
    load_enriched_ground_truth(enriched_dir)        -> dict[str, dict[str, Any]]

Both return plain dicts (not Pydantic models) to match the existing call sites
without churn. Each loader is tolerant of malformed JSON files (logs and
continues); use `validate_benchmark_case()` for strict validation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Default locations
# ---------------------------------------------------------------------------

# Resolved relative to the repo root from this file's location.
# scoring_core.py / data_loader.py live in research/tools/benchmarks/, so
# parents[3] is the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BENCHMARKS_DIR = _REPO_ROOT / "research" / "benchmarks"
DEFAULT_ENRICHED_DIR = _REPO_ROOT / "research" / "benchmarks" / "enriched"
DEFAULT_RECONCILED_GT_DIR = _REPO_ROOT / "research" / "validation" / "ground-truth-extraction"
NON_FTO_CORPUS_FILES = frozenset(
    {
        "benchmark_schema.json",
        # Fixed document/OCSR holdout evaluated by its dedicated vision gate;
        # these records are patent documents, not compound FTO runs.
        "vision-production-corpus-v1.json",
    }
)


# ---------------------------------------------------------------------------
# Pydantic schema (Pydantic stands in for jsonschema, which is not a dep)
# ---------------------------------------------------------------------------


class BenchmarkCaseSchema(BaseModel):
    """Lightweight validation of a benchmark case JSON record.

    Mirrors the required fields from research/benchmarks/benchmark_schema.json
    without enforcing every property — the goal is to catch obvious malformed
    files at load time, not duplicate the full JSON Schema.
    """

    model_config = ConfigDict(extra="allow")

    id: str = Field(..., min_length=1)
    name: str | None = None
    difficulty: str | None = None
    category: str | None = None


def validate_benchmark_case(case: dict[str, Any]) -> None:
    """Validate a single benchmark case dict; raise ValueError on failure."""
    try:
        BenchmarkCaseSchema.model_validate(case)
    except ValidationError as exc:
        raise ValueError(
            f"Invalid benchmark case (id={case.get('id', '<missing>')}): {exc}"
        ) from exc


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _normalize_difficulty(value: str) -> str:
    text = value.strip().replace("-", "_").replace(" ", "_").lower()
    mapping = {
        "easy": "Easy",
        "medium": "Medium",
        "high": "Hard",
        "hard": "Hard",
        "expert": "Expert",
        "very_hard": "Expert",
        "veryhard": "Expert",
    }
    return mapping.get(text, value.strip().title())


def _normalize_compound(compound: Any, case: dict[str, Any]) -> dict[str, Any]:
    raw = dict(compound) if isinstance(compound, dict) else {}
    name = _first_text(
        raw.get("generic_name"),
        raw.get("active_ingredient"),
        raw.get("drug_name"),
        raw.get("name"),
        case.get("compound_name"),
        case.get("compound_input"),
    )
    if name and not raw.get("generic_name"):
        raw["generic_name"] = name
    if case.get("compound_input") and not raw.get("smiles"):
        raw["smiles"] = case.get("compound_input")
    return raw


def _risk_from_case(case: dict[str, Any], benchmark_value: dict[str, Any]) -> str:
    expected_outcome = case.get("expected_outcome", {})
    benchmark = case.get("benchmark", {})
    return _first_text(
        benchmark_value.get("expected_risk_today"),
        benchmark_value.get("expected_risk"),
        benchmark.get("expected_risk_today") if isinstance(benchmark, dict) else "",
        benchmark.get("expected_risk") if isinstance(benchmark, dict) else "",
        expected_outcome.get("overall_risk") if isinstance(expected_outcome, dict) else "",
        case.get("expected_risk_today"),
        "unknown",
    )


def normalize_benchmark_case(
    case: dict[str, Any],
    *,
    source_file: Path,
    index: int,
) -> dict[str, Any]:
    """Normalize heterogeneous research fixtures into runner-compatible cases."""
    normalized = dict(case)
    normalized["id"] = _first_text(case.get("id"), f"{source_file.stem}_{index:03d}")

    compound = _normalize_compound(case.get("compound"), case)
    normalized["compound"] = compound
    normalized["name"] = _first_text(
        case.get("name"),
        compound.get("generic_name"),
        compound.get("brand_name"),
        compound.get("drug_name"),
        normalized["id"],
    )

    benchmark_value = dict(case.get("benchmark_value") or case.get("benchmark") or {})
    benchmark_value["expected_risk_today"] = _risk_from_case(case, benchmark_value)
    if "blocking_patents" not in benchmark_value:
        expected_outcome = case.get("expected_outcome", {})
        if isinstance(expected_outcome, dict):
            benchmark_value["blocking_patents"] = expected_outcome.get("blocking_patents", [])
    normalized["benchmark_value"] = benchmark_value

    normalized["category"] = _first_text(
        case.get("category"),
        benchmark_value.get("category"),
        case.get("original_benchmark", {}).get("category")
        if isinstance(case.get("original_benchmark"), dict)
        else "",
        source_file.stem,
    )
    difficulty = _first_text(
        case.get("difficulty"),
        benchmark_value.get("difficulty"),
        case.get("metadata", {}).get("difficulty") if isinstance(case.get("metadata"), dict) else "",
        case.get("original_benchmark", {}).get("difficulty")
        if isinstance(case.get("original_benchmark"), dict)
        else "",
        "Medium",
    )
    normalized["difficulty"] = _normalize_difficulty(difficulty)
    normalized["_source_file"] = str(source_file)
    return normalized


def _iter_case_records(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("cases", "entries", "published_analyses"):
        records = data.get(key)
        if isinstance(records, list):
            return [item for item in records if isinstance(item, dict)]
    if "id" in data:
        return [data]
    return []


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_benchmark_cases(
    benchmarks_dir: Path | None = None,
    *,
    validate: bool = False,
) -> list[dict[str, Any]]:
    """Load benchmark cases from all JSON files in a directory.

    Supports:
      - Collection format: top-level object with a "cases", "entries",
        or "published_analyses" array.
      - Top-level array of case objects.
      - Single-case format: top-level object with an "id" field.

    Schema files and dedicated non-FTO corpora are skipped.

    Parameters
    ----------
    benchmarks_dir:
        Directory to scan. Defaults to ``research/benchmarks``.
    validate:
        If True, each loaded case is validated against ``BenchmarkCaseSchema``
        and a ``ValueError`` is raised on the first invalid case. If False
        (default, matches legacy behaviour), malformed JSON files are logged
        and skipped.
    """
    directory = benchmarks_dir or DEFAULT_BENCHMARKS_DIR
    cases: list[dict[str, Any]] = []

    if not directory.exists():
        logger.error("benchmarks_dir_not_found", path=str(directory))
        return cases

    for json_file in sorted(directory.glob("*.json")):
        if json_file.name in NON_FTO_CORPUS_FILES:
            continue

        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "benchmark_file_error",
                file=json_file.name,
                error=str(exc),
            )
            continue

        records = _iter_case_records(data)
        for idx, case in enumerate(records, start=1):
            normalized = normalize_benchmark_case(case, source_file=json_file, index=idx)
            if validate:
                try:
                    validate_benchmark_case(normalized)
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid benchmark case in {json_file}: {exc}"
                    ) from exc
            cases.append(normalized)
        if records:
            logger.info(
                "loaded_benchmark_collection",
                file=json_file.name,
                cases=len(records),
            )

    logger.info("total_benchmark_cases_loaded", count=len(cases))
    return cases


def load_reconciled_ground_truth_cases(
    root_dir: Path | None = None,
    *,
    validate: bool = False,
) -> list[dict[str, Any]]:
    """Load the reconciled legal ground-truth compounds as benchmark cases."""
    root = root_dir or DEFAULT_RECONCILED_GT_DIR
    cases: list[dict[str, Any]] = []
    for json_file in sorted(root.glob("*/reconciled/ground_truth.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "reconciled_ground_truth_file_error",
                file=str(json_file),
                error=str(exc),
            )
            continue

        compound = data.get("compound", {}) if isinstance(data, dict) else {}
        case = {
            "id": f"golden_{json_file.parents[1].name}",
            "name": compound.get("name", json_file.parents[1].name),
            "compound": compound,
            "category": "reconciled_legal_ground_truth",
            "difficulty": "Hard",
            "benchmark_value": {
                "expected_risk_today": (
                    data.get("landscape_assessment", {}).get("overall_risk_today")
                    if isinstance(data.get("landscape_assessment"), dict)
                    else ""
                )
                or "unknown",
                "blocking_patents": data.get("known_blocking_patents", []),
                "non_blocking_patents": data.get("known_non_blocking_patents", []),
            },
            "ground_truth": data,
            "_source_file": str(json_file),
        }
        normalized = normalize_benchmark_case(case, source_file=json_file, index=1)
        if validate:
            validate_benchmark_case(normalized)
        cases.append(normalized)
    logger.info("total_reconciled_ground_truth_cases_loaded", count=len(cases))
    return cases


def load_enriched_ground_truth(
    enriched_dir: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Load all enriched ground-truth cases keyed by case ``id``.

    Replaces the duplicated ``_load_all_gt()`` helpers across the research
    benchmark scripts. Returns a flat ``{case_id: case_dict}`` mapping.
    """
    directory = enriched_dir or DEFAULT_ENRICHED_DIR
    by_id: dict[str, dict[str, Any]] = {}

    if not directory.exists():
        logger.error("enriched_dir_not_found", path=str(directory))
        return by_id

    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "enriched_file_error",
                file=path.name,
                error=str(exc),
            )
            continue

        for case in data.get("cases", []):
            cid = case.get("id", "")
            if cid:
                by_id[cid] = case

    return by_id


__all__ = [
    "BenchmarkCaseSchema",
    "DEFAULT_BENCHMARKS_DIR",
    "DEFAULT_ENRICHED_DIR",
    "DEFAULT_RECONCILED_GT_DIR",
    "load_benchmark_cases",
    "load_enriched_ground_truth",
    "load_reconciled_ground_truth_cases",
    "normalize_benchmark_case",
    "validate_benchmark_case",
]
