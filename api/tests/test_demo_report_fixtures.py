import re
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from certification_keyring_fixtures import (
    TEST_REPORT_CERTIFICATION_PUBLIC_KEYRING,
    TEST_REPORT_CERTIFICATION_SIGNING_KEYRING_SECRET,
)
from praviar_pipeline.models.report_document import FTOReport
from praviar_pipeline.report_certification_binding import (
    ReportCertificationSigner,
    sign_report_certification_binding,
)
from praviar_pipeline.showcase_fixture import showcase_fixture_receipt

from api.fixtures.demo_reports import (
    aspirin_report,
    showcase_report,
    sofosbuvir_report,
    succinic_acid_report,
)
from api.services.report_access import validate_report_publishability
from api.services.reports import build_blocker_family_contract_blockers
from api.workers.task_exports import _validate_export_report_payload

ANALYSIS_ID = "00000000-0000-0000-0000-000000000001"
ORG_ID = "00000000-0000-0000-0000-000000000002"


def _settings(app_env: str) -> SimpleNamespace:
    return SimpleNamespace(
        app_env=app_env,
        report_certification_public_keyring=TEST_REPORT_CERTIFICATION_PUBLIC_KEYRING,
    )


def _validate(report: dict) -> dict:
    report["report_certification_binding"] = sign_report_certification_binding(
        report,
        signer=ReportCertificationSigner.from_secret(
            TEST_REPORT_CERTIFICATION_SIGNING_KEYRING_SECRET
        ),
        analysis_id=ANALYSIS_ID,
        org_id=ORG_ID,
    )
    return validate_report_publishability(
        report,
        analysis_id=ANALYSIS_ID,
        org_id=ORG_ID,
    )


@pytest.mark.parametrize(
    ("fixture", "expected_decision"),
    [
        (showcase_report, "unclear"),
        (aspirin_report, "unclear"),
        (sofosbuvir_report, "blocked"),
    ],
)
def test_publishable_dev_seed_reports_are_explicitly_synthetic(
    fixture,
    expected_decision,
):
    report = fixture()

    with patch(
        "api.services.report_access.get_settings",
        return_value=_settings("dev"),
    ):
        summary = _validate(report)

    assert summary["decision"] == expected_decision
    provenance = next(iter(report["patent_details"].values()))["claims_text_provenance"]
    assert provenance["source"] == "synthetic_fixture"
    assert provenance["collector_identity"] == "dev.synthetic_fixture"
    assert provenance["artifact_locator"].startswith("praviar-demo://")


def test_synthetic_report_provenance_is_rejected_outside_development():
    with (
        patch(
            "api.services.report_access.get_settings",
            return_value=_settings("prod"),
        ),
        pytest.raises(
            ValueError,
            match="synthetic claim provenance is only publishable in development",
        ),
    ):
        _validate(showcase_report())


def test_incorrect_demo_report_still_fails_closed_in_development():
    with (
        patch(
            "api.services.report_access.get_settings",
            return_value=_settings("dev"),
        ),
        pytest.raises(ValueError, match="claims_incorrect must be 0"),
    ):
        _validate(succinic_acid_report())


@pytest.mark.parametrize(
    "fixture",
    [showcase_report, aspirin_report, sofosbuvir_report, succinic_acid_report],
)
def test_dev_seed_reports_revalidate_through_real_export_contract(fixture):
    validated = _validate_export_report_payload(fixture())

    assert validated.patent_analyses


@pytest.mark.parametrize("fixture", [sofosbuvir_report, succinic_acid_report])
def test_blocked_demo_reports_use_canonical_production_blocker_families(fixture):
    report = fixture()
    audit = report["clearance_decision"]["decision_audit"]
    summary = audit["claim_program_summary"]

    assert build_blocker_family_contract_blockers(report) == []
    assert sorted(
        patent_id
        for family in audit["blocker_families"]
        for patent_id in family["blocking_patent_ids"]
    ) == sorted(summary["blocking_patent_ids"])
    assert sorted(
        claim["claim_id"]
        for family in audit["blocker_families"]
        for claim in family["blocking_claims"]
    ) == sorted(summary["blocking_claim_ids"])
    assert report["matter_store"]["matter_evidence_index"] == report["matter_evidence_index"]


def test_showcase_report_is_a_deterministic_projection_of_canonical_receipt():
    generated_at = datetime(2026, 8, 11, tzinfo=UTC)

    first = showcase_report(generated_at=generated_at)
    second = showcase_report(generated_at=generated_at)
    receipt = showcase_fixture_receipt()

    assert first == second
    assert FTOReport.model_validate(first)
    assert first["compound"]["name"] == "Example Molecule Alpha"
    assert first["routing_profile"]["fixture_digest"] == receipt["fixture_digest"]
    assert first["claim_source_span_map"]["generated_from"] == receipt["fixture_id"]
    assert first["record_completeness"]["clearance_grade_ready"] is False
    assert first["total_input_tokens"] == 0
    assert first["estimated_cost_usd"] == 0


def test_showcase_report_contains_no_legacy_fixture_values():
    report = showcase_report(generated_at=datetime(2026, 8, 11, tzinfo=UTC))
    string_values: list[str] = []

    def collect(value) -> None:
        if isinstance(value, dict):
            for nested in value.values():
                collect(nested)
        elif isinstance(value, list):
            for nested in value:
                collect(nested)
        elif isinstance(value, str):
            string_values.append(value.lower())

    collect(report)
    serialized_values = "\n".join(string_values)
    for forbidden in (
        "aspirin",
        "acetylsalicylic",
        "sofosbuvir",
        "succinic acid",
        "us6977252",
        "novachem",
        "50-78-2",
    ):
        assert forbidden not in serialized_values


@pytest.mark.parametrize(
    "fixture",
    [aspirin_report, sofosbuvir_report, succinic_acid_report],
)
def test_legacy_component_reports_are_explicitly_synthetic(fixture):
    report = fixture()
    string_values: list[str] = []

    def collect(value) -> None:
        if isinstance(value, dict):
            for nested in value.values():
                collect(nested)
        elif isinstance(value, list):
            for nested in value:
                collect(nested)
        elif isinstance(value, str):
            string_values.append(value)

    collect(report)
    serialized_values = "\n".join(string_values)
    normalized = serialized_values.casefold()

    assert report["disclaimer"].startswith("SYNTHETIC COMPONENT-TEST FIXTURE:")
    assert "not the canonical showcase" in normalized
    assert "not release evidence" in normalized

    publication_ids = re.findall(
        r"\b(US|WO|EP)([0-9]{6,14})[A-Z][0-9]?\b",
        serialized_values,
    )
    assert publication_ids
    assert all(
        digits.startswith("1978000") if jurisdiction == "WO" else digits.startswith("000000")
        for jurisdiction, digits in publication_ids
    )

    proceedings = re.findall(r"\bIPR([0-9]{4})-[0-9]{5}\b", serialized_values)
    assert all(year == "0000" for year in proceedings)

    for forbidden in (
        "pfizer",
        "basf",
        "novozymes",
        "gilead",
        "bayer",
        "dsm ip assets",
        "roquette",
        "bioamber",
        "myriant",
        "reverdia",
        "succinity",
        "published ground truth",
        "published ground-truth",
        "real patent ids",
        "doi.org/",
        "patents.google.com/",
    ):
        assert forbidden not in normalized
