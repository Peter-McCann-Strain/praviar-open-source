from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

from praviar_pipeline.config import Settings
from praviar_pipeline.models.accused_acts import (
    AccusedActRecord,
    create_claimed_use_match_receipt,
    verify_claimed_use_match_attestation,
)
from praviar_pipeline.models.compound import ResolvedCompound
from praviar_pipeline.pipeline.accused_acts import (
    accused_act_supports_claim_category,
    normalize_accused_acts,
    regulatory_safe_harbor_review_required,
    structured_accused_act_records,
    submission_path_supports_artificial_infringement,
    territory_supports_jurisdiction,
)
from praviar_pipeline.pipeline.runtime.evidence_claims import (
    _accused_act_nexus_verified,
    _claimed_use_current_claim_context,
)

_CONTROLLING_CLAIM_TEXT = (
    "1. A method of secondary prevention of myocardial infarction comprising "
    "administering 75 mg aspirin once daily."
)
_CURRENT_CLAIM_RECEIPT_SHA256 = "a" * 64
_CONTROLLING_CLAIM_DOCUMENT_IDS = ["US1234567B2:grant-claims"]
_ANALYSIS_ID = UUID("11111111-1111-4111-8111-111111111111")
_ORG_ID = UUID("22222222-2222-4222-8222-222222222222")
_ISSUER_USER_ID = UUID("33333333-3333-4333-8333-333333333333")


@pytest.mark.parametrize(
    "narrative",
    [
        "No sale or import is planned.",
        "We will not manufacture, import, sell, offer for sale, or use in the US.",
        "Manufacture and sale will occur in India only, never in the US.",
        "Assess how to avoid a possible future launch.",
        "Hypothetically, the buyer might import the product.",
    ],
)
def test_free_text_never_establishes_an_accused_act(narrative: str) -> None:
    context = {
        "commercial_action": narrative,
        "commercial_territories": ["US"],
    }

    assert normalize_accused_acts(["commercial_launch"], context) == []
    assert territory_supports_jurisdiction(context, "US") is False


def test_denied_and_hypothetical_records_are_non_governing() -> None:
    context = {
        "commercial_territories": ["US"],
        "accused_acts": [
            _record(status="denied", act="sale"),
            _record(status="hypothetical", act="import"),
        ],
    }

    assert normalize_accused_acts(None, context) == []
    assert territory_supports_jurisdiction(context, "US") is False


def test_india_only_record_cannot_establish_a_us_nexus() -> None:
    context = {
        "commercial_territories": ["IN"],
        "accused_acts": [_record(jurisdiction="IN", act="manufacture")],
    }

    assert normalize_accused_acts(None, context) == ["manufacture"]
    assert territory_supports_jurisdiction(context, "US") is False
    assert territory_supports_jurisdiction(context, "IN") is True


def test_positive_record_requires_matching_declared_commercial_territory() -> None:
    context = {
        "commercial_territories": ["EP"],
        "accused_acts": [_record(jurisdiction="US", act="import")],
    }

    assert normalize_accused_acts(None, context) == ["import"]
    assert territory_supports_jurisdiction(context, "US") is False


def test_completed_actual_record_is_explicitly_historical() -> None:
    context = {
        "commercial_territories": ["US"],
        "accused_acts": [
            _record(
                act="sale",
                status="actual",
                start_date="2020-01-01",
                end_date="2020-12-31",
            )
        ],
    }

    assert normalize_accused_acts(None, context) == ["past_sale"]


@pytest.mark.parametrize(
    "path",
    ["anda", "nda_505_b_2", "abla", "biosimilar_351_k"],
)
def test_statutory_submission_paths_are_modeled_as_artificial_infringement(
    path: str,
) -> None:
    record = AccusedActRecord.model_validate(
        _record(
            act="regulatory_submission",
            purpose="regulatory_approval",
            regulatory_path=path,
        )
    )

    assert submission_path_supports_artificial_infringement(record) is True
    assert (
        regulatory_safe_harbor_review_required(
            accused_acts=["regulatory_submission"],
            product_context={
                "commercial_territories": ["US"],
                "accused_acts": [record.model_dump(mode="json")],
            },
            development_stage="preclinical",
        )
        is False
    )


@pytest.mark.parametrize("path", ["nda_505_b_1", "bla_351_a", "unknown"])
def test_other_submission_paths_do_not_establish_artificial_infringement(
    path: str,
) -> None:
    record = AccusedActRecord.model_validate(
        _record(
            act="regulatory_submission",
            purpose="regulatory_approval",
            regulatory_path=path,
        )
    )

    assert submission_path_supports_artificial_infringement(record) is False


def test_noncommercial_manufacture_requires_safe_harbor_review() -> None:
    context = {
        "commercial_territories": ["US"],
        "accused_acts": [
            _record(
                act="manufacture",
                purpose="clinical_research",
            )
        ],
    }

    assert regulatory_safe_harbor_review_required(
        accused_acts=["manufacture"],
        product_context=context,
        development_stage="clinical",
    )


def test_structured_contract_rejects_incoherent_dates_and_submission_fields() -> None:
    with pytest.raises(ValidationError, match="end_date"):
        AccusedActRecord.model_validate(_record(start_date="2027-01-02", end_date="2027-01-01"))
    with pytest.raises(ValidationError, match="regulatory_path"):
        AccusedActRecord.model_validate(
            _record(act="regulatory_submission", purpose="regulatory_approval")
        )
    with pytest.raises(ValidationError, match="only valid"):
        AccusedActRecord.model_validate(_record(act="sale", regulatory_path="anda"))


def test_temporal_status_cannot_assert_future_actual_or_stale_planned_act() -> None:
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    with pytest.raises(ValidationError, match="cannot start in the future"):
        AccusedActRecord.model_validate(_record(status="actual", start_date=tomorrow))
    with pytest.raises(ValidationError, match="require reconfirmation"):
        AccusedActRecord.model_validate(_record(status="planned", start_date=yesterday))


def test_method_claim_requires_direct_all_steps_or_complete_inducement_facts() -> None:
    direct_use = AccusedActRecord.model_validate(_record(act="use"))
    assert not accused_act_supports_claim_category(
        direct_use,
        claim_category="method_of_use",
        jurisdiction="US",
    )
    assert accused_act_supports_claim_category(
        AccusedActRecord.model_validate({**_record(act="use"), "performs_all_claim_steps": True}),
        claim_category="method_of_use",
        jurisdiction="US",
    )

    incomplete_inducement = AccusedActRecord.model_validate(
        {
            **_record(act="use", liability_theory="induced"),
            "direct_infringer": "Prescribing physician",
            "performs_all_claim_steps": True,
            "knowledge_of_patent": True,
        }
    )
    assert not accused_act_supports_claim_category(
        incomplete_inducement,
        claim_category="method_of_use",
        jurisdiction="US",
    )
    assert accused_act_supports_claim_category(
        incomplete_inducement.model_copy(update={"affirmative_encouragement": True}),
        claim_category="method_of_use",
        jurisdiction="US",
    )


def test_process_claim_requires_direct_all_steps_or_complete_271g_linkage() -> None:
    generic_import = AccusedActRecord.model_validate(_record(act="import"))
    assert not accused_act_supports_claim_category(
        generic_import,
        claim_category="process",
        jurisdiction="US",
    )

    direct_process = AccusedActRecord.model_validate(
        {**_record(act="manufacture"), "performs_all_claim_steps": True}
    )
    assert accused_act_supports_claim_category(
        direct_process,
        claim_category="process",
        jurisdiction="US",
    )

    imported_process_product = AccusedActRecord.model_validate(
        {
            **_record(act="import"),
            "manufacturing_jurisdiction": "CN",
            "process_used": "Claimed crystallization process",
            "process_use_verified": True,
            "materially_changed_after_process": False,
            "trivial_component_after_process": False,
        }
    )
    assert accused_act_supports_claim_category(
        imported_process_product,
        claim_category="process",
        jurisdiction="US",
    )


def test_only_eligible_submission_path_supports_product_claim_nexus() -> None:
    anda = AccusedActRecord.model_validate(
        _record(
            act="regulatory_submission",
            purpose="regulatory_approval",
            regulatory_path="anda",
        )
    )
    ordinary_nda = AccusedActRecord.model_validate(
        _record(
            act="regulatory_submission",
            purpose="regulatory_approval",
            regulatory_path="nda_505_b_1",
        )
    )

    assert accused_act_supports_claim_category(
        anda,
        claim_category="product",
        jurisdiction="US",
        compound=_compound(),
    )
    assert not accused_act_supports_claim_category(
        ordinary_nda,
        claim_category="product",
        jurisdiction="US",
        compound=_compound(),
    )


def test_submission_cannot_support_method_claim_without_verified_use_receipt() -> None:
    anda = AccusedActRecord.model_validate(
        _record(
            act="regulatory_submission",
            purpose="regulatory_approval",
            regulatory_path="anda",
        )
    )

    assert not accused_act_supports_claim_category(
        anda,
        claim_category="method_of_use",
        jurisdiction="US",
        patent_id="US1234567B2",
        claim_number=1,
        compound=_compound(),
        receipt_verification_keys=_KeyRing(),
    )


def test_runtime_method_nexus_fails_closed_without_claim_specific_receipt() -> None:
    compound = _compound()
    method_claim = SimpleNamespace(
        claim_number=1,
        preamble="A method of treating a patient",
        elements=[SimpleNamespace(element_text="administering aspirin for secondary prevention")],
    )
    record = _record(
        act="regulatory_submission",
        purpose="regulatory_approval",
        regulatory_path="anda",
    )
    context = {
        "commercial_territories": ["US"],
        "accused_acts": [record],
    }

    assert not _accused_act_nexus_verified(
        method_claim,
        None,
        patent_id="US1234567B2",
        accused_acts=["regulatory_submission"],
        product_context=context,
        jurisdiction="US",
        analysis_context_verified=True,
        compound_identity=compound,
        receipt_verification_keys=_KeyRing(),
    )


def test_claimed_use_receipt_is_claim_product_label_and_indication_specific() -> None:
    compound = _compound()
    receipt = create_claimed_use_match_receipt(
        analysis_id=_ANALYSIS_ID,
        org_id=_ORG_ID,
        report_id="report-fixture",
        report_fingerprint="b" * 64,
        accused_act_index=0,
        accused_act_sha256="c" * 64,
        patent_id="US1234567B2",
        claim_number=1,
        controlling_claim_text=_CONTROLLING_CLAIM_TEXT,
        current_claim_receipt_sha256=_CURRENT_CLAIM_RECEIPT_SHA256,
        controlling_claim_document_ids=_CONTROLLING_CLAIM_DOCUMENT_IDS,
        target_product_identity="aspirin",
        compound=compound,
        proposed_indication="Secondary prevention of myocardial infarction",
        proposed_label_use="75 mg orally once daily for secondary prevention",
        label_carve_out_state="none",
        issuer_user_id=_ISSUER_USER_ID,
        verified_at=datetime.now(UTC),
        evidence_references=["proposed-label-v7#section-1"],
        attestation_key_id="test-key",
        attestation_key=_KeyRing.key,
    )
    record = AccusedActRecord.model_validate(
        {
            **_record(
                act="regulatory_submission",
                purpose="regulatory_approval",
                regulatory_path="anda",
            ),
            "claimed_use_match_receipts": [receipt.model_dump(mode="json")],
        }
    )

    assert verify_claimed_use_match_attestation(
        receipt,
        attestation_key=_KeyRing.key,
    )
    assert not verify_claimed_use_match_attestation(
        receipt.model_copy(update={"attestation_hmac_sha256": "f" * 64}),
        attestation_key=_KeyRing.key,
    )

    assert accused_act_supports_claim_category(
        record,
        claim_category="method_of_use",
        jurisdiction="US",
        patent_id="US1234567B2",
        claim_number=1,
        controlling_claim_text=_CONTROLLING_CLAIM_TEXT,
        current_claim_receipt_sha256=_CURRENT_CLAIM_RECEIPT_SHA256,
        controlling_claim_document_ids=_CONTROLLING_CLAIM_DOCUMENT_IDS,
        compound=compound,
        receipt_verification_keys=_KeyRing(),
    )
    assert not accused_act_supports_claim_category(
        record,
        claim_category="method_of_use",
        jurisdiction="US",
        patent_id="US1234567B2",
        claim_number=2,
        controlling_claim_text=_CONTROLLING_CLAIM_TEXT,
        current_claim_receipt_sha256=_CURRENT_CLAIM_RECEIPT_SHA256,
        controlling_claim_document_ids=_CONTROLLING_CLAIM_DOCUMENT_IDS,
        compound=compound,
        receipt_verification_keys=_KeyRing(),
    )
    assert not accused_act_supports_claim_category(
        record.model_copy(update={"proposed_label_use": "A changed proposed label"}),
        claim_category="method_of_use",
        jurisdiction="US",
        patent_id="US1234567B2",
        claim_number=1,
        controlling_claim_text=_CONTROLLING_CLAIM_TEXT,
        current_claim_receipt_sha256=_CURRENT_CLAIM_RECEIPT_SHA256,
        controlling_claim_document_ids=_CONTROLLING_CLAIM_DOCUMENT_IDS,
        compound=compound,
        receipt_verification_keys=_KeyRing(),
    )
    assert not accused_act_supports_claim_category(
        record.model_copy(update={"proposed_indication": "A different indication"}),
        claim_category="method_of_use",
        jurisdiction="US",
        patent_id="US1234567B2",
        claim_number=1,
        controlling_claim_text=_CONTROLLING_CLAIM_TEXT,
        current_claim_receipt_sha256=_CURRENT_CLAIM_RECEIPT_SHA256,
        controlling_claim_document_ids=_CONTROLLING_CLAIM_DOCUMENT_IDS,
        compound=compound,
        receipt_verification_keys=_KeyRing(),
    )


@pytest.mark.parametrize(
    "required_literal",
    [
        "schema_version",
        "claimed_use_match",
        "product_identity_match",
        "reviewer_role",
        "attestation_statement_version",
    ],
)
def test_claimed_use_receipt_requires_every_signed_literal(
    required_literal: str,
) -> None:
    receipt = create_claimed_use_match_receipt(
        analysis_id=_ANALYSIS_ID,
        org_id=_ORG_ID,
        report_id="report-required-literals",
        report_fingerprint="b" * 64,
        accused_act_index=0,
        accused_act_sha256="c" * 64,
        patent_id="US1234567B2",
        claim_number=1,
        controlling_claim_text=_CONTROLLING_CLAIM_TEXT,
        current_claim_receipt_sha256=_CURRENT_CLAIM_RECEIPT_SHA256,
        controlling_claim_document_ids=_CONTROLLING_CLAIM_DOCUMENT_IDS,
        target_product_identity="aspirin",
        compound=_compound(),
        proposed_indication="Secondary prevention of myocardial infarction",
        proposed_label_use="75 mg orally once daily for secondary prevention",
        label_carve_out_state="none",
        issuer_user_id=_ISSUER_USER_ID,
        verified_at=datetime.now(UTC),
        evidence_references=["proposed-label-v7#section-1"],
        attestation_key_id="test-key",
        attestation_key=_KeyRing.key,
    )
    payload = receipt.model_dump(mode="json")
    payload.pop(required_literal)

    with pytest.raises(ValueError, match="Field required"):
        type(receipt).model_validate(payload)

    assert required_literal in type(receipt).model_json_schema()["required"]


def test_stale_claimed_use_receipt_fails_after_reissue_or_reexamination() -> None:
    compound = _compound()
    receipt = create_claimed_use_match_receipt(
        analysis_id=_ANALYSIS_ID,
        org_id=_ORG_ID,
        report_id="report-fixture",
        report_fingerprint="b" * 64,
        accused_act_index=0,
        accused_act_sha256="c" * 64,
        patent_id="US1234567B2",
        claim_number=1,
        controlling_claim_text=_CONTROLLING_CLAIM_TEXT,
        current_claim_receipt_sha256=_CURRENT_CLAIM_RECEIPT_SHA256,
        controlling_claim_document_ids=_CONTROLLING_CLAIM_DOCUMENT_IDS,
        target_product_identity="aspirin",
        compound=compound,
        proposed_indication="Secondary prevention of myocardial infarction",
        proposed_label_use="75 mg orally once daily for secondary prevention",
        label_carve_out_state="none",
        issuer_user_id=_ISSUER_USER_ID,
        verified_at=datetime.now(UTC),
        evidence_references=["proposed-label-v7#section-1"],
        attestation_key_id="test-key",
        attestation_key=_KeyRing.key,
    )
    record = AccusedActRecord.model_validate(
        {
            **_record(
                act="regulatory_submission",
                purpose="regulatory_approval",
                regulatory_path="anda",
            ),
            "claimed_use_match_receipts": [receipt.model_dump(mode="json")],
        }
    )
    common = {
        "record": record,
        "claim_category": "method_of_use",
        "jurisdiction": "US",
        "claim_number": 1,
        "compound": compound,
        "receipt_verification_keys": _KeyRing(),
    }

    assert not accused_act_supports_claim_category(
        **common,
        patent_id="US1234567B2",
        controlling_claim_text=_CONTROLLING_CLAIM_TEXT.replace(
            "75 mg",
            "150 mg",
        ),
        current_claim_receipt_sha256="b" * 64,
        controlling_claim_document_ids=["US1234567B2:reexamination-certificate-claims"],
    )
    assert not accused_act_supports_claim_category(
        **common,
        patent_id="US1234567B2",
        controlling_claim_text=_CONTROLLING_CLAIM_TEXT,
        current_claim_receipt_sha256="b" * 64,
        controlling_claim_document_ids=_CONTROLLING_CLAIM_DOCUMENT_IDS,
    )
    assert not accused_act_supports_claim_category(
        **common,
        patent_id="USRE50000E1",
        controlling_claim_text=_CONTROLLING_CLAIM_TEXT,
        current_claim_receipt_sha256=_CURRENT_CLAIM_RECEIPT_SHA256,
        controlling_claim_document_ids=["USRE50000E1:reissue-grant-claims"],
    )


def test_runtime_claimed_use_context_comes_from_current_claim_receipt(
    monkeypatch,
) -> None:
    claims_text = (
        "1. A method of treating a patient comprising administering aspirin.\n"
        "2. The method of claim 1, wherein the dose is 75 mg."
    )
    current_claim_receipt = SimpleNamespace(
        current_claim_text_sha256=hashlib.sha256(claims_text.encode("utf-8")).hexdigest(),
        effective_claim_ids=["1", "2"],
        controlling_claim_document_ids=["US1234567B2:grant-claims"],
        receipt_sha256="a" * 64,
    )
    monkeypatch.setattr(
        "praviar_pipeline.pipeline.runtime.evidence_claims.trusted_claim_text_provenance",
        lambda detail: object(),
    )
    monkeypatch.setattr(
        "praviar_pipeline.pipeline.runtime.evidence_claims._primary_status_receipts",
        lambda detail, **kwargs: {"current_claim_set": current_claim_receipt},
    )

    assert _claimed_use_current_claim_context(
        SimpleNamespace(claims_text=claims_text),
        claim_number=1,
        receipt_verification_keys=_KeyRing(),
    ) == (
        "A method of treating a patient comprising administering aspirin",
        "a" * 64,
        ["US1234567B2:grant-claims"],
    )

    current_claim_receipt.current_claim_text_sha256 = "b" * 64
    assert _claimed_use_current_claim_context(
        SimpleNamespace(claims_text=claims_text),
        claim_number=1,
        receipt_verification_keys=_KeyRing(),
    ) == ("", "", [])


def test_complete_skinny_label_carve_out_cannot_match_claimed_use() -> None:
    compound = _compound()
    receipt = create_claimed_use_match_receipt(
        analysis_id=_ANALYSIS_ID,
        org_id=_ORG_ID,
        report_id="report-fixture",
        report_fingerprint="b" * 64,
        accused_act_index=0,
        accused_act_sha256="c" * 64,
        patent_id="US1234567B2",
        claim_number=1,
        controlling_claim_text=_CONTROLLING_CLAIM_TEXT,
        current_claim_receipt_sha256=_CURRENT_CLAIM_RECEIPT_SHA256,
        controlling_claim_document_ids=_CONTROLLING_CLAIM_DOCUMENT_IDS,
        target_product_identity="aspirin",
        compound=compound,
        proposed_indication="Secondary prevention of myocardial infarction",
        proposed_label_use="Carved-out indication is omitted",
        label_carve_out_state="complete",
        issuer_user_id=_ISSUER_USER_ID,
        verified_at=datetime.now(UTC),
        evidence_references=["proposed-label-v8#carve-out"],
        attestation_key_id="test-key",
        attestation_key=_KeyRing.key,
    )
    record = AccusedActRecord.model_validate(
        {
            **_record(
                act="regulatory_submission",
                purpose="regulatory_approval",
                regulatory_path="anda",
                proposed_label_use="Carved-out indication is omitted",
                label_carve_out_state="complete",
            ),
            "claimed_use_match_receipts": [receipt.model_dump(mode="json")],
        }
    )

    assert not accused_act_supports_claim_category(
        record,
        claim_category="method_of_use",
        jurisdiction="US",
        patent_id="US1234567B2",
        claim_number=1,
        controlling_claim_text=_CONTROLLING_CLAIM_TEXT,
        current_claim_receipt_sha256=_CURRENT_CLAIM_RECEIPT_SHA256,
        controlling_claim_document_ids=_CONTROLLING_CLAIM_DOCUMENT_IDS,
        compound=compound,
        receipt_verification_keys=_KeyRing(),
    )


def test_submission_product_identity_must_match_resolved_small_molecule_or_biologic() -> None:
    mismatched = AccusedActRecord.model_validate(
        _record(
            act="regulatory_submission",
            purpose="regulatory_approval",
            regulatory_path="anda",
            target_product_identity="ibuprofen",
        )
    )
    assert not accused_act_supports_claim_category(
        mismatched,
        claim_category="product",
        jurisdiction="US",
        compound=_compound(),
    )

    biologic = _compound(name="trastuzumab", compound_type="biologic")
    matched_biologic = AccusedActRecord.model_validate(
        _record(
            act="regulatory_submission",
            purpose="regulatory_approval",
            regulatory_path="biosimilar_351_k",
            target_product_identity="trastuzumab",
        )
    )
    assert accused_act_supports_claim_category(
        matched_biologic,
        claim_category="product",
        jurisdiction="US",
        compound=biologic,
    )


def test_runtime_settings_validate_nested_structured_records() -> None:
    settings = Settings(
        product_context={
            "commercial_territories": ["US"],
            "accused_acts": [_record(act="sale")],
        }
    )
    assert settings.product_context["accused_acts"][0]["act"] == "sale"

    with pytest.raises(ValidationError):
        Settings(
            product_context={
                "accused_acts": [
                    _record(
                        act="sale",
                        start_date="2027-01-02",
                        end_date="2027-01-01",
                    )
                ]
            }
        )


def test_one_invalid_record_invalidates_the_entire_untrusted_set() -> None:
    context = {
        "accused_acts": [
            _record(act="sale"),
            {**_record(act="import"), "actor": ""},
        ]
    }

    assert structured_accused_act_records(context) == ()
    assert normalize_accused_acts(None, context) == []


def _record(
    *,
    act: str = "sale",
    jurisdiction: str = "US",
    start_date: str = "2027-01-01",
    end_date: str | None = None,
    actor: str = "Praviar Pharma Ltd",
    status: str = "planned",
    purpose: str = "commercial",
    regulatory_path: str = "none",
    instrumentality: str = "PRV-142 oral tablet",
    liability_theory: str | None = None,
    target_product_identity: str = "aspirin",
    proposed_indication: str = "Secondary prevention of myocardial infarction",
    proposed_label_use: str = "75 mg orally once daily for secondary prevention",
    label_carve_out_state: str = "none",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "act": act,
        "jurisdiction": jurisdiction,
        "start_date": start_date,
        "end_date": end_date,
        "actor": actor,
        "status": status,
        "purpose": purpose,
        "regulatory_path": regulatory_path,
        "instrumentality": instrumentality,
        "liability_theory": liability_theory
        or ("artificial_infringement" if act == "regulatory_submission" else "direct"),
    }
    if act == "regulatory_submission":
        payload.update(
            target_product_identity=target_product_identity,
            proposed_indication=proposed_indication,
            proposed_label_use=proposed_label_use,
            label_carve_out_state=label_carve_out_state,
        )
    return payload


def _compound(
    *,
    name: str = "aspirin",
    compound_type: str = "small_molecule",
) -> ResolvedCompound:
    return ResolvedCompound(
        name=name,
        canonical_smiles="CC(=O)OC1=CC=CC=C1C(=O)O" if name == "aspirin" else "",
        inchi_key="BSYNRYMUTXBXSQ-UHFFFAOYSA-N" if name == "aspirin" else "",
        original_input=name,
        input_type="name",
        compound_type=compound_type,
    )


class _KeyRing:
    key = b"k" * 32

    def verification_key(self, key_id: str) -> bytes:
        if key_id != "test-key":
            raise ValueError("unknown key")
        return self.key
