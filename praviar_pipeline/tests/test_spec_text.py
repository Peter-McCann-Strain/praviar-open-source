"""Tests for specification-text parsing and chunking (Task 2.2).

These exercise the claim-construction path: an ambiguous claim term must be
construable against the relevant specification passage even when the
specification is large, with no regression to the historical 80k truncation
that silently discarded later definitions.
"""

from __future__ import annotations

from praviar_pipeline.utils.spec_text import (
    chunk_spec_text,
    parse_spec_passages,
)


def test_parse_spec_passages_splits_on_paragraph_markers() -> None:
    spec = (
        "[0001] This invention relates to widgets.\n\n"
        '[0002] As used herein, the term "widget" means a fastening device.\n\n'
        "[0003] Preferred embodiments use steel."
    )
    passages = parse_spec_passages(spec)

    assert [p.paragraph for p in passages] == ["0001", "0002", "0003"]
    definitions = [p for p in passages if p.is_definition]
    assert len(definitions) == 1
    assert definitions[0].paragraph == "0002"
    assert definitions[0].citation == "para. 0002"


def test_parse_spec_passages_falls_back_to_blank_line_split() -> None:
    spec = "First block of text.\n\nThe term gadget refers to a control unit."
    passages = parse_spec_passages(spec)

    assert len(passages) == 2
    assert all(p.paragraph == "" for p in passages)
    assert passages[1].is_definition is True
    assert passages[1].citation == "spec."


def test_chunk_spec_text_returns_short_text_unchanged() -> None:
    spec = "[0001] A short specification within budget."
    assert chunk_spec_text(spec, max_chars=100_000) == spec


def test_chunk_spec_text_preserves_definition_past_historical_truncation() -> None:
    """The defining passage sits far past 80k yet must survive chunking.

    Historically the cache sliced ``full_text[:80000]``, which would discard a
    definition placed beyond that point. Definition-aware chunking keeps it so
    an ambiguous claim term can still be construed against the specification.
    """
    filler_para = "[0001] " + ("background discussion of the prior art. " * 60) + "\n\n"
    # ~120k characters of non-definitional filler precedes the definition.
    filler = filler_para * 1000
    definition = (
        '[5000] As used herein, the term "stabiliser" means a non-ionic '
        "surfactant that prevents aggregation of the active compound."
    )
    spec = filler + definition
    assert len(spec) > 80_000

    chunked = chunk_spec_text(spec, max_chars=80_000)

    assert len(chunked) <= 80_000
    # The ambiguous term's definition survived the size reduction.
    assert 'the term "stabiliser" means' in chunked
    assert "[5000]" in chunked


def test_chunk_spec_text_unparseable_text_keeps_documented_cap() -> None:
    spec = "x" * 200_000
    chunked = chunk_spec_text(spec, max_chars=50_000)
    assert len(chunked) == 50_000
