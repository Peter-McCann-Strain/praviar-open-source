"""Post-analysis step helpers for the Praviar Pipeline runtime."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from praviar_pipeline.logging_config import StepTimer
from praviar_pipeline.models.report_common import SourceHealthEntry, SourceStatus
from praviar_pipeline.utils.safe_diagnostics import (
    safe_exception_type,
    safe_failure_message,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from praviar_pipeline.models.regulatory_exclusivity import RegulatoryExclusivity

logger = structlog.get_logger()


def _record_regulatory_source_health(
    source_health: Any | None,
    *,
    source: str,
    status: SourceStatus,
    patent_count: int = 0,
    attempted_count: int = 0,
    covered_count: int = 0,
    error_message: str = "",
) -> SourceHealthEntry:
    entry = SourceHealthEntry(
        source=source,
        status=status,
        patent_count=patent_count,
        attempted_count=attempted_count,
        covered_count=covered_count,
        error_message=error_message,
    )
    entries = getattr(source_health, "entries", None)
    if entries is not None:
        entries.append(entry)
    return entry


async def run_critic_review(
    *,
    analyses: list,
    compound,
    timing_data: list,
    make_timing: Callable[[str, float, int, int], Any],
) -> tuple[Any, int, int]:
    from praviar_pipeline.pipeline.step4b_critic import review_analyses

    step_start = time.time()
    critic_report, critic_input_tokens, critic_output_tokens = await review_analyses(
        analyses,
        compound,
    )
    timing_data.append(
        make_timing("step4b_critic", step_start, len(analyses), len(critic_report.findings))
    )
    logger.info(
        "step4b_result",
        findings=len(critic_report.findings),
        flagged=len(critic_report.patents_flagged_for_revision),
        quality_score=critic_report.overall_quality_score,
        input_tokens=critic_input_tokens,
        output_tokens=critic_output_tokens,
    )
    return critic_report, critic_input_tokens, critic_output_tokens


async def run_doe_assessment(
    *,
    analyses: list,
    compound,
    drawing_evidence,
    timing_data: list,
    make_timing: Callable[[str, float, int, int], Any],
    prosecution_cache: dict[str, dict[str, Any]] | None = None,
) -> tuple[list, int, int]:
    from praviar_pipeline.pipeline.step5_doe import assess_equivalents

    step_start = time.time()
    with StepTimer("step5_doe", patents_in=len(analyses)):
        doe_assessments, doe_input_tokens, doe_output_tokens = await assess_equivalents(
            analyses,
            compound,
            drawing_evidence=drawing_evidence,
            prosecution_cache=prosecution_cache,
        )
    timing_data.append(make_timing("step5_doe", step_start, len(analyses), len(doe_assessments)))
    logger.info(
        "step5_result",
        assessments=len(doe_assessments),
        equivalent=sum(1 for assessment in doe_assessments if assessment.overall_equivalent),
        input_tokens=doe_input_tokens,
        output_tokens=doe_output_tokens,
    )
    return doe_assessments, doe_input_tokens, doe_output_tokens


async def run_invalidity_assessment(
    *,
    analyses: list,
    compound,
    patent_hits: list,
    drawing_evidence,
    timing_data: list,
    make_timing: Callable[[str, float, int, int], Any],
) -> tuple[list, int, int]:
    from praviar_pipeline.pipeline.step6_invalid import assess_invalidity

    step_start = time.time()
    with StepTimer("step6_invalid", patents_in=len(analyses)):
        (
            invalidity_assessments,
            invalidity_input_tokens,
            invalidity_output_tokens,
        ) = await assess_invalidity(
            analyses,
            compound,
            patent_hits=patent_hits,
            drawing_evidence=drawing_evidence,
        )
    timing_data.append(
        make_timing("step6_invalid", step_start, len(analyses), len(invalidity_assessments))
    )
    logger.info(
        "step6_result",
        assessed=len(invalidity_assessments),
        with_ptab=sum(
            1 for assessment in invalidity_assessments if assessment.ptab.has_been_challenged
        ),
        with_prior_art=sum(1 for assessment in invalidity_assessments if assessment.prior_art),
        input_tokens=invalidity_input_tokens,
        output_tokens=invalidity_output_tokens,
    )
    return invalidity_assessments, invalidity_input_tokens, invalidity_output_tokens


async def load_orange_book_if_available():
    try:
        from praviar_pipeline.clients.orange_book import load_orange_book

        orange_book = await load_orange_book()
        logger.info("orange_book_loaded", patents=orange_book.patent_count)
        return orange_book
    except (ImportError, FileNotFoundError, httpx.HTTPError, OSError) as exc:
        logger.warning(
            "orange_book_unavailable",
            error_type=safe_exception_type(exc),
        )
        return None


async def run_regulatory_enrichment(
    compound,
    *,
    source_health: Any | None = None,
) -> RegulatoryExclusivity | None:
    """Assemble regulatory exclusivity data for the compound.

    Queries Purple Book, PTE certificates, and Paragraph IV certifications
    in parallel. Each source failure is logged and recorded in SourceHealth;
    the step is non-blocking so the broader pipeline continues regardless.

    Returns a RegulatoryExclusivity instance if any data was found, else None.
    """
    import asyncio

    from praviar_pipeline.clients.purple_book import load_purple_book
    from praviar_pipeline.models.regulatory_exclusivity import PTEEntry, RegulatoryExclusivity

    is_biologic = getattr(compound, "compound_type", "small_molecule") == "biologic"
    nda_number: str = getattr(compound, "nda_number", "") or ""
    bla_number: str = getattr(compound, "bla_number", "") or ""
    compound_name: str = getattr(compound, "name", "") or ""

    sources_queried: list[str] = []
    source_statuses: list[SourceHealthEntry] = []
    purple_book_entry = None
    bpcia_expiry = None
    pte_entries: list[PTEEntry] = []
    pte_source_url = ""
    pte_source_scope = ""
    pte_source_coverage_note = ""
    pte_source_retrieved_at = None
    pte_source_publisher_last_modified = ""
    paragraph_iv_entries = []

    # --- Purple Book lookup (biologics) ---
    if is_biologic or bla_number:
        sources_queried.append("purple_book")
        try:
            index = await load_purple_book()
            lookup_key = bla_number or compound_name
            result = index.lookup_biologic(lookup_key)
            if result:
                # Retrieve the raw PurpleBookEntry for the model field
                from praviar_pipeline.clients.purple_book import PurpleBookEntry as _PBEntry

                pb_entry = _PBEntry(
                    bla_number=result["bla_number"],
                    proprietary_name=result.get("product_name", ""),
                    proper_name=result.get("proper_name", ""),
                    applicant=result.get("applicant", ""),
                    bla_type=result.get("bla_type", ""),
                    strength=result.get("strength", ""),
                    dosage_form=result.get("dosage_form", ""),
                    route=result.get("route", ""),
                    marketing_status=result.get("marketing_status", ""),
                    approval_date=result.get("approval_date", ""),
                    exclusivity_expiration=result.get("exclusivity_expiration", ""),
                    orphan_exclusivity_expiration=result.get("orphan_exclusivity_expiration", ""),
                )
                purple_book_entry = pb_entry

                # Derive BPCIA expiry from the exclusivity_expiration string
                expiry_str = result.get("exclusivity_expiration", "")
                if expiry_str:
                    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y"):
                        try:
                            import datetime

                            bpcia_expiry = datetime.datetime.strptime(expiry_str, fmt).date()
                            break
                        except ValueError:
                            pass
                logger.info(
                    "purple_book_hit",
                )
            source_statuses.append(
                _record_regulatory_source_health(
                    source_health,
                    source="purple_book",
                    status=SourceStatus.OK,
                    patent_count=1 if result else 0,
                )
            )
        except Exception as exc:
            logger.warning(
                "purple_book_enrichment_failed",
                error_type=safe_exception_type(exc),
            )
            source_statuses.append(
                _record_regulatory_source_health(
                    source_health,
                    source="purple_book",
                    status=SourceStatus.FAILED,
                    error_message=safe_failure_message("purple book enrichment", exc),
                )
            )

    # --- PTE lookup (any compound with NDA or BLA) ---
    if nda_number or bla_number or compound_name:
        sources_queried.append("pte_data")
        try:
            from praviar_pipeline.clients.pte_data import fetch_pte_certificate_dataset

            pte_dataset = await asyncio.wait_for(
                fetch_pte_certificate_dataset(),
                timeout=120.0,
            )
            raw_records = pte_dataset.records
            pte_source_url = pte_dataset.source_url
            pte_source_scope = pte_dataset.coverage_scope
            pte_source_coverage_note = pte_dataset.coverage_note
            pte_source_retrieved_at = pte_dataset.retrieved_at
            pte_source_publisher_last_modified = pte_dataset.publisher_last_modified
            # Filter to records matching this NDA/BLA or compound name
            nda_norm = (nda_number or bla_number).lstrip("NnBb").lstrip("0").lower()
            name_lower = compound_name.lower()
            for record in raw_records:
                rec_nda = record.get("nda_bla_number", "").lstrip("NnBb").lstrip("0").lower()
                rec_name = record.get("product_name", "").lower()
                if (nda_norm and nda_norm == rec_nda) or (name_lower and name_lower in rec_name):
                    pte_entries.append(
                        PTEEntry(
                            patent_number=record.get("patent_number", ""),
                            product_name=record.get("product_name", ""),
                            nda_bla_number=record.get("nda_bla_number", ""),
                            extension_days=str(record.get("extension_days", "")),
                            status="issued",
                        )
                    )
            logger.info("pte_enrichment_complete", hits=len(pte_entries))
            source_statuses.append(
                _record_regulatory_source_health(
                    source_health,
                    source="pte_data",
                    status=SourceStatus.OK,
                    patent_count=len(pte_entries),
                    attempted_count=len(raw_records),
                    covered_count=len(pte_entries),
                )
            )
        except Exception as exc:
            logger.warning(
                "pte_enrichment_failed",
                error_type=safe_exception_type(exc),
            )
            source_statuses.append(
                _record_regulatory_source_health(
                    source_health,
                    source="pte_data",
                    status=SourceStatus.FAILED,
                    error_message=safe_failure_message("PTE enrichment", exc),
                )
            )

    # --- Paragraph IV lookup (small molecules with NDA) ---
    if nda_number and not is_biologic:
        from praviar_pipeline.config import get_settings as _get_settings

        _para_iv_settings = _get_settings()
        pdf_url: str = getattr(_para_iv_settings, "paragraph_iv_pdf_url", "") or ""
        if pdf_url:
            sources_queried.append("paragraph_iv")
            try:
                from praviar_pipeline.clients.paragraph_iv import (
                    fetch_paragraph_iv_pdf,
                    lookup_paragraph_iv_status,
                    parse_paragraph_iv_pdf,
                )

                pdf_bytes = await asyncio.wait_for(
                    fetch_paragraph_iv_pdf(pdf_url),
                    timeout=60.0,
                )
                all_entries = parse_paragraph_iv_pdf(pdf_bytes)
                matched = lookup_paragraph_iv_status(nda_number, all_entries)
                paragraph_iv_entries.extend(matched)
                logger.info(
                    "paragraph_iv_enrichment_complete",
                    hits=len(matched),
                )
                source_statuses.append(
                    _record_regulatory_source_health(
                        source_health,
                        source="paragraph_iv",
                        status=SourceStatus.OK,
                        patent_count=len(matched),
                    )
                )
            except Exception as exc:
                logger.warning(
                    "paragraph_iv_enrichment_failed",
                    error_type=safe_exception_type(exc),
                )
                source_statuses.append(
                    _record_regulatory_source_health(
                        source_health,
                        source="paragraph_iv",
                        status=SourceStatus.FAILED,
                        error_message=safe_failure_message("Paragraph IV enrichment", exc),
                    )
                )
        else:
            logger.debug(
                "paragraph_iv_skipped_no_url",
            )
            source_statuses.append(
                _record_regulatory_source_health(
                    source_health,
                    source="paragraph_iv",
                    status=SourceStatus.NOT_CONFIGURED,
                    error_message="PARAGRAPH_IV_PDF_URL is not configured",
                )
            )

    # Only return a model if at least one source was queried
    if not sources_queried:
        return None

    return RegulatoryExclusivity(
        purple_book_entry=purple_book_entry,
        bpcia_exclusivity_expiry=bpcia_expiry,
        pte_extensions=pte_entries,
        pte_source_url=pte_source_url,
        pte_source_scope=pte_source_scope,
        pte_source_coverage_note=pte_source_coverage_note,
        pte_source_retrieved_at=pte_source_retrieved_at,
        pte_source_publisher_last_modified=pte_source_publisher_last_modified,
        paragraph_iv_challenges=paragraph_iv_entries,
        data_sources_queried=sources_queried,
        source_statuses=source_statuses,
    )


def run_verification_step(
    *,
    analyses: list,
    doe_assessments: list,
    invalidity_assessments: list,
    patent_hits: list,
    orange_book,
    timing_data: list,
    make_timing: Callable[[str, float, int, int], Any],
):
    from praviar_pipeline.pipeline.step7_verify import verify_analysis

    step_start = time.time()
    with StepTimer("step7_verify", patents_in=len(analyses)):
        verification = verify_analysis(
            analyses,
            doe_assessments,
            invalidity_assessments,
            patent_hits,
            orange_book=orange_book,
        )
    timing_data.append(
        make_timing("step7_verify", step_start, len(analyses), len(verification.checks))
    )
    logger.info(
        "step7_result",
        passed=verification.all_passed,
        checks=len(verification.checks),
        failed_checks=[check.check_name for check in verification.checks if not check.passed],
    )
    return verification
