"""Tests for EPO OPS client — mocked at the httpx transport level."""

from __future__ import annotations

import re

import pytest
from pytest_httpx import HTTPXMock

from praviar_pipeline.clients.epo_ops import EPOOPSClient, _to_docdb_format
from praviar_pipeline.clients.epo_ops_parsing import parse_family
from praviar_pipeline.errors import AuthenticationError
from praviar_pipeline.models.patent_lineage import PatentFamilyMember
from praviar_pipeline.utils.patent_family import (
    pending_family_member_ids,
    unresolved_family_member_ids,
)


@pytest.fixture
def epo_client(mock_settings) -> EPOOPSClient:
    return EPOOPSClient()


class TestDocdbFormat:
    def test_us_patent(self):
        assert _to_docdb_format("US7851188B2") == "US.7851188.B2"

    def test_ep_patent(self):
        assert _to_docdb_format("EP1234567A1") == "EP.1234567.A1"

    def test_passthrough(self):
        assert _to_docdb_format("unknown") == "unknown"


class TestTokenAcquisition:
    async def test_get_token(self, epo_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/auth/accesstoken"),
            json={"access_token": "test-token-123", "expires_in": 1200},
        )
        httpx_mock.add_response(
            url=re.compile(r".*/rest-services/.*"),
            json={},
        )

        # Trigger a request that needs a token
        await epo_client.get_legal_status("US7851188B2")
        # Verify auth endpoint was called
        requests = httpx_mock.get_requests()
        assert any("accesstoken" in str(r.url) for r in requests)
        await epo_client.close()

    async def test_auth_failure(self, epo_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/auth/accesstoken"),
            status_code=401,
        )

        with pytest.raises(AuthenticationError):
            await epo_client.get_legal_status("US7851188B2")
        await epo_client.close()

    async def test_missing_credentials(self, mock_settings):
        """Client should raise AuthenticationError if no key/secret configured."""
        from unittest.mock import patch

        with patch.dict("os.environ", {"OPS_CONSUMER_KEY": "", "OPS_CONSUMER_SECRET": ""}):
            client = EPOOPSClient()
            with pytest.raises(AuthenticationError):
                await client.get_legal_status("US7851188B2")
            await client.close()


class TestLegalStatus:
    async def test_get_legal_status(self, epo_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/auth/accesstoken"),
            json={"access_token": "test-token", "expires_in": 1200},
        )
        httpx_mock.add_response(
            url=re.compile(r".*/legal/publication/docdb/US\.7851188\.B2$"),
            json={
                "ops:world-patent-data": {
                    "ops:patent-family": {
                        "ops:family-member": {
                            "publication-reference": {"document-id": {"country": {"$": "US"}}},
                            "ops:legal": {
                                "@code": "GRANT",
                                "@desc": "Patent granted",
                                "@infl": "+",
                                "ops:L007": {"$": "2020-01-15"},
                                "ops:L018": {"$": "2020-01-16"},
                            },
                        },
                    }
                }
            },
        )

        events = await epo_client.get_legal_status("US7851188B2")
        assert len(events) == 1
        assert events[0]["event_code"] == "GRANT"
        assert events[0]["country"] == "US"
        assert events[0]["date_last_exchanged"] == "2020-01-16"
        await epo_client.close()

    async def test_legal_status_not_found(self, epo_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/auth/accesstoken"),
            json={"access_token": "test-token", "expires_in": 1200},
        )
        httpx_mock.add_response(
            url=re.compile(r".*/legal/publication/docdb/US\.0000000\.B2$"),
            status_code=404,
        )

        events = await epo_client.get_legal_status("US0000000B2")
        assert events == []
        await epo_client.close()


class TestFamily:
    async def test_get_family(self, epo_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/auth/accesstoken"),
            json={"access_token": "test-token", "expires_in": 1200},
        )
        httpx_mock.add_response(
            url=re.compile(r".*/family/.*"),
            json={
                "ops:world-patent-data": {
                    "ops:patent-family": {
                        "@family-id": "12345",
                        "ops:family-member": [
                            {
                                "publication-reference": {
                                    "document-id": [
                                        {
                                            "@document-id-type": "docdb",
                                            "country": {"$": "US"},
                                            "doc-number": {"$": "7851188"},
                                            "kind": {"$": "B2"},
                                        }
                                    ]
                                }
                            },
                            {
                                "publication-reference": {
                                    "document-id": [
                                        {
                                            "@document-id-type": "docdb",
                                            "country": {"$": "EP"},
                                            "doc-number": {"$": "1234567"},
                                            "kind": {"$": "A1"},
                                        }
                                    ]
                                }
                            },
                        ],
                    }
                }
            },
        )

        family = await epo_client.get_family("US7851188B2")
        assert family["family_id"] == "12345"
        assert len(family["members"]) == 2
        assert family["members"][0]["country"] == "US"
        assert family["members"][1]["country"] == "EP"
        await epo_client.close()

    def test_explicit_application_reference_links_a_publication_to_b_grant(self):
        family = parse_family(
            {
                "ops:world-patent-data": {
                    "ops:patent-family": {
                        "@family-id": "98765",
                        "ops:family-member": [
                            {
                                "@family-id": "98765",
                                "publication-reference": {
                                    "document-id": {
                                        "@document-id-type": "docdb",
                                        "country": {"$": "US"},
                                        "doc-number": {"$": "20200123456"},
                                        "kind": {"$": "A1"},
                                        "date": {"$": "20200116"},
                                    }
                                },
                                "application-reference": {
                                    "@doc-id": "100001",
                                    "document-id": {
                                        "@document-id-type": "docdb",
                                        "country": {"$": "US"},
                                        "doc-number": {"$": "16123456"},
                                        "kind": {"$": "A"},
                                        "date": {"$": "20190102"},
                                    },
                                },
                            },
                            {
                                "@family-id": "98765",
                                "publication-reference": {
                                    "document-id": {
                                        "@document-id-type": "docdb",
                                        "country": {"$": "US"},
                                        "doc-number": {"$": "11223344"},
                                        "kind": {"$": "B2"},
                                        "date": {"$": "20220201"},
                                    }
                                },
                                "application-reference": {
                                    "@doc-id": "100001",
                                    "document-id": {
                                        "@document-id-type": "docdb",
                                        "country": {"$": "US"},
                                        "doc-number": {"$": "16123456"},
                                        "kind": {"$": "A"},
                                        "date": {"$": "20190102"},
                                    },
                                },
                            },
                        ],
                    }
                }
            }
        )

        assert [member["doc_number"] for member in family["members"]] == [
            "20200123456",
            "11223344",
        ]
        assert {member["application_number"] for member in family["members"]} == {"US16123456"}
        assert all(member["application_identity_verified"] for member in family["members"])
        assert {member["application_identity_source"] for member in family["members"]} == {
            "epo_ops_family.application-reference.docdb"
        }

        members = [PatentFamilyMember(**member) for member in family["members"]]
        assert pending_family_member_ids(members) == []
        assert unresolved_family_member_ids(members) == []

    def test_missing_application_reference_remains_unresolved(self):
        family = parse_family(
            {
                "ops:world-patent-data": {
                    "ops:patent-family": {
                        "ops:family-member": {
                            "publication-reference": {
                                "document-id": {
                                    "@document-id-type": "docdb",
                                    "country": {"$": "US"},
                                    "doc-number": {"$": "20200123456"},
                                    "kind": {"$": "A1"},
                                }
                            }
                        }
                    }
                }
            }
        )

        member = family["members"][0]
        assert member["application_number"] == ""
        assert member["application_identity_verified"] is False
        assert member["application_identity_source"] == ""
        assert unresolved_family_member_ids([PatentFamilyMember(**member)]) == ["US20200123456A1"]

    def test_conflicting_application_references_remain_unresolved(self):
        family = parse_family(
            {
                "ops:world-patent-data": {
                    "ops:patent-family": {
                        "ops:family-member": {
                            "publication-reference": {
                                "document-id": {
                                    "@document-id-type": "docdb",
                                    "country": {"$": "US"},
                                    "doc-number": {"$": "20200123456"},
                                    "kind": {"$": "A1"},
                                }
                            },
                            "application-reference": [
                                {
                                    "@doc-id": "100001",
                                    "document-id": {
                                        "@document-id-type": "docdb",
                                        "country": {"$": "US"},
                                        "doc-number": {"$": "16123456"},
                                        "kind": {"$": "A"},
                                    },
                                },
                                {
                                    "@doc-id": "100002",
                                    "document-id": {
                                        "@document-id-type": "docdb",
                                        "country": {"$": "US"},
                                        "doc-number": {"$": "16999999"},
                                        "kind": {"$": "A"},
                                    },
                                },
                            ],
                        }
                    }
                }
            }
        )

        member = family["members"][0]
        assert member["application_number"] == ""
        assert member["application_identity_verified"] is False
        assert member["application_identity_source"] == ""
        assert unresolved_family_member_ids([PatentFamilyMember(**member)]) == ["US20200123456A1"]


class TestBibliographicData:
    async def test_get_biblio(self, epo_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/auth/accesstoken"),
            json={"access_token": "test-token", "expires_in": 1200},
        )
        httpx_mock.add_response(
            url=re.compile(r".*/biblio"),
            json={
                "ops:world-patent-data": {
                    "exchange-documents": {
                        "exchange-document": {
                            "bibliographic-data": {
                                "invention-title": [{"@lang": "en", "$": "Test title"}],
                                "parties": {
                                    "applicants": {
                                        "applicant": {
                                            "applicant-name": {"name": {"$": "Acme Corp"}}
                                        }
                                    },
                                    "inventors": {
                                        "inventor": {
                                            "inventor-name": {"name": {"$": "Ada Lovelace"}}
                                        }
                                    },
                                },
                                "patent-classifications": {
                                    "patent-classification": {
                                        "section": {"$": "A"},
                                        "class": {"$": "01"},
                                        "subclass": {"$": "B"},
                                    }
                                },
                                "priority-claims": {
                                    "priority-claim": {
                                        "@kind": "A",
                                        "document-id": {
                                            "country": {"$": "US"},
                                            "doc-number": {"$": "123"},
                                            "date": {"$": "20200101"},
                                        },
                                    }
                                },
                            },
                            "abstract": [{"@lang": "en", "p": {"$": "Short abstract"}}],
                        },
                    },
                }
            },
        )

        biblio = await epo_client.get_biblio("US7851188B2")
        assert biblio["title"] == "Test title"
        assert biblio["abstract"] == "Short abstract"
        assert biblio["applicants"] == ["Acme Corp"]
        assert biblio["inventors"] == ["Ada Lovelace"]
        assert biblio["cpc_codes"] == ["A01B"]
        assert biblio["priority_claims"][0]["country"] == "US"
        await epo_client.close()

    async def test_get_claims_text(self, epo_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/auth/accesstoken"),
            json={"access_token": "test-token", "expires_in": 1200},
        )
        httpx_mock.add_response(
            url=re.compile(r".*/claims"),
            json={
                "ops:world-patent-data": {
                    "ftxt:fulltext-documents": {
                        "ftxt:fulltext-document": {
                            "claims": [
                                {
                                    "@lang": "fr",
                                    "claim": {"claim-text": {"$": "ignored"}},
                                },
                                {
                                    "@lang": "en",
                                    "claim": [
                                        {"claim-text": {"$": "Claim 1"}},
                                        {"claim-text": {"$": "Claim 2"}},
                                    ],
                                },
                            ]
                        }
                    }
                }
            },
        )

        claims = await epo_client.get_claims_text("US7851188B2")
        assert claims == "Claim 1\n\nClaim 2"
        await epo_client.close()


class TestRegisterAndDrawings:
    async def test_get_register(self, epo_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/auth/accesstoken"),
            json={"access_token": "test-token", "expires_in": 1200},
        )
        httpx_mock.add_response(
            url=re.compile(
                r".*/register/publication/epodoc/EP1234567/"
                r"biblio,events,procedural-steps$"
            ),
            json={
                "ops:world-patent-data": {
                    "ops:register-search": {
                        "reg:register-documents": {
                            "reg:register-document": {
                                "@status": "Pending",
                                "@date-produced": "20260726",
                                "reg:bibliographic-data": {
                                    "reg:designation-of-states": {
                                        "reg:designation-epc": {
                                            "reg:country": [
                                                {"$": "EP"},
                                                {"$": "DE"},
                                            ]
                                        }
                                    },
                                },
                                "reg:events-data": {
                                    "reg:dossier-event": {
                                        "reg:event-date": {"reg:date": {"$": "2021-01-01"}},
                                        "reg:event-code": {"$": "OPP"},
                                        "reg:event-text": {
                                            "@event-text-type": "DESCRIPTION",
                                            "$": "Opposition filed",
                                        },
                                    },
                                },
                            }
                        }
                    }
                }
            },
        )
        httpx_mock.add_response(
            url=re.compile(r".*/register/publication/epodoc/EP1234567/upp$"),
            json={
                "ops:world-patent-data": {
                    "ops:register-search": {
                        "reg:register-documents": {
                            "reg:register-document": {
                                "@date-produced": "20260726",
                                "reg:unitary-patent": {
                                    "reg:unitary-patent-statuses": {
                                        "reg:unitary-patent-status": {
                                            "@change-date": "20260725",
                                            "@status-code": "6",
                                            "$": "Request for unitary effect filed",
                                        }
                                    }
                                },
                            }
                        }
                    }
                }
            },
        )

        register = await epo_client.get_register("EP1234567A1")
        assert register["designated_states"] == ["EP", "DE"]
        assert register["status"] == "Pending"
        assert register["opposition_events"][0]["event_code"] == "OPP"
        assert register["legal_events"][0]["event_description"] == "Opposition filed"
        assert register["record_produced_at"] == "20260726"
        assert register["unitary_patent"]["statuses"][0]["status_code"] == "6"
        assert "national post-grant" in register["scope_limitation"]
        await epo_client.close()

    async def test_get_drawing_page_count(self, epo_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/auth/accesstoken"),
            json={"access_token": "test-token", "expires_in": 1200},
        )
        httpx_mock.add_response(
            url=re.compile(r".*/images"),
            json={
                "ops:world-patent-data": {
                    "ops:document-inquiry": {
                        "ops:inquiry-result": {
                            "ops:document-instance": {
                                "@desc": "Drawing pages",
                                "@number-of-pages": "4",
                            }
                        }
                    }
                }
            },
        )

        assert await epo_client.get_drawing_page_count("US7851188B2") == 4
        await epo_client.close()

    async def test_fetch_drawing_page(self, epo_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/auth/accesstoken"),
            json={"access_token": "test-token", "expires_in": 1200},
        )
        httpx_mock.add_response(
            url=re.compile(r".*/images$"),
            match_headers={"Range": "3-3"},
            content=b"page-3",
        )

        page = await epo_client.fetch_drawing_page("US7851188B2", page=3)
        assert page == b"page-3"
        await epo_client.close()

    async def test_fetch_all_drawings(self, epo_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/auth/accesstoken"),
            json={"access_token": "test-token", "expires_in": 1200},
        )
        httpx_mock.add_response(
            url=re.compile(r".*/images$"),
            json={
                "ops:world-patent-data": {
                    "ops:document-inquiry": {
                        "ops:inquiry-result": {
                            "ops:document-instance": {
                                "@desc": "Drawing pages",
                                "@number-of-pages": "2",
                            }
                        }
                    }
                }
            },
        )
        httpx_mock.add_response(
            url=re.compile(r".*/images$"),
            match_headers={"Range": "1-1"},
            content=b"page-1",
        )
        httpx_mock.add_response(
            url=re.compile(r".*/images$"),
            match_headers={"Range": "2-2"},
            content=b"page-2",
        )

        drawings = await epo_client.fetch_all_drawings("US7851188B2")
        assert drawings == [(1, b"page-1"), (2, b"page-2")]
        await epo_client.close()
