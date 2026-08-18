from __future__ import annotations

from types import SimpleNamespace
from typing import ClassVar

import pytest

from praviar_pipeline.models.patent import PatentSource
from praviar_pipeline.pipeline.resolution.identity_derivations import (
    derive_prodrug_candidates,
    enumerate_tautomer_candidates,
)
from praviar_pipeline.pipeline.search import primary_sources


class _AsyncContextClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


@pytest.mark.asyncio
async def test_search_surechembl_combines_exact_similarity_and_substructure(
    succinic_acid,
    monkeypatch,
) -> None:
    class FakeSureChEMBLClient(_AsyncContextClient):
        async def search_by_smiles(self, smiles):
            assert smiles == succinic_acid.canonical_smiles
            return [
                {
                    "patents": [
                        {"patent_id": "US100"},
                        {"id": "US101"},
                        {"patent_id": ""},
                    ]
                }
            ]

        async def similarity_search(self, smiles, *, threshold):
            assert smiles == succinic_acid.canonical_smiles
            assert threshold == 0.73
            return [
                {"similarity": 0.82, "patents": [{"patent_id": "US200"}]},
                {"score": "0.76", "patents": [{"id": "US201"}]},
            ]

        async def substructure_search(self, smiles, *, max_results):
            assert smiles == succinic_acid.canonical_smiles
            assert max_results == 25
            return [
                {"patents": [{"patent_id": "US300"}, {"patent_id": "US200"}]},
            ]

    monkeypatch.setattr(primary_sources, "SureChEMBLClient", FakeSureChEMBLClient)
    monkeypatch.setattr(
        primary_sources,
        "get_settings",
        lambda: SimpleNamespace(
            search_tanimoto_threshold=0.73,
            search_surechembl_substructure_enabled=True,
            search_surechembl_max_results=25,
        ),
    )

    primary_sources.clear_surechembl_similarity_cache()
    results = await primary_sources.search_surechembl(succinic_acid)

    assert results == [
        ("US100", PatentSource.SURECHEMBL),
        ("US101", PatentSource.SURECHEMBL),
        ("US200", PatentSource.SURECHEMBL),
        ("US201", PatentSource.SURECHEMBL),
        ("US300", PatentSource.SURECHEMBL),
        ("US200", PatentSource.SURECHEMBL),
    ]
    assert primary_sources.get_surechembl_similarity_metadata("US200") == {
        "tanimoto_score": 0.82,
        "match_type": "similarity",
    }
    assert primary_sources.get_surechembl_similarity_metadata("US201") == {
        "tanimoto_score": 0.76,
        "match_type": "similarity",
    }
    assert primary_sources.get_surechembl_similarity_metadata("US300") == {
        "match_type": "substructure",
    }


@pytest.mark.asyncio
async def test_search_surechembl_includes_only_reviewable_derived_structure_lanes(
    succinic_acid,
    monkeypatch,
) -> None:
    source = "CC(=O)Oc1ccccc1C(=O)O"
    tautomer_record = enumerate_tautomer_candidates(source)
    prodrug_result = derive_prodrug_candidates(source)
    compound = succinic_acid.model_copy(
        update={
            "canonical_smiles": source,
            "free_base_smiles": source,
            "tautomer_enumeration": tautomer_record,
            "prodrug_candidates": prodrug_result.candidates,
        }
    )

    class FakeSureChEMBLClient(_AsyncContextClient):
        calls: ClassVar[list[str]] = []

        async def search_by_smiles(self, smiles):
            self.calls.append(smiles)
            return []

        async def similarity_search(self, smiles, *, threshold):
            return []

        async def substructure_search(self, smiles, *, max_results):
            return []

    monkeypatch.setattr(primary_sources, "SureChEMBLClient", FakeSureChEMBLClient)
    monkeypatch.setattr(
        primary_sources,
        "get_settings",
        lambda: SimpleNamespace(
            search_tanimoto_threshold=0.73,
            search_surechembl_substructure_enabled=False,
            search_surechembl_max_results=25,
        ),
    )

    await primary_sources.search_surechembl(compound)

    assert FakeSureChEMBLClient.calls[0] == source
    assert "O=C(O)c1ccccc1O" in FakeSureChEMBLClient.calls
    assert all(
        candidate.canonical_smiles in FakeSureChEMBLClient.calls
        for candidate in tautomer_record.candidates
        if candidate.search_eligible
    )
    assert len(FakeSureChEMBLClient.calls) == len(set(FakeSureChEMBLClient.calls))


@pytest.mark.asyncio
async def test_search_pubchem_similar_skips_self_and_continues_after_link_error(
    succinic_acid,
    monkeypatch,
) -> None:
    class FakePubChemClient(_AsyncContextClient):
        async def similarity_search(self, smiles, *, threshold, max_records):
            assert smiles == succinic_acid.canonical_smiles
            assert threshold == 0.6
            assert max_records == 20
            return [
                {"CID": succinic_acid.pubchem_cid},
                {"CID": 222},
                {"CID": 333},
                {},
            ]

        async def get_patent_links(self, cid):
            if cid == 333:
                raise RuntimeError("pubchem link service down")
            return [f"US{cid}", f"US{cid + 1}"]

    monkeypatch.setattr(primary_sources, "PubChemClient", FakePubChemClient)
    monkeypatch.setattr(
        primary_sources,
        "get_settings",
        lambda: SimpleNamespace(search_tanimoto_threshold=0.6),
    )

    results = await primary_sources.search_pubchem_similar(succinic_acid)

    assert results == [
        ("US222", PatentSource.PUBCHEM),
        ("US223", PatentSource.PUBCHEM),
    ]


@pytest.mark.asyncio
async def test_search_bigquery_uses_limited_terms_and_jurisdictions(
    succinic_acid,
    monkeypatch,
) -> None:
    class FakeBigQueryClient(_AsyncContextClient):
        instances: ClassVar[list[FakeBigQueryClient]] = []

        def __init__(self) -> None:
            self.calls = []
            self.instances.append(self)

        async def search_patents_by_compound(self, search_terms, *, jurisdictions):
            self.calls.append((search_terms, jurisdictions))
            return [{"publication_number": "US100"}]

    monkeypatch.setattr(primary_sources, "BigQueryClient", FakeBigQueryClient)
    monkeypatch.setattr(
        primary_sources,
        "get_settings",
        lambda: SimpleNamespace(
            search_max_synonyms_bigquery=1,
            search_max_cas_bigquery=1,
            search_allowed_jurisdictions=["US", "EP"],
        ),
    )

    rows = await primary_sources.search_bigquery(succinic_acid)

    assert rows == [{"publication_number": "US100"}]
    assert FakeBigQueryClient.instances[0].calls == [
        (
            ["succinic acid", "butanedioic acid", "110-15-6"],
            ["US", "EP"],
        )
    ]


@pytest.mark.asyncio
async def test_search_bigquery_annotations_filters_blank_publications(
    succinic_acid,
    monkeypatch,
) -> None:
    class FakeBigQueryClient(_AsyncContextClient):
        async def search_compound_annotations(self, *, name, inchikey, max_results):
            assert name == succinic_acid.name
            assert inchikey == succinic_acid.inchi_key
            assert max_results == 50
            return [
                {"publication_number": "US100"},
                {"publication_number": ""},
                {},
            ]

    monkeypatch.setattr(primary_sources, "BigQueryClient", FakeBigQueryClient)
    monkeypatch.setattr(
        primary_sources,
        "get_settings",
        lambda: SimpleNamespace(search_bigquery_max_results=50),
    )

    results = await primary_sources.search_bigquery_annotations(succinic_acid)

    assert results == [("US100", PatentSource.BIGQUERY)]


@pytest.mark.asyncio
async def test_search_patcid_includes_prefix_matches_and_skips_missing_ids(
    succinic_acid,
    monkeypatch,
) -> None:
    class FakePatCIDClient(_AsyncContextClient):
        async def lookup_by_inchikey(self, inchikey):
            assert inchikey == succinic_acid.inchi_key
            return ["US100"]

        async def lookup_by_inchikey_prefix(self, prefix):
            assert prefix == "KDYFGRWQOYBRFD"
            return [
                {"inchikey": succinic_acid.inchi_key, "patent_id": "USSELF"},
                {"inchikey": "OTHER-UHFFFAOYSA-N", "patent_id": "US200"},
                {"inchikey": "MISSING-UHFFFAOYSA-N", "patent_id": ""},
            ]

    monkeypatch.setattr(primary_sources, "PatCIDClient", FakePatCIDClient)

    results = await primary_sources.search_patcid(succinic_acid)

    assert results == [
        ("US100", PatentSource.PATCID),
        ("US200", PatentSource.PATCID),
    ]
