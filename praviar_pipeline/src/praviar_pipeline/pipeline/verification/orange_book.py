"""Orange Book verification helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from praviar_pipeline.config import get_settings
from praviar_pipeline.models.verification import VerificationCheck

if TYPE_CHECKING:
    from praviar_pipeline.clients.orange_book import OrangeBookIndex
    from praviar_pipeline.models.analysis import PatentAnalysis


def check_orange_book(
    analyses: list[PatentAnalysis],
    orange_book: OrangeBookIndex | None,
) -> VerificationCheck:
    """Cross-reference blocking patents against FDA Orange Book listings."""
    if orange_book is None:
        return VerificationCheck(
            check_name="orange_book_cross_reference",
            passed=False,
            details="Orange Book cross-reference unavailable",
        )

    findings = []
    settings = get_settings()
    for analysis in analyses:
        entries = orange_book.lookup(analysis.patent_id)
        if not entries:
            continue

        nda_numbers = sorted({entry.nda_number for entry in entries if entry.nda_number})
        products = sorted({entry.product_name for entry in entries if entry.product_name})
        ingredients = sorted(
            {entry.active_ingredient for entry in entries if entry.active_ingredient}
        )
        dosage_forms_routes = sorted(
            {entry.dosage_form_route for entry in entries if entry.dosage_form_route}
        )
        exclusivity_pairs = sorted(
            {
                (record.code, record.expiration_date)
                for entry in entries
                for record in entry.exclusivities
            }
        )
        delist_requested = any(entry.delist_requested for entry in entries)

        status = "LISTED — DELIST REQUESTED" if delist_requested else "LISTED"
        risk_str = analysis.risk_level.value.upper()
        findings.append(
            f"{analysis.patent_id} ({risk_str}): Orange Book {status} — "
            f"NDA {', '.join(nda_numbers)}, "
            f"products: {', '.join(products[: settings.verification_max_ob_products])}, "
            f"ingredients: {', '.join(ingredients[: settings.verification_max_ob_products])}"
        )

        from praviar_pipeline.models.patent import (
            OrangeBookExclusivity,
            OrangeBookInfo,
        )

        analysis.orange_book_info = OrangeBookInfo(
            is_listed=True,
            nda_numbers=nda_numbers,
            product_names=products,
            active_ingredients=ingredients,
            dosage_forms_routes=dosage_forms_routes,
            reference_listed_drug=any(entry.reference_listed_drug for entry in entries),
            reference_standard=any(entry.reference_standard for entry in entries),
            drug_substance_patent=any(entry.drug_substance_patent for entry in entries),
            drug_product_patent=any(entry.drug_product_patent for entry in entries),
            patent_use_codes=sorted(
                {entry.patent_use_code for entry in entries if entry.patent_use_code}
            ),
            exclusivities=[
                OrangeBookExclusivity(code=code, expiration_date=expiration_date)
                for code, expiration_date in exclusivity_pairs
            ],
            pediatric_exclusivity=any(entry.pediatric_exclusivity for entry in entries),
            delist_requested=delist_requested,
        )

    return VerificationCheck(
        check_name="orange_book_cross_reference",
        passed=True,
        details=(
            f"Orange Book matches: {len(findings)} patents found. "
            + "; ".join(findings[: settings.verification_max_ob_findings])
            if findings
            else f"No Orange Book listings found for analyzed patents "
            f"(checked {orange_book.patent_count} listed patents)"
        ),
    )
