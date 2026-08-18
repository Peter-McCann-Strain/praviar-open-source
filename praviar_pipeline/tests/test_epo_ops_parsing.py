"""Tests for OPS response-shape tolerant parsers."""

from __future__ import annotations

from praviar_pipeline.clients.epo_ops_parsing import parse_biblio


def test_parse_biblio_accepts_exchange_documents_list_container() -> None:
    """OPS can wrap exchange-documents in a list for published-data biblio."""
    payload = {
        "ops:world-patent-data": [
            {
                "exchange-documents": [
                    {
                        "exchange-document": {
                            "bibliographic-data": {
                                "invention-title": [
                                    {"@lang": "en", "$": "Nucleoside phosphoramidates"}
                                ],
                                "parties": {
                                    "applicants": {
                                        "applicant": {
                                            "applicant-name": {"name": {"$": "Pharmasset Ltd."}}
                                        }
                                    }
                                },
                                "patent-classifications": {
                                    "patent-classification": {
                                        "section": {"$": "C"},
                                        "class": {"$": "07"},
                                        "subclass": {"$": "H"},
                                        "main-group": {"$": "19"},
                                        "subgroup": {"$": "073"},
                                    }
                                },
                                "priority-claims": {
                                    "priority-claim": {
                                        "@kind": "national",
                                        "document-id": [
                                            {
                                                "country": {"$": "US"},
                                                "doc-number": {"$": "200760514806P"},
                                                "date": {"$": "20070404"},
                                            }
                                        ],
                                    }
                                },
                            },
                            "abstract": {
                                "@lang": "en",
                                "p": {"$": "A compound useful for antiviral treatment."},
                            },
                        },
                    }
                ]
            }
        ]
    }

    result = parse_biblio(payload)

    assert result["title"] == "Nucleoside phosphoramidates"
    assert result["abstract"] == "A compound useful for antiviral treatment."
    assert result["applicants"] == ["Pharmasset Ltd."]
    assert result["cpc_codes"] == ["C07H19/073"]
    assert result["priority_claims"] == [
        {
            "country": "US",
            "doc_number": "200760514806P",
            "date": "20070404",
            "kind": "national",
        }
    ]
