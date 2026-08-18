"""Resolve structured customer act facts into legally material categories.

The legacy commercial-action narrative is deliberately non-governing.  It may
still be shown to reviewers, but keyword matching never establishes an act,
territory, date, actor, or purpose.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from pydantic import ValidationError

from praviar_pipeline.models.accused_acts import (
    AccusedActRecord,
    verify_claimed_use_match_receipt,
)

_US_TERRITORY_ALIASES = {
    "US",
    "USA",
    "UNITED STATES",
    "UNITED STATES OF AMERICA",
}
_EP_TERRITORY_ALIASES = {
    "EP",
    "EPC",
    "EU",
    "EUROPE",
    "EUROPEAN UNION",
    "UPC",
}
_EPC_STATE_CODES = {
    "AL",
    "AT",
    "BE",
    "BG",
    "CH",
    "CY",
    "CZ",
    "DE",
    "DK",
    "EE",
    "ES",
    "FI",
    "FR",
    "GB",
    "GR",
    "HR",
    "HU",
    "IE",
    "IS",
    "IT",
    "LI",
    "LT",
    "LU",
    "LV",
    "MC",
    "ME",
    "MK",
    "MT",
    "NL",
    "NO",
    "PL",
    "PT",
    "RO",
    "RS",
    "SE",
    "SI",
    "SK",
    "SM",
    "TR",
}
_PRECOMMERCIAL_STAGES = {
    "discovery",
    "lead_optimization",
    "preclinical",
    "clinical",
    "regulatory",
    "registration",
}
_NONCOMMERCIAL_PURPOSES = {
    "clinical_research",
    "experimental",
    "internal_research",
    "regulatory_approval",
}
_ARTIFICIAL_INFRINGEMENT_PATHS = {
    "anda",
    "nda_505_b_2",
    "abla",
    "biosimilar_351_k",
}


def _product_context_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def structured_accused_act_records(
    product_context: object = None,
) -> tuple[AccusedActRecord, ...]:
    """Return the exact validated act record set, failing closed as one unit."""
    raw_records = _product_context_mapping(product_context).get("accused_acts")
    if not isinstance(raw_records, (list, tuple)) or not raw_records:
        return ()
    records: list[AccusedActRecord] = []
    try:
        for raw_record in raw_records:
            records.append(
                raw_record
                if isinstance(raw_record, AccusedActRecord)
                else AccusedActRecord.model_validate(raw_record)
            )
    except (TypeError, ValueError, ValidationError):
        return ()
    return tuple(records)


def governing_accused_act_records(
    product_context: object = None,
    *,
    jurisdiction: object = None,
) -> tuple[AccusedActRecord, ...]:
    """Return affirmative records, optionally restricted to one jurisdiction."""
    normalized_jurisdiction = str(jurisdiction or "").strip().upper()
    return tuple(
        record
        for record in structured_accused_act_records(product_context)
        if record.can_establish_exposure
        and (not normalized_jurisdiction or record.jurisdiction == normalized_jurisdiction)
    )


def normalize_accused_acts(
    intended_actions: list[str] | tuple[str, ...] | None,
    product_context: object = None,
    *,
    jurisdiction: object = None,
) -> list[str]:
    """Return acts established by structured records.

    ``intended_actions`` remains in the signature for call-site compatibility,
    but it is a review-scope selector, not evidence that an act will occur.
    Free-form product context is likewise never parsed for governing facts.
    """
    del intended_actions
    acts: list[str] = []
    today = date.today()
    for record in governing_accused_act_records(
        product_context,
        jurisdiction=jurisdiction,
    ):
        historical = (
            record.status == "actual" and record.end_date is not None and record.end_date < today
        )
        acts.append(f"past_{record.act}" if historical else record.act)

    return list(dict.fromkeys(act for act in acts if act))


def past_acts_in_scope(accused_acts: list[str] | tuple[str, ...]) -> bool:
    """Return whether any normalized accused act is expressly historical."""
    return any(str(action or "").startswith("past_") for action in accused_acts)


def accused_act_years(product_context: object = None) -> tuple[int, ...]:
    """Return years from exact structured act dates (legacy compatibility helper)."""
    return tuple(
        dict.fromkeys(
            year
            for record in governing_accused_act_records(product_context)
            for year in (
                record.start_date.year,
                *([record.end_date.year] if record.end_date is not None else []),
            )
        )
    )


def commercial_territories(product_context: object = None) -> tuple[str, ...]:
    """Return normalized customer-declared commercial territories."""
    raw = _product_context_mapping(product_context).get("commercial_territories")
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(
        dict.fromkeys(
            " ".join(str(value).strip().upper().replace("_", " ").split())
            for value in raw
            if str(value).strip()
        )
    )


def territory_supports_jurisdiction(
    product_context: object,
    jurisdiction: object,
) -> bool:
    """Require both a matching act record and declared commercial territory."""
    territories = set(commercial_territories(product_context))
    normalized_jurisdiction = str(jurisdiction or "").strip().upper()
    if not territories or not normalized_jurisdiction:
        return False
    if not governing_accused_act_records(
        product_context,
        jurisdiction=normalized_jurisdiction,
    ):
        return False
    if normalized_jurisdiction == "US":
        return bool(territories.intersection(_US_TERRITORY_ALIASES))
    if normalized_jurisdiction == "EP":
        return bool(
            territories.intersection(_EP_TERRITORY_ALIASES)
            or territories.intersection(_EPC_STATE_CODES)
        )
    return normalized_jurisdiction in territories


def regulatory_safe_harbor_review_required(
    *,
    accused_acts: list[str] | tuple[str, ...],
    product_context: object,
    development_stage: object,
    jurisdiction: object = None,
) -> bool:
    """Flag acts that could implicate a regulatory-development safe harbor."""
    records = governing_accused_act_records(
        product_context,
        jurisdiction=jurisdiction,
    )
    if not records:
        return False
    normalized_acts = {
        str(act).removeprefix("past_")
        for act in accused_acts
        if str(act).removeprefix("past_") != "regulatory_submission"
    }
    if not normalized_acts.intersection({"import", "manufacture", "use"}):
        return False
    stage = str(development_stage or "").strip().lower()
    return stage in _PRECOMMERCIAL_STAGES or any(
        record.purpose in _NONCOMMERCIAL_PURPOSES
        for record in records
        if record.act in {"import", "manufacture", "use"}
    )


def submission_path_supports_artificial_infringement(
    record: AccusedActRecord,
) -> bool:
    """Return whether a submission path is one expressly modeled under §271(e)(2)."""
    return (
        record.act == "regulatory_submission"
        and record.regulatory_path in _ARTIFICIAL_INFRINGEMENT_PATHS
        and record.liability_theory == "artificial_infringement"
    )


def submission_target_matches_compound(
    record: AccusedActRecord,
    compound: object,
) -> bool:
    """Require the declared submission product to match a resolved identity."""
    target = " ".join(str(record.target_product_identity or "").casefold().split())
    if not target:
        return False
    model_dump = getattr(compound, "model_dump", None)
    raw = model_dump(mode="json") if callable(model_dump) else {}
    if not isinstance(raw, Mapping):
        return False
    candidates = {
        " ".join(str(raw.get(field) or "").casefold().split())
        for field in (
            "name",
            "canonical_smiles",
            "inchi_key",
            "original_input",
        )
        if str(raw.get(field) or "").strip()
    }
    return target in candidates


def _verified_claimed_use_match(
    record: AccusedActRecord,
    *,
    patent_id: str,
    claim_number: int,
    controlling_claim_text: str,
    current_claim_receipt_sha256: str,
    controlling_claim_document_ids: list[str],
    compound: object,
    receipt_verification_keys: object,
) -> bool:
    label_carve_out_state = record.label_carve_out_state
    if (
        label_carve_out_state in {None, "complete", "unknown"}
        or not controlling_claim_text.strip()
        or not current_claim_receipt_sha256
        or not controlling_claim_document_ids
        or receipt_verification_keys is None
    ):
        return False
    assert label_carve_out_state is not None
    verification_key = getattr(receipt_verification_keys, "verification_key", None)
    if not callable(verification_key):
        return False
    for receipt in record.claimed_use_match_receipts:
        try:
            attestation_key = verification_key(receipt.attestation_key_id)
        except ValueError:
            continue
        if verify_claimed_use_match_receipt(
            receipt,
            attestation_key=attestation_key,
            patent_id=patent_id,
            claim_number=claim_number,
            controlling_claim_text=controlling_claim_text,
            current_claim_receipt_sha256=current_claim_receipt_sha256,
            controlling_claim_document_ids=controlling_claim_document_ids,
            target_product_identity=record.target_product_identity or "",
            compound=compound,
            proposed_indication=record.proposed_indication or "",
            proposed_label_use=record.proposed_label_use or "",
            label_carve_out_state=label_carve_out_state,
        ):
            return True
    return False


def accused_act_supports_claim_category(
    record: AccusedActRecord,
    *,
    claim_category: str,
    jurisdiction: str,
    patent_id: str = "",
    claim_number: int = 0,
    controlling_claim_text: str = "",
    current_claim_receipt_sha256: str = "",
    controlling_claim_document_ids: list[str] | None = None,
    compound: object = None,
    receipt_verification_keys: object = None,
) -> bool:
    """Apply direct, induced, submission, and §271(g) act-category gates."""
    if not record.can_establish_exposure or record.jurisdiction != jurisdiction:
        return False
    if claim_category == "method_of_use":
        return (
            (
                submission_path_supports_artificial_infringement(record)
                and submission_target_matches_compound(record, compound)
                and _verified_claimed_use_match(
                    record,
                    patent_id=patent_id,
                    claim_number=claim_number,
                    controlling_claim_text=controlling_claim_text,
                    current_claim_receipt_sha256=current_claim_receipt_sha256,
                    controlling_claim_document_ids=(controlling_claim_document_ids or []),
                    compound=compound,
                    receipt_verification_keys=receipt_verification_keys,
                )
            )
            or (
                record.act == "use"
                and record.liability_theory == "direct"
                and record.performs_all_claim_steps is True
            )
            or (
                record.act == "use"
                and record.liability_theory == "induced"
                and record.performs_all_claim_steps is True
                and bool(record.direct_infringer)
                and record.knowledge_of_patent is True
                and record.affirmative_encouragement is True
            )
        )
    if claim_category == "process":
        return (
            record.act == "manufacture"
            and record.liability_theory == "direct"
            and record.performs_all_claim_steps is True
        ) or (
            record.act in {"import", "offer_for_sale", "sale", "use"}
            and record.liability_theory == "direct"
            and bool(record.manufacturing_jurisdiction)
            and record.manufacturing_jurisdiction != jurisdiction
            and bool(record.process_used)
            and record.process_use_verified is True
            and record.materially_changed_after_process is False
            and record.trivial_component_after_process is False
        )
    return (
        record.act in {"import", "manufacture", "offer_for_sale", "sale", "use"}
        and record.liability_theory == "direct"
    ) or (
        submission_path_supports_artificial_infringement(record)
        and submission_target_matches_compound(record, compound)
    )


__all__ = [
    "accused_act_supports_claim_category",
    "accused_act_years",
    "commercial_territories",
    "governing_accused_act_records",
    "normalize_accused_acts",
    "past_acts_in_scope",
    "regulatory_safe_harbor_review_required",
    "structured_accused_act_records",
    "submission_path_supports_artificial_infringement",
    "submission_target_matches_compound",
    "territory_supports_jurisdiction",
]
