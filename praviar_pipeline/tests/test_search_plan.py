from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.models.search import ExpandedSearchQueries
from praviar_pipeline.pipeline.search.plan import build_search_plan


def test_build_search_plan_excludes_expanded_sources_when_disabled(succinic_acid):
    empty_expansion = ExpandedSearchQueries()
    plan = build_search_plan(
        compound=succinic_acid,
        expanded_queries=empty_expansion,
        has_expansion=False,
        settings=SimpleNamespace(
            search_enable_pubchem=True,
            search_enable_surechembl=True,
            search_enable_bigquery=True,
            search_enable_patcid=True,
            search_allowed_jurisdictions=["US", "EP", "WO", "KR", "JP"],
            ops_consumer_key="ops-key",
            ops_consumer_secret="ops-secret",
            kipris_api_key="kipris-key",
            patentscope_username="wipo-user",
            patentscope_password="wipo-pass",
            patentsview_api_key="pv-key",
        ),
        search_pubchem_sdq=lambda compound: ("pubchem_sdq", compound.name),
        search_surechembl=lambda compound: ("surechembl", compound.name),
        search_bigquery=lambda compound: ("bigquery", compound.name),
        search_bigquery_annotations=lambda compound: ("bigquery_annotations", compound.name),
        search_patcid=lambda compound: ("patcid", compound.name),
        search_pubchem_similar=lambda compound: ("pubchem_similar", compound.name),
        search_bigquery_cpc=lambda compound, expanded: ("cpc_search", compound.name, expanded),
        search_bigquery_assignee=lambda compound, expanded: (
            "assignee_search",
            compound.name,
            expanded,
        ),
        search_epo_claims=lambda compound, expanded: ("epo_search", compound.name, expanded),
        search_kipris=lambda compound: ("kipris", compound.name),
        search_patentscope=lambda compound: ("patentscope", compound.name),
        search_bigquery_translated=lambda compound: ("bigquery_translated", compound.name),
        search_patentsview=lambda compound: ("patentsview", compound.name),
    )

    names = [name for name, _coro in plan]

    assert "cpc_search" not in names
    assert "assignee_search" not in names
    assert "epo_search" not in names
    assert names[:6] == [
        "pubchem_sdq",
        "surechembl",
        "bigquery",
        "bigquery_annotations",
        "patcid",
        "pubchem_similar",
    ]


def test_build_search_plan_includes_expanded_sources_when_enabled(succinic_acid):
    empty_expansion = ExpandedSearchQueries()
    plan = build_search_plan(
        compound=succinic_acid,
        expanded_queries=empty_expansion,
        has_expansion=True,
        settings=SimpleNamespace(
            search_enable_pubchem=True,
            search_enable_surechembl=True,
            search_enable_bigquery=True,
            search_enable_patcid=True,
            search_allowed_jurisdictions=["US", "EP", "WO", "KR", "JP"],
            ops_consumer_key="ops-key",
            ops_consumer_secret="ops-secret",
            kipris_api_key="kipris-key",
            patentscope_username="wipo-user",
            patentscope_password="wipo-pass",
            patentsview_api_key="pv-key",
        ),
        search_pubchem_sdq=lambda compound: ("pubchem_sdq", compound.name),
        search_surechembl=lambda compound: ("surechembl", compound.name),
        search_bigquery=lambda compound: ("bigquery", compound.name),
        search_bigquery_annotations=lambda compound: ("bigquery_annotations", compound.name),
        search_patcid=lambda compound: ("patcid", compound.name),
        search_pubchem_similar=lambda compound: ("pubchem_similar", compound.name),
        search_bigquery_cpc=lambda compound, expanded: ("cpc_search", compound.name, expanded),
        search_bigquery_assignee=lambda compound, expanded: (
            "assignee_search",
            compound.name,
            expanded,
        ),
        search_epo_claims=lambda compound, expanded: ("epo_search", compound.name, expanded),
        search_kipris=lambda compound: ("kipris", compound.name),
        search_patentscope=lambda compound: ("patentscope", compound.name),
        search_bigquery_translated=lambda compound: ("bigquery_translated", compound.name),
        search_patentsview=lambda compound: ("patentsview", compound.name),
    )

    names = [name for name, _coro in plan]

    assert names[6:9] == ["cpc_search", "assignee_search", "epo_search"]
    assert "lens" not in names
    assert names[-4:] == [
        "kipris",
        "patentscope",
        "bigquery_translated",
        "patentsview",
    ]


def test_build_search_plan_disables_bigquery_family_of_sources(succinic_acid):
    empty_expansion = ExpandedSearchQueries()
    plan = build_search_plan(
        compound=succinic_acid,
        expanded_queries=empty_expansion,
        has_expansion=True,
        settings=SimpleNamespace(
            search_enable_pubchem=True,
            search_enable_surechembl=True,
            search_enable_bigquery=False,
            search_enable_patcid=True,
            ops_consumer_key="ops-key",
            ops_consumer_secret="ops-secret",
        ),
        search_pubchem_sdq=lambda compound: ("pubchem_sdq", compound.name),
        search_surechembl=lambda compound: ("surechembl", compound.name),
        search_bigquery=lambda compound: ("bigquery", compound.name),
        search_bigquery_annotations=lambda compound: ("bigquery_annotations", compound.name),
        search_patcid=lambda compound: ("patcid", compound.name),
        search_pubchem_similar=lambda compound: ("pubchem_similar", compound.name),
        search_bigquery_cpc=lambda compound, expanded: ("cpc_search", compound.name, expanded),
        search_bigquery_assignee=lambda compound, expanded: (
            "assignee_search",
            compound.name,
            expanded,
        ),
        search_epo_claims=lambda compound, expanded: ("epo_search", compound.name, expanded),
        search_kipris=lambda compound: ("kipris", compound.name),
        search_patentscope=lambda compound: ("patentscope", compound.name),
        search_bigquery_translated=lambda compound: ("bigquery_translated", compound.name),
        search_patentsview=lambda compound: ("patentsview", compound.name),
    )

    names = [name for name, _coro in plan]

    assert "bigquery" not in names
    assert "bigquery_annotations" not in names
    assert "cpc_search" not in names
    assert "assignee_search" not in names
    assert "bigquery_translated" not in names
    assert "epo_search" in names


def test_build_search_plan_disables_pubchem_sources(succinic_acid):
    empty_expansion = ExpandedSearchQueries()
    plan = build_search_plan(
        compound=succinic_acid,
        expanded_queries=empty_expansion,
        has_expansion=False,
        settings=SimpleNamespace(
            search_enable_pubchem=False,
            search_enable_surechembl=True,
            search_enable_bigquery=True,
            search_enable_patcid=True,
        ),
        search_pubchem_sdq=lambda compound: ("pubchem_sdq", compound.name),
        search_surechembl=lambda compound: ("surechembl", compound.name),
        search_bigquery=lambda compound: ("bigquery", compound.name),
        search_bigquery_annotations=lambda compound: ("bigquery_annotations", compound.name),
        search_patcid=lambda compound: ("patcid", compound.name),
        search_pubchem_similar=lambda compound: ("pubchem_similar", compound.name),
        search_bigquery_cpc=lambda compound, expanded: ("cpc_search", compound.name, expanded),
        search_bigquery_assignee=lambda compound, expanded: (
            "assignee_search",
            compound.name,
            expanded,
        ),
        search_epo_claims=lambda compound, expanded: ("epo_search", compound.name, expanded),
        search_kipris=lambda compound: ("kipris", compound.name),
        search_patentscope=lambda compound: ("patentscope", compound.name),
        search_bigquery_translated=lambda compound: ("bigquery_translated", compound.name),
        search_patentsview=lambda compound: ("patentsview", compound.name),
    )

    names = [name for name, _coro in plan]

    assert "pubchem_sdq" not in names
    assert "pubchem_similar" not in names
