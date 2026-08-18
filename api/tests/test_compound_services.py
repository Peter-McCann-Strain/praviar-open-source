"""Tests for api.services.compounds."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import (
    bind_report_data,
    make_compound_mock,
    valid_report_data,
    valid_report_data_for_patents,
)
from pydantic import ValidationError

from api.errors import APIError
from api.schemas.compounds import CompoundResponse
from api.services.compounds import (
    compare_compounds_for_org,
    escape_like_pattern,
    org_compound_query,
)


def _report_with_patents(
    patent_ids: list[str],
    *,
    inchi_key: str = "",
) -> dict:
    report = valid_report_data_for_patents([{"patent_id": patent_id} for patent_id in patent_ids])
    report["compound"]["inchi_key"] = inchi_key
    return report


def _compound_row(
    compound,
    *,
    display_name: str | None = None,
    analysis_count: int = 1,
):
    return (
        compound,
        display_name if display_name is not None else compound.name,
        datetime(2026, 7, 1, tzinfo=UTC),
        analysis_count,
    )


def _analysis_row(
    analysis_id: uuid.UUID,
    compound_smiles: str,
    report: dict,
    *,
    org_id: uuid.UUID,
) -> tuple[uuid.UUID, str, dict]:
    """Return a report row certified for the exact queried tenant and analysis."""
    return (
        analysis_id,
        compound_smiles,
        bind_report_data(report, analysis_id=analysis_id, org_id=org_id),
    )


def test_escape_like_pattern_treats_compound_search_as_literal_text():
    assert escape_like_pattern(r"C%C_N\salt") == r"C\%C\_N\\salt"


def test_org_compound_query_selects_local_usage_without_global_counters():
    query = org_compound_query(uuid.uuid4())
    rendered = str(query)

    assert "organization_compounds" in rendered
    assert "organization_compounds.org_id =" in rendered
    assert "organization_compounds.display_name" in rendered
    assert "organization_compounds.first_analyzed_at" in rendered
    assert "organization_compounds.analysis_count" in rendered
    assert ", compounds.name" not in rendered
    assert ", compounds.first_analyzed_at" not in rendered
    assert ", compounds.analysis_count" not in rendered


def test_compound_response_rejects_bare_global_orm_shape() -> None:
    with pytest.raises(ValidationError):
        CompoundResponse.model_validate(
            SimpleNamespace(
                id=uuid.uuid4(),
                canonical_smiles="CCO",
                inchi_key="LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
                name="Ethanol",
                molecular_formula="C2H6O",
                molecular_weight=46.07,
                functional_groups=["alcohol"],
                pubchem_cid=702,
                first_analyzed_at=datetime(2020, 1, 1, tzinfo=UTC),
                analysis_count=999,
            )
        )


class TestCompareCompoundsForOrg:
    @pytest.mark.asyncio
    async def test_compare_excludes_revoked_report_with_exact_owner_context(self):
        db = AsyncMock()
        org_id = uuid.uuid4()
        compound_id = uuid.uuid4()
        analysis_id = uuid.uuid4()
        compound = make_compound_mock(
            id=compound_id,
            canonical_smiles="AAA",
            name="A",
        )
        report = _report_with_patents(["US91000020A1"])
        compound_result = MagicMock()
        compound_result.all.return_value = [_compound_row(compound)]
        analysis_rows_result = MagicMock()
        analysis_rows_result.all.return_value = [
            _analysis_row(analysis_id, "AAA", report, org_id=org_id)
        ]
        db.execute = AsyncMock(side_effect=[compound_result, analysis_rows_result])

        with patch(
            "api.services.compounds.validate_report_publishability",
            side_effect=ValueError("certification_release_receipt_revoked"),
        ) as validate:
            result = await compare_compounds_for_org(
                db,
                org_id,
                [compound_id],
            )

        assert result["overlapping_patents"] == []
        validate.assert_called_once_with(
            report,
            analysis_id=str(analysis_id),
            org_id=str(org_id),
        )

    @pytest.mark.asyncio
    async def test_compare_uses_latest_report_per_smiles_and_preserves_request_order(self):
        db = AsyncMock()
        org_id = uuid.uuid4()
        id1, id2 = uuid.uuid4(), uuid.uuid4()
        compound_b = make_compound_mock(id=id2, canonical_smiles="BBB", name="B")
        compound_a = make_compound_mock(id=id1, canonical_smiles="AAA", name="A")

        compound_result = MagicMock()
        compound_result.all.return_value = [
            _compound_row(compound_b, analysis_count=3),
            _compound_row(compound_a, analysis_count=2),
        ]

        analysis_rows_result = MagicMock()
        analysis_rows_result.all.return_value = [
            _analysis_row(
                id1,
                "AAA",
                _report_with_patents(["US91000020A1"]),
                org_id=org_id,
            ),
            _analysis_row(
                id1,
                "AAA",
                _report_with_patents(["US91000003A1"]),
                org_id=org_id,
            ),
            _analysis_row(
                id2,
                "BBB",
                _report_with_patents(["US91000020A1", "US91000019A1"]),
                org_id=org_id,
            ),
        ]
        db.execute = AsyncMock(side_effect=[compound_result, analysis_rows_result])

        result = await compare_compounds_for_org(db, org_id, [id1, id2])

        assert [compound.id for compound in result["compounds"]] == [id1, id2]
        assert [compound.analysis_count for compound in result["compounds"]] == [2, 3]
        assert result["overlapping_patents"] == [{"patent_id": "US91000020A1", "compound_count": 2}]
        analysis_query = str(db.execute.await_args_list[1].args[0])
        assert "analyses.status" in analysis_query
        assert "jsonb_typeof(analyses.report_data)" in analysis_query
        assert "analyses.report_data !=" in analysis_query
        assert "ORDER BY analyses.completed_at DESC, analyses.id DESC" in analysis_query
        assert "row_number()" not in analysis_query
        assert "rn =" not in analysis_query

    @pytest.mark.asyncio
    async def test_compare_skips_latest_report_without_source_span_provenance(self):
        db = AsyncMock()
        org_id = uuid.uuid4()
        id1, id2 = uuid.uuid4(), uuid.uuid4()
        compound_a = make_compound_mock(id=id1, canonical_smiles="AAA", name="A")
        compound_b = make_compound_mock(id=id2, canonical_smiles="BBB", name="B")

        compound_result = MagicMock()
        compound_result.all.return_value = [
            _compound_row(compound_a),
            _compound_row(compound_b),
        ]

        latest_legacy_report = valid_report_data(
            patent_analyses=[{"patent_id": "US91000002A1"}],
        )
        latest_legacy_report.pop("claim_source_span_map")
        analysis_rows_result = MagicMock()
        analysis_rows_result.all.return_value = [
            _analysis_row(id1, "AAA", latest_legacy_report, org_id=org_id),
            _analysis_row(
                id1,
                "AAA",
                _report_with_patents(["US91000016A1"]),
                org_id=org_id,
            ),
            _analysis_row(
                id2,
                "BBB",
                _report_with_patents(["US91000016A1"]),
                org_id=org_id,
            ),
        ]
        db.execute = AsyncMock(side_effect=[compound_result, analysis_rows_result])

        result = await compare_compounds_for_org(db, org_id, [id1, id2])

        assert result["overlapping_patents"] == [{"patent_id": "US91000016A1", "compound_count": 2}]

    @pytest.mark.asyncio
    async def test_compare_skips_latest_report_that_fails_publishability(self):
        db = AsyncMock()
        org_id = uuid.uuid4()
        id1, id2 = uuid.uuid4(), uuid.uuid4()
        compound_a = make_compound_mock(id=id1, canonical_smiles="AAA", name="A")
        compound_b = make_compound_mock(id=id2, canonical_smiles="BBB", name="B")

        compound_result = MagicMock()
        compound_result.all.return_value = [
            _compound_row(compound_a),
            _compound_row(compound_b),
        ]

        failed_verification_report = _report_with_patents(["US91000001A1"])
        failed_verification_report["verification_summary"]["claims_incorrect"] = 1
        analysis_rows_result = MagicMock()
        analysis_rows_result.all.return_value = [
            _analysis_row(id1, "AAA", failed_verification_report, org_id=org_id),
            _analysis_row(
                id1,
                "AAA",
                _report_with_patents(["US91000016A1"]),
                org_id=org_id,
            ),
            _analysis_row(
                id2,
                "BBB",
                _report_with_patents(["US91000016A1"]),
                org_id=org_id,
            ),
        ]
        db.execute = AsyncMock(side_effect=[compound_result, analysis_rows_result])

        result = await compare_compounds_for_org(db, org_id, [id1, id2])

        assert result["overlapping_patents"] == [{"patent_id": "US91000016A1", "compound_count": 2}]

    @pytest.mark.asyncio
    async def test_compare_skips_report_when_patent_ids_are_missing_from_source_span_map(self):
        db = AsyncMock()
        org_id = uuid.uuid4()
        id1, id2 = uuid.uuid4(), uuid.uuid4()
        compound_a = make_compound_mock(id=id1, canonical_smiles="AAA", name="A")
        compound_b = make_compound_mock(id=id2, canonical_smiles="BBB", name="B")

        compound_result = MagicMock()
        compound_result.all.return_value = [
            _compound_row(compound_a),
            _compound_row(compound_b),
        ]

        mismatched_report = _report_with_patents(["US91000016A1"])
        mismatched_report["patent_analyses"] = [{"patent_id": "US91000004A1"}]
        analysis_rows_result = MagicMock()
        analysis_rows_result.all.return_value = [
            _analysis_row(id1, "AAA", mismatched_report, org_id=org_id),
            _analysis_row(
                id1,
                "AAA",
                _report_with_patents(["US91000016A1"]),
                org_id=org_id,
            ),
            _analysis_row(
                id2,
                "BBB",
                _report_with_patents(["US91000016A1"]),
                org_id=org_id,
            ),
        ]
        db.execute = AsyncMock(side_effect=[compound_result, analysis_rows_result])

        result = await compare_compounds_for_org(db, org_id, [id1, id2])

        assert result["overlapping_patents"] == [{"patent_id": "US91000016A1", "compound_count": 2}]

    @pytest.mark.asyncio
    async def test_compare_skips_malformed_patent_analyses_before_marking_smiles_handled(self):
        db = AsyncMock()
        org_id = uuid.uuid4()
        id1, id2 = uuid.uuid4(), uuid.uuid4()
        compound_a = make_compound_mock(id=id1, canonical_smiles="AAA", name="A")
        compound_b = make_compound_mock(id=id2, canonical_smiles="BBB", name="B")

        compound_result = MagicMock()
        compound_result.all.return_value = [
            _compound_row(compound_a),
            _compound_row(compound_b),
        ]

        malformed_report = _report_with_patents(["US91000003A1"])
        malformed_report["patent_analyses"] = {"not": "an array"}
        analysis_rows_result = MagicMock()
        analysis_rows_result.all.return_value = [
            _analysis_row(id1, "AAA", malformed_report, org_id=org_id),
            _analysis_row(
                id1,
                "AAA",
                _report_with_patents(["US91000016A1"]),
                org_id=org_id,
            ),
            _analysis_row(
                id2,
                "BBB",
                _report_with_patents(["US91000016A1"]),
                org_id=org_id,
            ),
        ]
        db.execute = AsyncMock(side_effect=[compound_result, analysis_rows_result])

        result = await compare_compounds_for_org(db, org_id, [id1, id2])

        assert result["overlapping_patents"] == [{"patent_id": "US91000016A1", "compound_count": 2}]

    @pytest.mark.asyncio
    async def test_compare_skips_needs_review_patent_without_supported_source_span(self):
        db = AsyncMock()
        org_id = uuid.uuid4()
        id1, id2 = uuid.uuid4(), uuid.uuid4()
        compound_a = make_compound_mock(id=id1, canonical_smiles="AAA", name="A")
        compound_b = make_compound_mock(id=id2, canonical_smiles="BBB", name="B")

        compound_result = MagicMock()
        compound_result.all.return_value = [
            _compound_row(compound_a),
            _compound_row(compound_b),
        ]

        needs_review_report = _report_with_patents(["US91000014A1"])
        needs_review_report["claim_source_span_map"]["entries"][0]["support_status"] = (
            "needs_review"
        )
        needs_review_report["claim_source_span_map"]["entries"][0]["source_span_ids"] = []
        analysis_rows_result = MagicMock()
        analysis_rows_result.all.return_value = [
            _analysis_row(id1, "AAA", needs_review_report, org_id=org_id),
            _analysis_row(
                id1,
                "AAA",
                _report_with_patents(["US91000016A1"]),
                org_id=org_id,
            ),
            _analysis_row(
                id2,
                "BBB",
                _report_with_patents(["US91000016A1"]),
                org_id=org_id,
            ),
        ]
        db.execute = AsyncMock(side_effect=[compound_result, analysis_rows_result])

        result = await compare_compounds_for_org(db, org_id, [id1, id2])

        assert result["overlapping_patents"] == [{"patent_id": "US91000016A1", "compound_count": 2}]

    @pytest.mark.asyncio
    async def test_compare_skips_patent_with_only_stray_unreferenced_span(self):
        db = AsyncMock()
        org_id = uuid.uuid4()
        id1, id2 = uuid.uuid4(), uuid.uuid4()
        compound_a = make_compound_mock(id=id1, canonical_smiles="AAA", name="A")
        compound_b = make_compound_mock(id=id2, canonical_smiles="BBB", name="B")

        compound_result = MagicMock()
        compound_result.all.return_value = [
            _compound_row(compound_a),
            _compound_row(compound_b),
        ]

        stray_span_report = _report_with_patents(["US91000012A1"])
        stray_span_report["claim_source_span_map"]["entries"] = []
        analysis_rows_result = MagicMock()
        analysis_rows_result.all.return_value = [
            _analysis_row(id1, "AAA", stray_span_report, org_id=org_id),
            _analysis_row(
                id1,
                "AAA",
                _report_with_patents(["US91000016A1"]),
                org_id=org_id,
            ),
            _analysis_row(
                id2,
                "BBB",
                _report_with_patents(["US91000016A1"]),
                org_id=org_id,
            ),
        ]
        db.execute = AsyncMock(side_effect=[compound_result, analysis_rows_result])

        result = await compare_compounds_for_org(db, org_id, [id1, id2])

        assert result["overlapping_patents"] == [{"patent_id": "US91000016A1", "compound_count": 2}]

    @pytest.mark.asyncio
    async def test_compare_resolves_blank_smiles_compounds_by_report_inchi_key(self):
        db = AsyncMock()
        org_id = uuid.uuid4()
        id1, id2 = uuid.uuid4(), uuid.uuid4()
        inchi1 = "AAAAAAAAAAAAAA-BBBBBBBBBB-C"
        inchi2 = "DDDDDDDDDDDDDD-EEEEEEEEEE-F"
        compound_a = make_compound_mock(
            id=id1,
            canonical_smiles="",
            inchi_key=inchi1,
            name="Biologic A",
        )
        compound_b = make_compound_mock(
            id=id2,
            canonical_smiles="",
            inchi_key=inchi2,
            name="Peptide B",
        )

        compound_result = MagicMock()
        compound_result.all.return_value = [
            _compound_row(compound_a),
            _compound_row(compound_b),
        ]
        analysis_rows_result = MagicMock()
        analysis_1_id, analysis_2_id = uuid.uuid4(), uuid.uuid4()
        analysis_rows_result.all.return_value = [
            _analysis_row(
                analysis_1_id,
                "",
                _report_with_patents(["US91000020A1"], inchi_key=inchi1),
                org_id=org_id,
            ),
            _analysis_row(
                analysis_2_id,
                "",
                _report_with_patents(["US91000020A1"], inchi_key=inchi2),
                org_id=org_id,
            ),
        ]
        db.execute = AsyncMock(side_effect=[compound_result, analysis_rows_result])

        result = await compare_compounds_for_org(db, org_id, [id1, id2])

        assert result["overlapping_patents"] == [{"patent_id": "US91000020A1", "compound_count": 2}]
        analysis_query = str(db.execute.await_args_list[1].args[0])
        assert "analyses.report_data #>>" in analysis_query

    @pytest.mark.asyncio
    async def test_compare_does_not_guess_between_duplicate_smiles_without_inchi(self):
        db = AsyncMock()
        org_id = uuid.uuid4()
        id1, id2 = uuid.uuid4(), uuid.uuid4()
        compound_result = MagicMock()
        compound_result.all.return_value = [
            _compound_row(
                make_compound_mock(
                    id=id1,
                    canonical_smiles="DUPLICATE",
                    inchi_key="AAAAAAAAAAAAAA-BBBBBBBBBB-C",
                )
            ),
            _compound_row(
                make_compound_mock(
                    id=id2,
                    canonical_smiles="DUPLICATE",
                    inchi_key="DDDDDDDDDDDDDD-EEEEEEEEEE-F",
                )
            ),
        ]
        analysis_rows_result = MagicMock()
        analysis_id = uuid.uuid4()
        analysis_rows_result.all.return_value = [
            _analysis_row(
                analysis_id,
                "DUPLICATE",
                _report_with_patents(["US91000020A1"]),
                org_id=org_id,
            )
        ]
        db.execute = AsyncMock(side_effect=[compound_result, analysis_rows_result])

        result = await compare_compounds_for_org(db, org_id, [id1, id2])

        assert result["overlapping_patents"] == []

    @pytest.mark.asyncio
    async def test_compare_raises_when_requested_compound_missing(self):
        db = AsyncMock()
        org_id = uuid.uuid4()
        id1, id2 = uuid.uuid4(), uuid.uuid4()

        compound_result = MagicMock()
        compound_result.all.return_value = [_compound_row(make_compound_mock(id=id1))]
        db.execute = AsyncMock(return_value=compound_result)

        with pytest.raises(APIError, match="One or more compounds not found"):
            await compare_compounds_for_org(db, org_id, [id1, id2])
