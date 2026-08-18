from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.certification_policy import (
    certify_runtime_adapter,
    counsel_certified_jurisdictions_for_modality,
    expand_jurisdiction_bundle,
    filter_certified_runtime_adapters,
    filter_runtime_adapter_patent_ids,
    infer_jurisdiction_bundle,
    lane_status_for_trust_mode,
    local_review_required_for_lane,
    normalize_jurisdiction,
)


def test_certify_runtime_adapter_respects_explicit_target_jurisdictions():
    result = certify_runtime_adapter(
        "patentsview",
        settings=SimpleNamespace(asset_type_hint="small_molecule"),
        target_jurisdictions=["EP"],
    )

    assert not result.allowed
    assert "not validated there" in result.reason


def test_filter_runtime_adapter_patent_ids_keeps_only_matching_jurisdictions():
    filtered = filter_runtime_adapter_patent_ids(
        "patentsview",
        target_patent_ids=["US1234567B2", "EP1234567B1"],
    )

    assert filtered == ["US1234567B2"]


def test_filter_certified_runtime_adapters_dedupes_and_preserves_unknown_sources():
    filtered = filter_certified_runtime_adapters(
        ["family_record", "family_record", "custom_overlay"],
        settings=SimpleNamespace(asset_type_hint="small_molecule"),
        target_patent_ids=["EP1234567B1"],
    )

    assert filtered == ["family_record", "custom_overlay"]


def test_expand_jurisdiction_bundle_major_markets():
    expanded = expand_jurisdiction_bundle("major_markets")

    assert expanded == ("US", "EP", "UK", "IN", "JP", "CN")


def test_infer_jurisdiction_bundle_distinguishes_custom_and_named_sets():
    assert infer_jurisdiction_bundle(["US", "EP"]) == "us_europe"
    assert infer_jurisdiction_bundle(["EP", "UK"]) == "europe_uk"
    assert infer_jurisdiction_bundle(["US", "EP", "UK", "IN", "JP", "CN"]) == "major_markets"
    assert infer_jurisdiction_bundle(["US", "JP"]) == "custom"


def test_counsel_certified_jurisdictions_and_lane_status_follow_modality_defaults():
    assert counsel_certified_jurisdictions_for_modality("formulation") == ("US", "EP")
    assert counsel_certified_jurisdictions_for_modality("markush_candidate") == ()
    assert (
        lane_status_for_trust_mode(
            "UK",
            modality="formulation",
            trust_mode="counsel",
        )
        == "screening_only"
    )
    assert (
        lane_status_for_trust_mode(
            "UK",
            modality="formulation",
            trust_mode="monitor",
        )
        == "monitor_only"
    )
    assert local_review_required_for_lane("UK", modality="formulation") is True


def test_normalize_jurisdiction_covers_aliases_separators_and_unknown_values():
    assert normalize_jurisdiction(None) == ""
    assert normalize_jurisdiction(" united-kingdom ") == "UK"
    assert normalize_jurisdiction("united kingdom") == "UK"
    assert normalize_jurisdiction("new-market") == "NEW_MARKET"
