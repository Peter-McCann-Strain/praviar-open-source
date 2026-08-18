"""Database sync helpers for the Praviar Pipeline runtime."""

from __future__ import annotations

import json

import structlog

from praviar_pipeline.config import get_settings
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

logger = structlog.get_logger()


def sync_pipeline_to_database(report_dict: dict, user_input: str, duration: float) -> None:
    """Register a CLI pipeline run in PostgreSQL for the web app."""
    db_url = get_settings().database_url
    if not db_url:
        logger.warning(
            "db_sync_skipped",
        )
        return

    try:
        import uuid as uuid_mod

        from sqlalchemy import create_engine, text
        from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError

        sync_url = db_url.replace("+asyncpg", "").replace("+aiopg", "")
        engine = create_engine(sync_url, pool_pre_ping=True)

        analysis_id = str(uuid_mod.uuid4())
        risk_summary = report_dict.get("risk_summary", {})
        compound = report_dict.get("compound", {})

        with engine.connect() as conn:
            # Use the first available user/org — single-org demo setup
            row = (
                conn.execute(
                    text("SELECT id, org_id FROM users LIMIT 1"),
                )
                .mappings()
                .first()
            )
            if not row:
                logger.error("db_sync_no_users")
                return
            user_id = str(row["id"])
            org_id = str(row["org_id"])

            # Map risk level to DB enum (uppercase)
            raw_risk = risk_summary.get("overall_risk", "low")
            risk_upper = raw_risk.upper() if raw_risk else "LOW"

            conn.execute(
                text("""
                    INSERT INTO analyses (
                        id, org_id, compound_input, compound_name, compound_smiles,
                        compound_cid, input_type, config, status, current_step,
                        progress_pct, report_data, overall_risk, blocking_patents_count,
                        total_patents_found, executive_summary,
                        total_input_tokens, total_output_tokens, estimated_cost_usd,
                        pipeline_duration_seconds, initiated_by,
                        error_message, flagged_for_review
                    ) VALUES (
                        :id, :org_id, :compound_input, :compound_name, :compound_smiles,
                        :compound_cid, :input_type, :config, 'completed', :current_step,
                        :progress_pct, :report_data, :overall_risk, :blocking_patents_count,
                        :total_patents_found, :executive_summary,
                        :total_input_tokens, :total_output_tokens, :estimated_cost_usd,
                        :pipeline_duration_seconds, :initiated_by,
                        '', false
                    )
                """),
                {
                    "id": analysis_id,
                    "org_id": org_id,
                    "compound_input": user_input,
                    "compound_name": compound.get("name", ""),
                    "compound_smiles": compound.get("canonical_smiles", ""),
                    "compound_cid": compound.get("pubchem_cid"),
                    "input_type": "name",
                    "config": "{}",
                    "current_step": 8,
                    "progress_pct": 100.0,
                    "report_data": json.dumps(report_dict, default=str),
                    "overall_risk": risk_upper,
                    "blocking_patents_count": risk_summary.get("blocking_patents_count", 0),
                    "total_patents_found": report_dict.get("total_patents_found", 0),
                    "executive_summary": risk_summary.get("executive_summary", ""),
                    "total_input_tokens": report_dict.get("total_input_tokens", 0),
                    "total_output_tokens": report_dict.get("total_output_tokens", 0),
                    "estimated_cost_usd": report_dict.get("estimated_cost_usd", 0.0),
                    "pipeline_duration_seconds": duration,
                    "initiated_by": user_id,
                },
            )

            # Commit the analysis row first so compound failures don't roll it back
            conn.commit()

            inchi_key = compound.get("inchi_key", "")
            if inchi_key:
                compound_id = str(uuid_mod.uuid4())
                try:
                    conn.execute(
                        text("""
                            INSERT INTO compounds (id, canonical_smiles, inchi_key, name,
                                molecular_formula, molecular_weight, functional_groups,
                                pubchem_cid, analysis_count)
                            VALUES (:id, :smiles, :inchi_key, :name, :formula, :mw,
                                :groups, :cid, 1)
                            ON CONFLICT (inchi_key) DO UPDATE SET
                                analysis_count = compounds.analysis_count + 1,
                                name = COALESCE(NULLIF(EXCLUDED.name, ''), compounds.name)
                        """),
                        {
                            "id": compound_id,
                            "smiles": compound.get("canonical_smiles", ""),
                            "inchi_key": inchi_key,
                            "name": compound.get("name", ""),
                            "formula": compound.get("molecular_formula", ""),
                            "mw": compound.get("molecular_weight"),
                            "groups": json.dumps(compound.get("functional_groups", [])),
                            "cid": compound.get("pubchem_cid"),
                        },
                    )
                    conn.commit()
                except (OperationalError, IntegrityError, ProgrammingError) as exc:
                    logger.warning(
                        "compound_upsert_failed",
                        operation="compound_upsert",
                        error_type=safe_exception_type(exc),
                    )
                    conn.rollback()

        engine.dispose()
        logger.info(
            "db_sync_complete",
        )

    except ImportError as exc:
        logger.error(
            "db_sync_failed",
            operation="database_sync",
            error_type=safe_exception_type(exc),
        )
    except (OperationalError, IntegrityError, ProgrammingError, OSError) as exc:
        logger.error(
            "db_sync_failed",
            operation="database_sync",
            error_type=safe_exception_type(exc),
        )
