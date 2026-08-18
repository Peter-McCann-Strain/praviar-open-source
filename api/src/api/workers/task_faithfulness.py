"""Celery task: shadow-mode Faithfulness-Aware UQ scorer (T3-02).

# -----------------------------------------------------------------------------
# Paper citation
# -----------------------------------------------------------------------------
# Vashurin, Fadeeva et al., "Faithfulness-Aware Uncertainty Quantification for
# Fact-Checking the Output of Retrieval Augmented Generation".
# arXiv:2505.21072 (May 2025). https://arxiv.org/abs/2505.21072
#
# Claimed gain: per-claim entailment scoring isolates "model is unsure" from
# "model output is unsupported by evidence", which is the failure mode that
# matters in a regulated FTO export.
#
# Deterministic smoke coverage: ``bench/faithfulness_uq_benchmark.py`` uses
# programmed synthetic responses and is not empirical performance evidence.
# Field correlation with reviewer overrides is blocked on T3-03 (labelled FTO
# decision corpus).
#
# Feasibility caveats (from the critic):
#   - Paper numbers are on QA-style RAG, not on long patent claim language;
#     accuracy may regress on dense legal prose.
#   - Per-report inference cost scales with cited spans (10 to 30 per element).
#   - Scores must NOT order the reviewer queue until calibrated; shadow only.
# -----------------------------------------------------------------------------

This task runs after the pipeline completes successfully when the
``PRAVIAR_FAITHFULNESS_UQ_ENABLED`` env var is truthy. Without the flag, no
behaviour changes and the task is never dispatched.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

logger = structlog.get_logger()


def _make_anthropic_client(api_key: str) -> object:
    """Construct an Anthropic synchronous client. Imported lazily so workers
    without the dep installed still load the module.
    """
    import anthropic

    return anthropic.Anthropic(api_key=api_key)


def _analysis_lock_key(analysis_id: uuid.UUID) -> int:
    """Return a stable signed bigint key for PostgreSQL advisory locks."""
    return analysis_id.int & ((1 << 63) - 1)


def _existing_score_count(db: Session, *, analysis_id: uuid.UUID, model_id: str) -> int:
    from api.db.models import FaithfulnessScore

    result = db.execute(
        select(func.count(FaithfulnessScore.id)).where(
            FaithfulnessScore.analysis_id == analysis_id,
            FaithfulnessScore.model_id == model_id,
        )
    )
    return int(result.scalar() or 0)


def compute_faithfulness_scores_impl(
    *,
    engine,
    analysis_id: str,
    org_id: str,
    client_factory=_make_anthropic_client,
    settings_factory=None,
    max_pairs: int | None = 50,
) -> dict:
    """Score (claim, evidence) pairs for the named analysis and persist them.

    Returns a small summary dict suitable for logging or returning from a
    Celery task. Caller is responsible for providing the tenant context used
    for RLS binding and ownership checks.
    """
    from api.config import get_settings
    from api.db.models import Analysis
    from api.db.session import bind_org_to_sync_session
    from api.errors import APIError
    from api.services.faithfulness_uq import (
        FAITHFULNESS_MODEL_ID,
        is_feature_enabled,
        score_report,
    )
    from api.services.no_paid_api import no_paid_api_enabled
    from api.services.report_access import require_completed_report_payload

    if not is_feature_enabled():
        logger.debug("faithfulness_uq_disabled_skip", analysis_id=analysis_id)
        return {"status": "disabled", "analysis_id": analysis_id, "scored": 0}
    if not org_id:
        raise ValueError("org_id is required for faithfulness scoring")

    try:
        analysis_uuid = uuid.UUID(str(analysis_id))
    except ValueError:
        logger.warning("faithfulness_uq_invalid_analysis_id", analysis_id=analysis_id)
        return {"status": "invalid_analysis_id", "analysis_id": analysis_id, "scored": 0}

    lock_key = _analysis_lock_key(analysis_uuid)
    with engine.connect() as lock_conn:
        result = lock_conn.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key})
        if not bool(result.scalar()):
            logger.info("faithfulness_uq_skipped_already_running", analysis_id=analysis_id)
            return {"status": "already_running", "analysis_id": analysis_id, "scored": 0}
        try:
            with Session(engine) as db:
                bind_org_to_sync_session(db, org_id)
                analysis = db.get(Analysis, analysis_uuid)
                if not analysis:
                    logger.warning("faithfulness_uq_analysis_missing", analysis_id=analysis_id)
                    return {"status": "missing", "analysis_id": analysis_id, "scored": 0}
                if str(analysis.org_id) != str(org_id):
                    logger.error(
                        "faithfulness_uq_org_mismatch",
                        analysis_id=analysis_id,
                        expected_org_id=org_id,
                        actual_org_id=str(analysis.org_id),
                    )
                    return {"status": "blocked", "analysis_id": analysis_id, "scored": 0}
                if analysis.report_data is None:
                    logger.info("faithfulness_uq_no_report_data", analysis_id=analysis_id)
                    return {"status": "no_report", "analysis_id": analysis_id, "scored": 0}

                existing_count = _existing_score_count(
                    db,
                    analysis_id=analysis_uuid,
                    model_id=FAITHFULNESS_MODEL_ID,
                )
                if existing_count:
                    logger.info(
                        "faithfulness_uq_skipped_already_scored",
                        analysis_id=analysis_id,
                        model_id=FAITHFULNESS_MODEL_ID,
                        scored=existing_count,
                    )
                    return {
                        "status": "already_scored",
                        "analysis_id": analysis_id,
                        "scored": existing_count,
                    }

                try:
                    report_data = require_completed_report_payload(analysis)
                except APIError as exc:
                    logger.info(
                        "faithfulness_uq_unpublishable_report",
                        analysis_id=analysis_id,
                        detail=exc.detail,
                        hint="skipping shadow scoring until report publishability gates pass",
                    )
                    return {
                        "status": "unpublishable_report",
                        "analysis_id": analysis_id,
                        "scored": 0,
                    }

                settings = (settings_factory or get_settings)()
                api_key = getattr(settings, "anthropic_api_key", "") or ""
                if not api_key:
                    logger.warning(
                        "faithfulness_uq_no_api_key",
                        analysis_id=analysis_id,
                        hint="ANTHROPIC_API_KEY is unset; skipping shadow scoring",
                    )
                    return {"status": "no_api_key", "analysis_id": analysis_id, "scored": 0}
                if client_factory is _make_anthropic_client and no_paid_api_enabled():
                    logger.warning(
                        "faithfulness_uq_no_paid_api_blocked",
                        analysis_id=analysis_id,
                        hint="NO_PAID_API=true; skipping live shadow scoring",
                    )
                    return {"status": "no_paid_api", "analysis_id": analysis_id, "scored": 0}

                client = client_factory(api_key)
                results = score_report(
                    report_data=report_data,
                    client=client,
                    model_id=FAITHFULNESS_MODEL_ID,
                    max_pairs=max_pairs,
                )

                rows = _build_rows(
                    analysis_id=analysis.id,
                    org_id=analysis.org_id,
                    results=results,
                )
                # Bind tenant context before persisting so the org_isolation RLS
                # policy accepts the INSERT. Worker role has BYPASSRLS in prod;
                # this keeps the write path correct under a non-privileged role too.
                db.execute(
                    select(func.set_config("app.current_org_id", str(analysis.org_id), True))
                )
                if rows:
                    from api.db.models import FaithfulnessScore

                    db.execute(
                        pg_insert(FaithfulnessScore)
                        .values(
                            [
                                {
                                    "id": r.id,
                                    "org_id": r.org_id,
                                    "analysis_id": r.analysis_id,
                                    "finding_index": r.finding_index,
                                    "evidence_index": r.evidence_index,
                                    "claim_sentence": r.claim_sentence,
                                    "evidence_span": r.evidence_span,
                                    "verdict": r.verdict,
                                    "confidence": r.confidence,
                                    "model_id": r.model_id,
                                }
                                for r in rows
                            ]
                        )
                        .on_conflict_do_nothing(
                            constraint="uq_faithfulness_scores_analysis_pair_model"
                        )
                    )
                db.commit()
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})

    verdict_counts = {label: 0 for label in ("ENTAILED", "NEUTRAL", "CONTRADICTS")}
    for _, verdict in results:
        verdict_counts[verdict.verdict] = verdict_counts.get(verdict.verdict, 0) + 1
    logger.info(
        "faithfulness_uq_completed",
        analysis_id=analysis_id,
        scored=len(results),
        verdict_counts=verdict_counts,
    )
    return {
        "status": "completed",
        "analysis_id": analysis_id,
        "scored": len(results),
        "verdict_counts": verdict_counts,
    }


def _build_rows(
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    results: Iterable[tuple[Any, Any]],
) -> list[Any]:
    """Materialise FaithfulnessScore ORM rows from scorer output."""
    from api.db.models import FaithfulnessScore

    rows: list[Any] = []
    for pair, verdict in results:
        rows.append(
            FaithfulnessScore(
                org_id=org_id,
                analysis_id=analysis_id,
                finding_index=pair.finding_index,
                evidence_index=pair.evidence_index,
                claim_sentence=pair.claim_sentence,
                evidence_span=pair.evidence_span,
                verdict=verdict.verdict,
                confidence=verdict.confidence,
                model_id=verdict.model_id,
            )
        )
    return rows
