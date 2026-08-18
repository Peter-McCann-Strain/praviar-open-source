from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from api.workers.task_persistence import upsert_compound_impl


def _compound_payload() -> dict:
    return {
        "canonical_smiles": "CC(=O)Oc1ccccc1C(=O)O",
        "inchi_key": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
        "name": "Aspirin",
        "molecular_formula": "C9H8O4",
        "molecular_weight": 180.16,
        "functional_groups": ["carboxyl", "ester"],
        "pubchem_cid": 2244,
        "compound_type": "small_molecule",
    }


def test_upsert_compound_persists_global_identity_and_org_usage_atomically() -> None:
    db = MagicMock()
    compound_id = uuid.uuid4()
    identity_result = MagicMock()
    identity_result.scalar_one.return_value = compound_id
    db.execute.side_effect = [identity_result, MagicMock()]
    org_id = uuid.uuid4()
    completed_at = datetime(2026, 7, 16, 18, 30, tzinfo=UTC)

    upsert_compound_impl(
        db,
        _compound_payload(),
        org_id=org_id,
        completed_at=completed_at,
    )

    assert db.execute.call_count == 2
    identity_sql = str(db.execute.call_args_list[0].args[0].compile(dialect=postgresql.dialect()))
    usage_sql = str(db.execute.call_args_list[1].args[0].compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (inchi_key) DO UPDATE" in identity_sql
    assert "RETURNING compounds.id" in identity_sql
    assert "INSERT INTO organization_compounds" in usage_sql
    assert "ON CONFLICT (org_id, compound_id) DO UPDATE" in usage_sql
    assert "organization_compounds.analysis_count + " in usage_sql
    assert "display_name" in usage_sql
    assert "least(organization_compounds.first_analyzed_at" in usage_sql

    usage_params = db.execute.call_args_list[1].args[0].compile().params
    assert org_id in usage_params.values()
    assert compound_id in usage_params.values()
    assert completed_at in usage_params.values()
    assert "Aspirin" in usage_params.values()


def test_global_identity_never_persists_cross_tenant_display_name() -> None:
    db = MagicMock()
    identity_result = MagicMock()
    identity_result.scalar_one.return_value = uuid.uuid4()
    db.execute.side_effect = [identity_result, MagicMock()]
    compound = _compound_payload()
    compound["name"] = "Confidential Project Nightingale"

    upsert_compound_impl(
        db,
        compound,
        org_id=uuid.uuid4(),
        completed_at=datetime.now(UTC),
    )

    identity_statement = db.execute.call_args_list[0].args[0]
    identity_sql = str(identity_statement.compile(dialect=postgresql.dialect()))
    identity_params = identity_statement.compile().params
    update_clause = identity_sql.split("DO UPDATE SET", 1)[1]
    assert "name =" in update_clause
    assert "Confidential Project Nightingale" not in identity_params.values()


@pytest.mark.parametrize("compound_type", ["biologic", "peptide"])
def test_upsert_compound_skips_non_indexable_biologic_identity(
    compound_type: str,
) -> None:
    db = MagicMock()
    compound = _compound_payload()
    compound.update(
        {
            "compound_type": compound_type,
            "inchi_key": "",
            "canonical_smiles": "",
        }
    )

    upsert_compound_impl(
        db,
        compound,
        org_id=uuid.uuid4(),
        completed_at=datetime.now(UTC),
    )

    db.execute.assert_not_called()


def test_upsert_compound_links_small_molecule_by_unique_existing_smiles() -> None:
    db = MagicMock()
    compound_id = uuid.uuid4()
    lookup_result = MagicMock()
    lookup_result.scalars.return_value.all.return_value = [compound_id]
    update_result = MagicMock()
    update_result.scalar_one.return_value = compound_id
    db.execute.side_effect = [lookup_result, update_result, MagicMock()]
    compound = _compound_payload()
    compound["inchi_key"] = ""

    upsert_compound_impl(
        db,
        compound,
        org_id=uuid.uuid4(),
        completed_at=datetime.now(UTC),
    )

    assert db.execute.call_count == 3
    lookup_sql = str(db.execute.call_args_list[0].args[0].compile(dialect=postgresql.dialect()))
    update_sql = str(db.execute.call_args_list[1].args[0].compile(dialect=postgresql.dialect()))
    assert "FROM compounds" in lookup_sql
    assert "compounds.canonical_smiles =" in lookup_sql
    assert "LIMIT" in lookup_sql
    assert "UPDATE compounds SET" in update_sql
    assert "analysis_count=(compounds.analysis_count +" in update_sql
    assert "RETURNING compounds.id" in update_sql


def test_upsert_compound_fails_closed_for_ambiguous_small_molecule_smiles() -> None:
    db = MagicMock()
    lookup_result = MagicMock()
    lookup_result.scalars.return_value.all.return_value = [uuid.uuid4(), uuid.uuid4()]
    db.execute.return_value = lookup_result
    compound = _compound_payload()
    compound["inchi_key"] = ""

    with pytest.raises(ValueError, match="ambiguous without inchi_key"):
        upsert_compound_impl(
            db,
            compound,
            org_id=uuid.uuid4(),
            completed_at=datetime.now(UTC),
        )

    assert db.execute.call_count == 1


def test_upsert_compound_fails_closed_for_missing_small_molecule_identity() -> None:
    db = MagicMock()
    compound = _compound_payload()
    compound.update({"inchi_key": "", "canonical_smiles": ""})

    with pytest.raises(ValueError, match="missing global identity fields"):
        upsert_compound_impl(
            db,
            compound,
            org_id=uuid.uuid4(),
            completed_at=datetime.now(UTC),
        )

    db.execute.assert_not_called()


def test_upsert_compound_rejects_malformed_or_unknown_typed_identity() -> None:
    db = MagicMock()
    malformed = _compound_payload()
    malformed["inchi_key"] = "not-an-inchikey"
    with pytest.raises(ValueError, match="invalid inchi_key"):
        upsert_compound_impl(
            db,
            malformed,
            org_id=uuid.uuid4(),
            completed_at=datetime.now(UTC),
        )

    unknown = _compound_payload()
    unknown["compound_type"] = "gene_therapy"
    with pytest.raises(ValueError, match="unsupported completed compound_type"):
        upsert_compound_impl(
            db,
            unknown,
            org_id=uuid.uuid4(),
            completed_at=datetime.now(UTC),
        )

    db.execute.assert_not_called()


def test_upsert_compound_requires_completion_timestamp() -> None:
    db = MagicMock()

    with pytest.raises(ValueError, match="requires completed_at"):
        upsert_compound_impl(
            db,
            _compound_payload(),
            org_id=uuid.uuid4(),
            completed_at=None,  # type: ignore[arg-type]
        )

    db.execute.assert_not_called()
