"""Tests for api.services.report_evidence_filter — covering previously-missed branches.

All functions are pure and synchronous; no mocking required.
Targets: lines 57, 65, 72, 78, 86-90, 119, 152, 174, 201, 206-207, 221.
"""

from __future__ import annotations

# ── helpers ──────────────────────────────────────────────────────────────────


def _f():
    from api.services import report_evidence_filter as f

    return f


# ── normalized_trust_mode: line 57 — fallback "explorer" when invalid value ──


def test_normalized_trust_mode_invalid_returns_explorer():
    f = _f()
    assert f.normalized_trust_mode({"trust_mode": "unknown_mode"}) == "explorer"


# ── looks_like_patent_identifier: line 65 ────────────────────────────────────


def test_looks_like_patent_identifier_true():
    f = _f()
    assert f.looks_like_patent_identifier("US10000000B2") is True


def test_looks_like_patent_identifier_false():
    f = _f()
    assert f.looks_like_patent_identifier("aspirin synthesis") is False


# ── query_patent_identifier: line 72 (match found) ───────────────────────────


def test_query_patent_identifier_with_match_returns_identifier():
    f = _f()
    result = f.query_patent_identifier("see US10000000B2 for details")
    assert result is not None
    assert "US10000000" in result


def test_query_patent_identifier_no_match_returns_none():
    f = _f()
    assert f.query_patent_identifier("no patent here") is None


# ── excerpt: line 78 (empty content) ─────────────────────────────────────────


def test_excerpt_empty_content_returns_empty_string():
    f = _f()
    assert f.excerpt("", "query") == ""


def test_excerpt_whitespace_only_returns_empty_string():
    f = _f()
    assert f.excerpt("   ", "query") == ""


# ── excerpt: lines 86-90 (content > limit, query found at offset) ─────────────


def test_excerpt_long_content_with_query_found_returns_window():
    f = _f()
    # build a content string >220 chars with query buried inside
    prefix_padding = "x" * 100
    suffix_padding = "y" * 200
    content = f"{prefix_padding} aspirin {suffix_padding}"
    result = f.excerpt(content, "aspirin", limit=50)
    # result must be shorter than the full content and contain the query
    assert "aspirin" in result
    assert len(result) < len(content)


# ── classify_provider: line 119 (empty source name → None) ───────────────────


def test_classify_provider_empty_string_returns_none():
    f = _f()
    assert f.classify_provider("") is None


def test_classify_provider_none_returns_none():
    f = _f()
    assert f.classify_provider(None) is None  # type: ignore[arg-type]


def test_classify_provider_unknown_returns_none():
    f = _f()
    assert f.classify_provider("totally_unknown_source_xyz") is None


# ── collect_sources: line 152 (non-dict log_entry continues) ─────────────────


def test_collect_sources_non_dict_log_entry_is_skipped():
    f = _f()
    report = {"search_strategy_log": ["not a dict", 42, None]}
    result = f.collect_sources(report)
    assert result == []


# ── collect_jurisdictions: line 174 (non-dict log_entry continues) ────────────


def test_collect_jurisdictions_non_dict_log_entry_is_skipped():
    f = _f()
    report = {
        "search_strategy_log": ["string entry", 99],
        "target_jurisdictions": ["US"],
    }
    result = f.collect_jurisdictions(report)
    assert result == ["US"]


# ── report_compound_context: line 201 (compound not a dict) ──────────────────


def test_report_compound_context_non_dict_compound_returns_empty():
    f = _f()
    assert f.report_compound_context({"compound": "aspirin"}) == ("", "", None)


def test_report_compound_context_missing_compound_returns_empty():
    f = _f()
    assert f.report_compound_context({}) == ("", "", None)


# ── report_compound_context: lines 206-207 (cid_raw is digit string) ──────────


def test_report_compound_context_string_cid_parses_to_int():
    f = _f()
    report = {"compound": {"name": "aspirin", "pubchem_cid": "2244"}}
    name, smiles, cid = f.report_compound_context(report)
    assert name == "aspirin"
    assert cid == 2244


# ── external_query_jurisdictions: line 221 ("UK" → "GB") ─────────────────────


def test_external_query_jurisdictions_uk_maps_to_gb():
    f = _f()
    report = {"target_jurisdictions": ["UK", "US"]}
    result = f.external_query_jurisdictions(report)
    assert "GB" in result
    assert "UK" not in result
    assert "US" in result
