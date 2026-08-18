from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from praviar_pipeline.errors import AuthenticationError, SourceUnavailableError
from praviar_pipeline.models.invalidity import PTABResult
from praviar_pipeline.pipeline.invalidity.ptab import check_ptab_impl


def _ptab_client_ctx(client):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=ctx)


@pytest.mark.asyncio
async def test_check_ptab_impl_returns_empty_when_no_proceedings():
    client = AsyncMock()
    client.get_proceedings.return_value = []

    result = await check_ptab_impl(
        "US7851188B2",
        client_factory=_ptab_client_ctx(client),
        parse_date_fn=lambda value: date.fromisoformat(value) if value else None,
        logger=MagicMock(),
    )

    assert result.has_been_challenged is False
    assert result.proceedings == []
    assert result.all_claims_cancelled == []


@pytest.mark.asyncio
async def test_check_ptab_impl_parses_production_shape_without_inventing_claim_effects():
    client = AsyncMock()
    client.get_proceedings.return_value = [
        {
            "trialNumber": "IPR2020-00123",
            "trialTypeCode": "IPR",
            "trialMetaData": {
                "trialTypeCode": "102",
                "trialStatusCategory": "Final Written Decision",
                "accordedFilingDate": "2020-01-01",
            },
        }
    ]
    client.get_decisions.return_value = [
        {
            "trialNumber": "IPR2020-00123",
            "decisionData": {
                "decisionTypeCategory": "Final Written Decision",
                "decisionIssueDate": "2021-06-01",
            },
            "documentData": {"documentFilingDate": "2021-06-01"},
        }
    ]

    result = await check_ptab_impl(
        "US7851188B2",
        client_factory=_ptab_client_ctx(client),
        parse_date_fn=lambda value: date.fromisoformat(value) if value else None,
        logger=MagicMock(),
    )

    assert result.has_been_challenged is True
    assert len(result.proceedings) == 1
    assert result.proceedings[0].final_written_decision_verified is True
    assert result.proceedings[0].decision_date == date(2021, 6, 1)
    assert result.proceedings[0].claims_reported_cancelled == []
    assert result.proceedings[0].claims_cancelled == []
    assert result.all_claims_cancelled == []


@pytest.mark.asyncio
async def test_check_ptab_impl_rejects_obsolete_flat_claim_effect_fields():
    client = AsyncMock()
    client.get_proceedings.return_value = [
        {
            "trialNumber": "IPR2020-00123",
            "trialTypeCode": "IPR",
            "trialMetaData": {
                "trialTypeCode": "102",
                "trialStatusCategory": "Final Written Decision",
            },
        }
    ]
    client.get_decisions.return_value = [
        {
            "claimsCancelled": ["1", "3"],
            "decisionType": "Final Written Decision",
            "cancellationCertificateIssued": True,
            "reviewAndAppealPosture": "certificate issued after review concluded",
        }
    ]

    with pytest.raises(SourceUnavailableError, match="PTAB lookup failed"):
        await check_ptab_impl(
            "US7851188B2",
            client_factory=_ptab_client_ctx(client),
            parse_date_fn=lambda value: value,
            logger=MagicMock(),
        )


def test_ptab_aggregate_cannot_claim_cancellation_without_a_proceeding() -> None:
    with pytest.raises(ValueError, match=r"challenge state|verified proceedings"):
        PTABResult(
            has_been_challenged=False,
            proceedings=[],
            all_claims_cancelled=[1],
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("authentication_failure", [False, True])
async def test_check_ptab_impl_never_exposes_provider_credentials(authentication_failure):
    sentinel = "ptab-credential-sentinel-must-not-escape"
    request = httpx.Request(
        "GET",
        f"https://ptab.example.invalid/proceedings?api_key={sentinel}",
    )
    if authentication_failure:
        provider_error = AuthenticationError(
            f"rejected request {request.url}",
            source="ptab",
        )
        expected_type = AuthenticationError
        expected_message = "PTAB authentication failed"
    else:
        provider_error = httpx.ConnectError(
            f"failed request {request.url}",
            request=request,
        )
        expected_type = SourceUnavailableError
        expected_message = "ptab unavailable: PTAB lookup failed"

    client = AsyncMock()
    client.get_proceedings.side_effect = provider_error
    logger = MagicMock()

    with pytest.raises(expected_type) as exc_info:
        await check_ptab_impl(
            "US7851188B2",
            client_factory=_ptab_client_ctx(client),
            parse_date_fn=lambda value: value,
            logger=logger,
        )

    assert str(exc_info.value) == expected_message
    assert sentinel not in str(exc_info.value)
    assert sentinel not in repr(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    logger.error.assert_called_once()
    assert logger.error.call_args.kwargs["error_type"] == type(provider_error).__name__
    assert sentinel not in repr((logger.error.call_args.args, logger.error.call_args.kwargs))
    assert "error" not in logger.error.call_args.kwargs
    assert "exc_info" not in logger.error.call_args.kwargs
