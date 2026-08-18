"""Tests for SG-122 continuation/divisional/reissue expansion (Step 2)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from praviar_pipeline.errors import ConfigurationError, SourceUnavailableError
from praviar_pipeline.models.patent import PatentHit, PatentSource
from praviar_pipeline.pipeline.search.continuation_expansion import expand_continuations


def _hit(patent_id: str, **kwargs) -> PatentHit:
    return PatentHit(
        patent_id=patent_id,
        sources=[PatentSource.BIGQUERY],
        confidence_score=0.5,
        **kwargs,
    )


def _odp_client_factory(continuity_entries: list[dict]) -> type:
    """Build an async-context-manager factory returning a mocked ODP client."""

    class _FakeODPClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get_continuity_data(self, patent_id: str) -> list[dict]:
            return continuity_entries

    return _FakeODPClient


def _epo_client_factory(family_data: dict | None, *, raises: Exception | None = None) -> type:
    class _FakeEPOClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get_family(self, patent_id: str) -> dict | None:
            if raises is not None:
                raise raises
            return family_data

    return _FakeEPOClient


def _mock_settings_both_enabled() -> object:
    class _S:
        uspto_odp_api_key = "test-key"
        ops_consumer_key = "ops-key"
        ops_consumer_secret = "ops-sec"
        search_max_family_patents = 50

    return _S()


async def test_expand_continuations_adds_continuation_hit():
    hits = [_hit("US7000000B2", title="Parent")]
    odp_factory = _odp_client_factory(
        [
            {
                "claimParentageTypeLabel": "Continuation",
                "childPatentNumber": "US7500000B2",
            }
        ]
    )
    epo_factory = _epo_client_factory({"family_id": "F1", "members": []})

    with patch(
        "praviar_pipeline.pipeline.search.continuation_expansion.get_settings",
        return_value=_mock_settings_both_enabled(),
    ):
        added = await expand_continuations(
            hits,
            odp_client_factory=odp_factory,
            epo_client_factory=epo_factory,
            max_depth=1,
        )

    assert added == 1
    assert len(hits) == 2
    child = next(h for h in hits if h.patent_id == "US7500000B2")
    assert child.family_role == "continuation"
    assert child.parent_application_id == "US7000000B2"


async def test_expand_continuations_dedupes_existing_hit():
    # Continuation is already in the hit list — must not be duplicated.
    hits = [
        _hit("US7000000B2", title="Parent"),
        _hit("US7500000B2", title="Already-found continuation"),
    ]
    odp_factory = _odp_client_factory(
        [
            {
                "claimParentageTypeLabel": "Continuation",
                "childPatentNumber": "US7500000B2",
            }
        ]
    )
    epo_factory = _epo_client_factory({"family_id": "F1", "members": []})

    with patch(
        "praviar_pipeline.pipeline.search.continuation_expansion.get_settings",
        return_value=_mock_settings_both_enabled(),
    ):
        added = await expand_continuations(
            hits,
            odp_client_factory=odp_factory,
            epo_client_factory=epo_factory,
            max_depth=1,
        )

    assert added == 0
    assert len(hits) == 2
    existing = next(h for h in hits if h.patent_id == "US7500000B2")
    # Metadata was merged onto the existing hit.
    assert existing.family_role == "continuation"
    assert existing.parent_application_id == "US7000000B2"
    # Existing hit kept its own source (no duplication).
    assert PatentSource.BIGQUERY in existing.sources


async def test_expand_continuations_fails_closed_on_source_unavailable():
    hits = [_hit("US7000000B2", title="Parent")]

    class _UnavailableODP:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get_continuity_data(self, patent_id: str):
            raise SourceUnavailableError("uspto_odp", "503 unavailable")

    epo_factory = _epo_client_factory(
        None, raises=SourceUnavailableError("epo_ops", "503 on family")
    )

    with patch(
        "praviar_pipeline.pipeline.search.continuation_expansion.get_settings",
        return_value=_mock_settings_both_enabled(),
    ):
        with pytest.raises(SourceUnavailableError) as excinfo:
            await expand_continuations(
                hits,
                odp_client_factory=_UnavailableODP,
                epo_client_factory=epo_factory,
                max_depth=1,
            )

    assert excinfo.value.source == "uspto_odp"


async def test_expand_continuations_fails_closed_without_credentials():
    hits = [_hit("US7000000B2")]

    class _NoCredsSettings:
        uspto_odp_api_key = ""
        ops_consumer_key = ""
        ops_consumer_secret = ""
        search_max_family_patents = 50

    # Factories must not be instantiated; pass sentinels that would explode if called.
    def _boom():  # pragma: no cover - should never be called
        raise AssertionError("client factory should not be invoked without credentials")

    with patch(
        "praviar_pipeline.pipeline.search.continuation_expansion.get_settings",
        return_value=_NoCredsSettings(),
    ):
        with pytest.raises(ConfigurationError) as excinfo:
            await expand_continuations(
                hits,
                odp_client_factory=_boom,
                epo_client_factory=_boom,
            )

    assert excinfo.value.source == "continuation_expansion"
    assert "uspto_odp" in str(excinfo.value)
    assert "epo_ops" in str(excinfo.value)
    assert len(hits) == 1


async def test_expand_continuations_wraps_transport_errors_as_source_unavailable():
    hits = [_hit("US7000000B2", title="Parent")]

    class _BrokenODP:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get_continuity_data(self, patent_id: str):
            raise httpx.ConnectError("offline")

    epo_factory = _epo_client_factory({"members": []})

    with patch(
        "praviar_pipeline.pipeline.search.continuation_expansion.get_settings",
        return_value=_mock_settings_both_enabled(),
    ):
        with pytest.raises(SourceUnavailableError) as excinfo:
            await expand_continuations(
                hits,
                odp_client_factory=_BrokenODP,
                epo_client_factory=epo_factory,
                max_depth=1,
            )

    assert excinfo.value.source == "uspto_odp"
    assert str(excinfo.value) == "uspto_odp unavailable: continuation lookup failed"
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__context__ is None


async def test_expand_continuations_adds_divisional_and_reissue():
    hits = [_hit("US8000000B2", title="Parent")]
    odp_factory = _odp_client_factory(
        [
            {"claimParentageTypeLabel": "Divisional", "childPatentNumber": "US8100000B2"},
            {"claimParentageTypeLabel": "Reissue", "childPatentNumber": "USRE46000E1"},
            {
                "claimParentageTypeLabel": "Continuation-in-part",
                "childPatentNumber": "US8200000B2",
            },
            # Noise: a "parent" entry we should ignore.
            {"claimParentageTypeLabel": "Parent", "childPatentNumber": "US7900000B2"},
        ]
    )
    epo_factory = _epo_client_factory({"members": []})

    with patch(
        "praviar_pipeline.pipeline.search.continuation_expansion.get_settings",
        return_value=_mock_settings_both_enabled(),
    ):
        added = await expand_continuations(
            hits,
            odp_client_factory=odp_factory,
            epo_client_factory=epo_factory,
            max_depth=1,
        )

    assert added == 3
    roles = {h.patent_id: h.family_role for h in hits if h.parent_application_id}
    assert roles["US8100000B2"] == "divisional"
    assert roles["USRE46000E1"] == "reissue"
    assert roles["US8200000B2"] == "continuation_in_part"


async def test_expand_continuations_epo_family_adds_non_us_member():
    hits = [_hit("US7000000B2", title="Parent")]
    odp_factory = _odp_client_factory([])
    epo_factory = _epo_client_factory(
        {
            "family_id": "F1",
            "members": [
                {"country": "EP", "doc_number": "1234567", "kind": "A1"},
                # US self — must be skipped via normalized-id de-dupe.
                {"country": "US", "doc_number": "7000000", "kind": "B2"},
            ],
        }
    )

    with patch(
        "praviar_pipeline.pipeline.search.continuation_expansion.get_settings",
        return_value=_mock_settings_both_enabled(),
    ):
        added = await expand_continuations(
            hits,
            odp_client_factory=odp_factory,
            epo_client_factory=epo_factory,
            max_depth=1,
        )

    assert added == 1
    ep_hit = next(h for h in hits if h.patent_id.startswith("EP"))
    assert ep_hit.parent_application_id == "US7000000B2"
    assert ep_hit.family_role == "unknown"


async def test_expand_continuations_respects_max_depth():
    """Chain: parent -> child -> grandchild. With max_depth=1, stop after one level."""
    continuity_by_patent = {
        "US7000000B2": [
            {"claimParentageTypeLabel": "Continuation", "childPatentNumber": "US7500000B2"},
        ],
        "US7500000B2": [
            {"claimParentageTypeLabel": "Continuation", "childPatentNumber": "US8000000B2"},
        ],
    }

    class _ChainODP:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get_continuity_data(self, patent_id: str):
            return continuity_by_patent.get(patent_id, [])

    epo_factory = _epo_client_factory({"members": []})

    hits = [_hit("US7000000B2")]
    with patch(
        "praviar_pipeline.pipeline.search.continuation_expansion.get_settings",
        return_value=_mock_settings_both_enabled(),
    ):
        added = await expand_continuations(
            hits,
            odp_client_factory=_ChainODP,
            epo_client_factory=epo_factory,
            max_depth=1,
        )
    assert added == 1
    ids = {h.patent_id for h in hits}
    assert "US7500000B2" in ids
    assert "US8000000B2" not in ids

    # With max_depth=2, the grandchild is also picked up.
    hits = [_hit("US7000000B2")]
    with patch(
        "praviar_pipeline.pipeline.search.continuation_expansion.get_settings",
        return_value=_mock_settings_both_enabled(),
    ):
        added = await expand_continuations(
            hits,
            odp_client_factory=_ChainODP,
            epo_client_factory=epo_factory,
            max_depth=2,
        )
    ids = {h.patent_id for h in hits}
    assert "US7500000B2" in ids
    assert "US8000000B2" in ids
    assert added == 2


async def test_expand_continuations_empty_hits_noop():
    added = await expand_continuations([])
    assert added == 0


# Ensure AsyncMock import is considered used (re-exported for potential future tests).
_ = AsyncMock
