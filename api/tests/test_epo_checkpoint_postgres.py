"""Live PostgreSQL race proof for the durable EPO checkpoint store.

This test is intentionally gated and leaves append-only canary history behind.
It therefore requires a disposable, fully migrated test database.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from praviar_pipeline.clients.epo_publication_server import EPCheckpointAdvance
from praviar_pipeline.models.epo_publication import (
    EPSignedSnapshotHighWaterReceipt,
    EPTrustedAcquisitionKey,
    build_ep_snapshot_checkpoint_batch_sha256,
    build_ep_snapshot_checkpoint_envelope_sha256,
)
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from api.db.epo_checkpoint_store import PostgresEPAtomicCheckpointStore

pytestmark = pytest.mark.asyncio


class _UnusedKeyProvider:
    async def load_trusted_checkpoint_keys(
        self,
    ) -> dict[str, EPTrustedAcquisitionKey]:
        return {}


def _advances(
    *,
    source_stream_id: str,
    generation: int,
    prior: tuple[str | None, str | None],
    sequence: int,
    fork_marker: str,
) -> tuple[EPCheckpointAdvance, EPCheckpointAdvance]:
    authority_source = (fork_marker + "a" * 64)[:64]
    register_source = (fork_marker + "b" * 64)[:64]
    required_as_of = date(2026, 7, 27)
    batch = build_ep_snapshot_checkpoint_batch_sha256(
        source_stream_id=source_stream_id,
        schema_epoch=1,
        authority_subject="1234567",
        register_subject="EP1234567",
        required_as_of=required_as_of,
        authority_checkpoint_generation=generation,
        register_checkpoint_generation=generation,
        authority_prior_checkpoint_envelope_sha256=prior[0],
        register_prior_checkpoint_envelope_sha256=prior[1],
        authority_minimum_snapshot_sequence=sequence,
        register_minimum_snapshot_sequence=sequence,
        authority_source_acquisition_envelope_sha256=authority_source,
        register_source_acquisition_envelope_sha256=register_source,
    )

    def make(manifest_type: str) -> EPCheckpointAdvance:
        authority = manifest_type == "authority"
        receipt = EPSignedSnapshotHighWaterReceipt(
            envelope_version="praviar-epo-high-water-envelope-v1",
            source_stream_id=source_stream_id,
            schema_epoch=1,
            manifest_type=manifest_type,
            subject="1234567" if authority else "EP1234567",
            required_as_of=required_as_of,
            checkpoint_batch_sha256=batch,
            checkpoint_generation=generation,
            counterpart_source_acquisition_envelope_sha256=(
                register_source if authority else authority_source
            ),
            prior_checkpoint_envelope_sha256=prior[0 if authority else 1],
            minimum_snapshot_sequence=sequence,
            source_acquisition_envelope_sha256=(authority_source if authority else register_source),
            signing_key_id=f"live-{manifest_type}-checkpoint-v1",
            key_revocation_epoch=0,
            signed_at=datetime(2026, 7, 27, 12, tzinfo=UTC),
            signature=(b"\x41" if authority else b"\x42") * 64,
        )
        return EPCheckpointAdvance(
            checkpoint=receipt,
            checkpoint_envelope_sha256=build_ep_snapshot_checkpoint_envelope_sha256(receipt),
            source_snapshot_sequence=sequence,
        )

    return make("authority"), make("register")


async def test_two_connections_restart_and_competing_fork_are_atomic() -> None:
    if os.getenv("RUN_POSTGRES_EPO_CHECKPOINT_TESTS") != "1":
        pytest.skip("set RUN_POSTGRES_EPO_CHECKPOINT_TESTS=1 for the live race proof")
    if os.getenv("EPO_CHECKPOINT_TEST_DATABASE_DISPOSABLE") != "1":
        pytest.fail("live EPO race proof requires an explicitly disposable database")
    url = os.getenv("EPO_CHECKPOINT_TEST_DATABASE_URL")
    if not url:
        pytest.fail("EPO_CHECKPOINT_TEST_DATABASE_URL is required for the live race proof")

    source_stream_id = f"epo-race-{uuid4().hex}"
    engines = [
        create_async_engine(url, isolation_level="SERIALIZABLE", pool_pre_ping=True)
        for _ in range(3)
    ]
    stores = [
        PostgresEPAtomicCheckpointStore(
            engine,
            key_provider=_UnusedKeyProvider(),
            source_stream_id=source_stream_id,
            schema_epoch=1,
        )
        for engine in engines
    ]
    try:
        first = _advances(
            source_stream_id=source_stream_id,
            generation=1,
            prior=(None, None),
            sequence=10,
            fork_marker="0",
        )
        first_results = await asyncio.gather(
            stores[0].compare_and_advance_atomic(first),
            stores[1].compare_and_advance_atomic(first),
        )
        assert sorted(result.status for result in first_results) == [
            "advanced",
            "idempotent",
        ]

        restarted = await stores[2].compare_and_advance_atomic(first)
        assert restarted.status == "idempotent"

        prior = (
            first[0].checkpoint_envelope_sha256,
            first[1].checkpoint_envelope_sha256,
        )
        fork_a = _advances(
            source_stream_id=source_stream_id,
            generation=2,
            prior=prior,
            sequence=11,
            fork_marker="1",
        )
        fork_b = _advances(
            source_stream_id=source_stream_id,
            generation=2,
            prior=prior,
            sequence=11,
            fork_marker="2",
        )
        fork_results = await asyncio.gather(
            stores[0].compare_and_advance_atomic(fork_a),
            stores[1].compare_and_advance_atomic(fork_b),
        )
        assert sorted(result.status for result in fork_results) == [
            "advanced",
            "rejected",
        ]

        async with engines[2].connect() as connection:
            current = (
                await connection.execute(
                    text(
                        """
                        SELECT checkpoint_generation, checkpoint_batch_sha256
                        FROM epo_atomic_checkpoints
                        WHERE source_stream_id = :source_stream_id
                          AND schema_epoch = 1
                        ORDER BY manifest_type
                        """
                    ),
                    {"source_stream_id": source_stream_id},
                )
            ).all()
            history_count = (
                await connection.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM epo_atomic_checkpoint_history
                        WHERE source_stream_id = :source_stream_id
                          AND schema_epoch = 1
                        """
                    ),
                    {"source_stream_id": source_stream_id},
                )
            ).scalar_one()
        assert len(current) == 2
        assert {row.checkpoint_generation for row in current} == {2}
        assert len({row.checkpoint_batch_sha256 for row in current}) == 1
        assert history_count == 4

        with pytest.raises(DBAPIError):
            async with engines[2].begin() as connection:
                await connection.execute(
                    text(
                        """
                        UPDATE epo_atomic_checkpoints
                        SET checkpoint_generation = checkpoint_generation + 2
                        WHERE source_stream_id = :source_stream_id
                          AND schema_epoch = 1
                          AND manifest_type = 'authority'
                        """
                    ),
                    {"source_stream_id": source_stream_id},
                )
    finally:
        await asyncio.gather(*(engine.dispose() for engine in engines))
