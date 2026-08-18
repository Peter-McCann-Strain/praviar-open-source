"""Tests for PTAB client — mocked at the httpx transport level."""

from __future__ import annotations

import re

import pytest
from pytest_httpx import HTTPXMock

from praviar_pipeline.clients.ptab import PTABClient
from praviar_pipeline.errors import AuthenticationError, SourceUnavailableError


@pytest.fixture
def ptab_client(mock_settings) -> PTABClient:
    return PTABClient()


class TestPTABProceedings:
    async def test_get_proceedings(self, ptab_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/proceedings/search"),
            json={
                "results": [
                    {
                        "trialNumber": "IPR2019-00123",
                        "trialTypeCode": "IPR",
                        "trialMetaData": {
                            "trialTypeCode": "102",
                            "trialStatusCategory": "Final Written Decision",
                            "accordedFilingDate": "2019-01-15",
                        },
                    }
                ]
            },
        )

        proceedings = await ptab_client.get_proceedings("7851188")
        assert len(proceedings) == 1
        assert proceedings[0]["trialNumber"] == "IPR2019-00123"
        await ptab_client.close()

    async def test_get_proceedings_empty(self, ptab_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/proceedings/search"),
            json={"results": []},
        )

        proceedings = await ptab_client.get_proceedings("0000000")
        assert proceedings == []
        await ptab_client.close()

    async def test_get_proceedings_strips_prefix(self, ptab_client, httpx_mock: HTTPXMock):
        """Patent numbers like US7851188B2 should be cleaned before search."""
        httpx_mock.add_response(
            url=re.compile(r".*/proceedings/search"),
            json={"results": []},
        )

        await ptab_client.get_proceedings("US7851188B2")
        request = httpx_mock.get_requests()[0]
        body = request.read().decode()
        # Cleaned number should not contain full patent format
        assert "US7851188B2" not in body
        assert "7851188" in body
        await ptab_client.close()

    async def test_get_proceedings_auth_failure(self, ptab_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/proceedings/search"),
            status_code=401,
        )

        with pytest.raises(AuthenticationError):
            await ptab_client.get_proceedings("7851188")
        await ptab_client.close()

    async def test_get_proceedings_500_raises_after_retries(
        self, ptab_client, httpx_mock: HTTPXMock
    ):
        httpx_mock.add_response(
            url=re.compile(r".*/proceedings/search"),
            status_code=500,
        )
        httpx_mock.add_response(
            url=re.compile(r".*/proceedings/search"),
            status_code=500,
        )
        httpx_mock.add_response(
            url=re.compile(r".*/proceedings/search"),
            status_code=500,
        )

        with pytest.raises(SourceUnavailableError):
            await ptab_client.get_proceedings("7851188")
        await ptab_client.close()

    async def test_get_proceedings_429_raises_after_retries(
        self, ptab_client, httpx_mock: HTTPXMock
    ):
        httpx_mock.add_response(
            url=re.compile(r".*/proceedings/search"),
            status_code=429,
        )
        httpx_mock.add_response(
            url=re.compile(r".*/proceedings/search"),
            status_code=429,
        )
        httpx_mock.add_response(
            url=re.compile(r".*/proceedings/search"),
            status_code=429,
        )

        with pytest.raises(SourceUnavailableError):
            await ptab_client.get_proceedings("7851188")
        await ptab_client.close()


class TestPTABDecisions:
    async def test_get_decisions(self, ptab_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/decisions/search"),
            json={
                "results": [
                    {
                        "trialNumber": "IPR2019-00123",
                        "decisionData": {"decisionTypeCategory": "Final Written Decision"},
                    }
                ]
            },
        )

        decisions = await ptab_client.get_decisions("IPR2019-00123")
        assert len(decisions) == 1
        assert decisions[0]["trialNumber"] == "IPR2019-00123"
        await ptab_client.close()

    async def test_get_decisions_not_found(self, ptab_client, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=re.compile(r".*/decisions/search"),
            status_code=404,
        )

        decisions = await ptab_client.get_decisions("BOGUS-00000")
        assert decisions == []
        await ptab_client.close()
