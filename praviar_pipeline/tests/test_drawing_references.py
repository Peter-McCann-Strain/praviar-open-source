from __future__ import annotations

from praviar_pipeline.pipeline.drawings.references import cross_check_figure_references


def test_cross_check_handles_figure_structure_and_scheme_variants() -> None:
    text = "FIG. 1, Figure 2, Structure 8, and Scheme 12 show the embodiments."

    gaps = cross_check_figure_references(text, 5)

    assert gaps == [
        "Figure 8 referenced in claims but only 5 drawing pages were fetched",
        "Figure 12 referenced in claims but only 5 drawing pages were fetched",
    ]


def test_cross_check_ignores_roman_numeral_formula_references() -> None:
    text = "The compound of Formula I and Structure II is described in the specification."

    gaps = cross_check_figure_references(text, 3)

    assert gaps == []
