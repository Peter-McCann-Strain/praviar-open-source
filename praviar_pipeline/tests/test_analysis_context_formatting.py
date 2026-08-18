from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.pipeline.analysis.context_formatting import (
    format_compound_for_analysis,
    format_patent_for_analysis,
)


def test_format_patent_for_analysis_includes_triage_context(
    sample_patent_hit, sample_triage_results
) -> None:
    text = format_patent_for_analysis(sample_patent_hit, sample_triage_results[0])
    assert "US7851188B2" in text
    assert "BioAmber Inc." in text
    assert "Directly covers succinic acid fermentation methods" in text


def test_format_compound_for_analysis_uses_settings_max_synonyms(succinic_acid) -> None:
    settings = SimpleNamespace(analysis_context_max_synonyms=1)
    text = format_compound_for_analysis(succinic_acid, get_settings_fn=lambda: settings)
    assert "succinic acid" in text
    assert "butanedioic acid" in text
