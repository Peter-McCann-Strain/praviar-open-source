from __future__ import annotations

from datetime import date

import pytest

from praviar_pipeline.models.invalidity import PriorArtReference
from praviar_pipeline.pipeline.invalidity import scholarly_helpers

pytestmark = pytest.mark.usefixtures("mock_settings")


def test_build_openalex_reference_normalizes_doi_url():
    reference = scholarly_helpers.build_openalex_reference(
        {
            "id": "oa-1",
            "title": "OpenAlex paper",
            "publication_date": "2010-01-01",
            "doi": "https://doi.org/10.1000/example",
            "authorships": [{"author": {"display_name": "A. Author"}}],
        }
    )

    assert reference.reference_id == "oa-1"
    assert reference.doi == "10.1000/example"


def test_collect_reference_deduplicates_by_doi():
    refs_by_doi: dict[str, PriorArtReference] = {}
    refs_no_doi: list[PriorArtReference] = []
    reference = PriorArtReference(
        reference_id="r1",
        title="Paper",
        doi="10.1000/dup",
        source_database="pubmed",
    )

    scholarly_helpers.collect_reference(reference, refs_by_doi, refs_no_doi)
    scholarly_helpers.collect_reference(reference, refs_by_doi, refs_no_doi)

    assert list(refs_by_doi) == ["10.1000/dup"]
    assert refs_no_doi == []


def test_filter_references_before_priority_date_skips_post_priority_refs():
    older = PriorArtReference(
        reference_id="older",
        title="Older",
        publication_date=date(2008, 1, 1),
        source_database="pubmed",
    )
    newer = PriorArtReference(
        reference_id="newer",
        title="Newer",
        publication_date=date(2012, 1, 1),
        source_database="pubmed",
    )

    filtered, skipped = scholarly_helpers.filter_references_before_priority_date(
        [older, newer],
        date(2010, 1, 1),
    )

    assert [reference.reference_id for reference in filtered] == ["older"]
    assert skipped == 1


def test_combine_scholarly_references_merges_and_filters():
    by_doi = {
        "10.1000/dup": PriorArtReference(
            reference_id="doi-ref",
            title="Doi Ref",
            publication_date=date(2009, 1, 1),
            doi="10.1000/dup",
            source_database="semantic_scholar",
        )
    }
    no_doi = [
        PriorArtReference(
            reference_id="no-doi",
            title="No Doi",
            publication_date=date(2008, 1, 1),
            source_database="pubmed",
        ),
        PriorArtReference(
            reference_id="post-priority",
            title="Post Priority",
            publication_date=date(2012, 1, 1),
            source_database="pubmed",
        ),
    ]

    filtered, skipped, total_raw, unique_by_doi, without_doi = (
        scholarly_helpers.combine_scholarly_references(
            [(by_doi, no_doi)],
            date(2010, 1, 1),
        )
    )

    assert [reference.reference_id for reference in filtered] == ["doi-ref", "no-doi"]
    assert skipped == 1
    assert total_raw == 3
    assert unique_by_doi == 1
    assert without_doi == 2
