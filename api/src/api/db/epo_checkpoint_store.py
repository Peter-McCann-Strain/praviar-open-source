"""Durable PostgreSQL implementation of the EPO two-row checkpoint CAS."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal, Protocol, cast

from praviar_pipeline.clients.epo_publication_server import (
    EPCheckpointAdvance,
    EPCheckpointBatchResult,
)
from praviar_pipeline.models.epo_publication import (
    EPTrustedAcquisitionKey,
    build_ep_snapshot_checkpoint_batch_sha256,
    build_ep_snapshot_checkpoint_envelope_sha256,
)
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

_SOURCE_STREAM_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_RETRYABLE_SQLSTATES = frozenset({"40001", "40P01"})
_MAX_SERIALIZATION_ATTEMPTS = 3

_SELECT_CURRENT = text(
    """
    SELECT
        source_stream_id,
        schema_epoch,
        manifest_type,
        canonical_subject,
        required_as_of,
        checkpoint_generation,
        checkpoint_envelope_sha256,
        prior_checkpoint_envelope_sha256,
        source_snapshot_sequence,
        minimum_snapshot_sequence,
        source_acquisition_envelope_sha256,
        counterpart_source_acquisition_envelope_sha256,
        checkpoint_batch_sha256,
        signing_key_id,
        key_revocation_epoch,
        signed_at,
        checkpoint_signature
    FROM epo_atomic_checkpoints
    WHERE source_stream_id = :source_stream_id
      AND schema_epoch = :schema_epoch
      AND (
          (manifest_type = 'authority' AND canonical_subject = :authority_subject)
          OR
          (manifest_type = 'register' AND canonical_subject = :register_subject)
      )
    ORDER BY manifest_type, canonical_subject
    FOR UPDATE
    """
)

_INSERT_CURRENT = text(
    """
    INSERT INTO epo_atomic_checkpoints (
        source_stream_id,
        schema_epoch,
        manifest_type,
        canonical_subject,
        required_as_of,
        checkpoint_generation,
        checkpoint_envelope_sha256,
        prior_checkpoint_envelope_sha256,
        source_snapshot_sequence,
        minimum_snapshot_sequence,
        source_acquisition_envelope_sha256,
        counterpart_source_acquisition_envelope_sha256,
        checkpoint_batch_sha256,
        signing_key_id,
        key_revocation_epoch,
        signed_at,
        checkpoint_signature
    ) VALUES (
        :source_stream_id,
        :schema_epoch,
        :manifest_type,
        :canonical_subject,
        :required_as_of,
        :checkpoint_generation,
        :checkpoint_envelope_sha256,
        :prior_checkpoint_envelope_sha256,
        :source_snapshot_sequence,
        :minimum_snapshot_sequence,
        :source_acquisition_envelope_sha256,
        :counterpart_source_acquisition_envelope_sha256,
        :checkpoint_batch_sha256,
        :signing_key_id,
        :key_revocation_epoch,
        :signed_at,
        :checkpoint_signature
    )
    """
)

_UPDATE_CURRENT = text(
    """
    UPDATE epo_atomic_checkpoints
    SET
        required_as_of = :required_as_of,
        checkpoint_generation = :checkpoint_generation,
        checkpoint_envelope_sha256 = :checkpoint_envelope_sha256,
        prior_checkpoint_envelope_sha256 = :prior_checkpoint_envelope_sha256,
        source_snapshot_sequence = :source_snapshot_sequence,
        minimum_snapshot_sequence = :minimum_snapshot_sequence,
        source_acquisition_envelope_sha256 = :source_acquisition_envelope_sha256,
        counterpart_source_acquisition_envelope_sha256 =
            :counterpart_source_acquisition_envelope_sha256,
        checkpoint_batch_sha256 = :checkpoint_batch_sha256,
        signing_key_id = :signing_key_id,
        key_revocation_epoch = :key_revocation_epoch,
        signed_at = :signed_at,
        checkpoint_signature = :checkpoint_signature,
        updated_at = transaction_timestamp()
    WHERE source_stream_id = :source_stream_id
      AND schema_epoch = :schema_epoch
      AND manifest_type = :manifest_type
      AND canonical_subject = :canonical_subject
      AND checkpoint_generation = :expected_checkpoint_generation
      AND checkpoint_envelope_sha256 = :expected_checkpoint_envelope_sha256
      AND source_snapshot_sequence = :expected_source_snapshot_sequence
      AND required_as_of = :expected_required_as_of
      AND checkpoint_batch_sha256 = :expected_checkpoint_batch_sha256
    """
)

_INSERT_HISTORY = text(
    """
    INSERT INTO epo_atomic_checkpoint_history (
        source_stream_id,
        schema_epoch,
        manifest_type,
        canonical_subject,
        required_as_of,
        checkpoint_generation,
        checkpoint_envelope_sha256,
        prior_checkpoint_envelope_sha256,
        source_snapshot_sequence,
        minimum_snapshot_sequence,
        source_acquisition_envelope_sha256,
        counterpart_source_acquisition_envelope_sha256,
        checkpoint_batch_sha256,
        signing_key_id,
        key_revocation_epoch,
        signed_at,
        checkpoint_signature
    ) VALUES (
        :source_stream_id,
        :schema_epoch,
        :manifest_type,
        :canonical_subject,
        :required_as_of,
        :checkpoint_generation,
        :checkpoint_envelope_sha256,
        :prior_checkpoint_envelope_sha256,
        :source_snapshot_sequence,
        :minimum_snapshot_sequence,
        :source_acquisition_envelope_sha256,
        :counterpart_source_acquisition_envelope_sha256,
        :checkpoint_batch_sha256,
        :signing_key_id,
        :key_revocation_epoch,
        :signed_at,
        :checkpoint_signature
    )
    """
)


class EPCheckpointKeyProvider(Protocol):
    async def load_trusted_checkpoint_keys(
        self,
    ) -> Mapping[str, EPTrustedAcquisitionKey]: ...


@dataclass(frozen=True, slots=True)
class _CheckpointState:
    source_stream_id: str
    schema_epoch: int
    manifest_type: Literal["authority", "register"]
    canonical_subject: str
    required_as_of: date
    checkpoint_generation: int
    checkpoint_envelope_sha256: str
    prior_checkpoint_envelope_sha256: str | None
    source_snapshot_sequence: int
    minimum_snapshot_sequence: int
    source_acquisition_envelope_sha256: str
    counterpart_source_acquisition_envelope_sha256: str
    checkpoint_batch_sha256: str
    signing_key_id: str
    key_revocation_epoch: int
    signed_at: datetime
    checkpoint_signature: bytes

    @classmethod
    def from_advance(cls, advance: EPCheckpointAdvance) -> _CheckpointState:
        checkpoint = advance.checkpoint
        return cls(
            source_stream_id=checkpoint.source_stream_id,
            schema_epoch=checkpoint.schema_epoch,
            manifest_type=checkpoint.manifest_type,
            canonical_subject=checkpoint.subject,
            required_as_of=checkpoint.required_as_of,
            checkpoint_generation=checkpoint.checkpoint_generation,
            checkpoint_envelope_sha256=advance.checkpoint_envelope_sha256,
            prior_checkpoint_envelope_sha256=checkpoint.prior_checkpoint_envelope_sha256,
            source_snapshot_sequence=advance.source_snapshot_sequence,
            minimum_snapshot_sequence=checkpoint.minimum_snapshot_sequence,
            source_acquisition_envelope_sha256=(checkpoint.source_acquisition_envelope_sha256),
            counterpart_source_acquisition_envelope_sha256=(
                checkpoint.counterpart_source_acquisition_envelope_sha256
            ),
            checkpoint_batch_sha256=checkpoint.checkpoint_batch_sha256,
            signing_key_id=checkpoint.signing_key_id,
            key_revocation_epoch=checkpoint.key_revocation_epoch,
            signed_at=checkpoint.signed_at,
            checkpoint_signature=checkpoint.signature,
        )

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any] | RowMapping) -> _CheckpointState:
        manifest_type = str(row["manifest_type"])
        if manifest_type not in {"authority", "register"}:
            raise ValueError("persisted EPO checkpoint has an invalid manifest type")
        return cls(
            source_stream_id=str(row["source_stream_id"]),
            schema_epoch=int(row["schema_epoch"]),
            manifest_type=cast(Literal["authority", "register"], manifest_type),
            canonical_subject=str(row["canonical_subject"]),
            required_as_of=row["required_as_of"],
            checkpoint_generation=int(row["checkpoint_generation"]),
            checkpoint_envelope_sha256=str(row["checkpoint_envelope_sha256"]),
            prior_checkpoint_envelope_sha256=(
                str(row["prior_checkpoint_envelope_sha256"])
                if row["prior_checkpoint_envelope_sha256"] is not None
                else None
            ),
            source_snapshot_sequence=int(row["source_snapshot_sequence"]),
            minimum_snapshot_sequence=int(row["minimum_snapshot_sequence"]),
            source_acquisition_envelope_sha256=str(row["source_acquisition_envelope_sha256"]),
            counterpart_source_acquisition_envelope_sha256=str(
                row["counterpart_source_acquisition_envelope_sha256"]
            ),
            checkpoint_batch_sha256=str(row["checkpoint_batch_sha256"]),
            signing_key_id=str(row["signing_key_id"]),
            key_revocation_epoch=int(row["key_revocation_epoch"]),
            signed_at=row["signed_at"],
            checkpoint_signature=bytes(row["checkpoint_signature"]),
        )

    def parameters(self) -> dict[str, object]:
        return {
            "source_stream_id": self.source_stream_id,
            "schema_epoch": self.schema_epoch,
            "manifest_type": self.manifest_type,
            "canonical_subject": self.canonical_subject,
            "required_as_of": self.required_as_of,
            "checkpoint_generation": self.checkpoint_generation,
            "checkpoint_envelope_sha256": self.checkpoint_envelope_sha256,
            "prior_checkpoint_envelope_sha256": self.prior_checkpoint_envelope_sha256,
            "source_snapshot_sequence": self.source_snapshot_sequence,
            "minimum_snapshot_sequence": self.minimum_snapshot_sequence,
            "source_acquisition_envelope_sha256": self.source_acquisition_envelope_sha256,
            "counterpart_source_acquisition_envelope_sha256": (
                self.counterpart_source_acquisition_envelope_sha256
            ),
            "checkpoint_batch_sha256": self.checkpoint_batch_sha256,
            "signing_key_id": self.signing_key_id,
            "key_revocation_epoch": self.key_revocation_epoch,
            "signed_at": self.signed_at,
            "checkpoint_signature": self.checkpoint_signature,
        }


def _rejected() -> EPCheckpointBatchResult:
    return EPCheckpointBatchResult(
        status="rejected",
        persisted_checkpoint_envelope_sha256=(),
    )


def _validate_candidate_pair(
    advances: tuple[EPCheckpointAdvance, EPCheckpointAdvance],
    *,
    source_stream_id: str,
    schema_epoch: int,
) -> tuple[_CheckpointState, _CheckpointState] | None:
    candidates = tuple(_CheckpointState.from_advance(advance) for advance in advances)
    authority, register = candidates
    expected_batch_sha256 = build_ep_snapshot_checkpoint_batch_sha256(
        source_stream_id=authority.source_stream_id,
        schema_epoch=authority.schema_epoch,
        authority_subject=authority.canonical_subject,
        register_subject=register.canonical_subject,
        required_as_of=authority.required_as_of,
        authority_checkpoint_generation=authority.checkpoint_generation,
        register_checkpoint_generation=register.checkpoint_generation,
        authority_prior_checkpoint_envelope_sha256=(authority.prior_checkpoint_envelope_sha256),
        register_prior_checkpoint_envelope_sha256=(register.prior_checkpoint_envelope_sha256),
        authority_minimum_snapshot_sequence=authority.minimum_snapshot_sequence,
        register_minimum_snapshot_sequence=register.minimum_snapshot_sequence,
        authority_source_acquisition_envelope_sha256=(authority.source_acquisition_envelope_sha256),
        register_source_acquisition_envelope_sha256=(register.source_acquisition_envelope_sha256),
    )
    if (
        authority.manifest_type != "authority"
        or register.manifest_type != "register"
        or authority.source_stream_id != source_stream_id
        or register.source_stream_id != source_stream_id
        or authority.schema_epoch != schema_epoch
        or register.schema_epoch != schema_epoch
        or register.canonical_subject != f"EP{authority.canonical_subject}"
        or authority.required_as_of != register.required_as_of
        or authority.checkpoint_batch_sha256 != expected_batch_sha256
        or register.checkpoint_batch_sha256 != expected_batch_sha256
        or any(
            advance.checkpoint_envelope_sha256
            != build_ep_snapshot_checkpoint_envelope_sha256(advance.checkpoint)
            for advance in advances
        )
        or authority.counterpart_source_acquisition_envelope_sha256
        != register.source_acquisition_envelope_sha256
        or register.counterpart_source_acquisition_envelope_sha256
        != authority.source_acquisition_envelope_sha256
        or authority.signing_key_id == register.signing_key_id
    ):
        return None
    return authority, register


def _classify_batch(
    current: Mapping[Literal["authority", "register"], _CheckpointState],
    candidates: tuple[_CheckpointState, _CheckpointState],
) -> Literal["advanced", "idempotent", "rejected"]:
    if len(current) not in {0, 2}:
        return "rejected"
    if len(current) == 0:
        if all(
            candidate.checkpoint_generation == 1
            and candidate.prior_checkpoint_envelope_sha256 is None
            for candidate in candidates
        ):
            return "advanced"
        return "rejected"

    authority_current = current["authority"]
    register_current = current["register"]
    if (
        authority_current.checkpoint_batch_sha256 != register_current.checkpoint_batch_sha256
        or authority_current.required_as_of != register_current.required_as_of
        or register_current.canonical_subject != f"EP{authority_current.canonical_subject}"
    ):
        return "rejected"

    exact = tuple(current[candidate.manifest_type] == candidate for candidate in candidates)
    if all(exact):
        return "idempotent"
    if any(exact):
        return "rejected"

    for candidate in candidates:
        persisted = current[candidate.manifest_type]
        if (
            candidate.checkpoint_generation != persisted.checkpoint_generation + 1
            or candidate.prior_checkpoint_envelope_sha256 != persisted.checkpoint_envelope_sha256
            or candidate.source_snapshot_sequence <= persisted.source_snapshot_sequence
            or candidate.minimum_snapshot_sequence < persisted.minimum_snapshot_sequence
            or candidate.required_as_of < persisted.required_as_of
        ):
            return "rejected"
    return "advanced"


def _db_sqlstate(exc: DBAPIError) -> str | None:
    original = exc.orig
    return getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)


class PostgresEPAtomicCheckpointStore:
    """Serializable, restart-safe atomic authority/Register checkpoint store."""

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        key_provider: EPCheckpointKeyProvider,
        source_stream_id: str,
        schema_epoch: int,
    ) -> None:
        if engine.url.get_backend_name() != "postgresql":
            raise ValueError("EPO checkpoint persistence requires PostgreSQL")
        if not _SOURCE_STREAM_RE.fullmatch(source_stream_id):
            raise ValueError("EPO checkpoint source stream id is invalid")
        if schema_epoch < 1:
            raise ValueError("EPO checkpoint schema epoch must be positive")
        self._engine = engine
        self._key_provider = key_provider
        self._source_stream_id = source_stream_id
        self._schema_epoch = schema_epoch

    async def load_trusted_checkpoint_keys(
        self,
    ) -> Mapping[str, EPTrustedAcquisitionKey]:
        return await self._key_provider.load_trusted_checkpoint_keys()

    async def compare_and_advance_atomic(
        self,
        advances: tuple[EPCheckpointAdvance, EPCheckpointAdvance],
    ) -> EPCheckpointBatchResult:
        candidates = _validate_candidate_pair(
            advances,
            source_stream_id=self._source_stream_id,
            schema_epoch=self._schema_epoch,
        )
        if candidates is None:
            return _rejected()
        for attempt in range(_MAX_SERIALIZATION_ATTEMPTS):
            try:
                return await self._compare_and_advance_once(candidates)
            except DBAPIError as exc:
                if (
                    _db_sqlstate(exc) not in _RETRYABLE_SQLSTATES
                    or attempt == _MAX_SERIALIZATION_ATTEMPTS - 1
                ):
                    raise
                await asyncio.sleep(0)
        raise AssertionError("unreachable serialization retry state")

    async def _compare_and_advance_once(
        self,
        candidates: tuple[_CheckpointState, _CheckpointState],
    ) -> EPCheckpointBatchResult:
        authority, register = candidates
        query_parameters = {
            "source_stream_id": self._source_stream_id,
            "schema_epoch": self._schema_epoch,
            "authority_subject": authority.canonical_subject,
            "register_subject": register.canonical_subject,
        }
        lock_identities = sorted(
            f"{self._source_stream_id}:{self._schema_epoch}:"
            f"{candidate.manifest_type}:{candidate.canonical_subject}"
            for candidate in candidates
        )
        async with (
            self._engine.connect() as connection,
            connection.begin(),
        ):
            # This must be the first statement in the transaction.
            await connection.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
            # Transaction advisory locks protect absent rows; SELECT FOR
            # UPDATE below protects rows that already exist. Stable ordering
            # prevents pairwise deadlocks.
            for lock_identity in lock_identities:
                await connection.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_identity, 0))"),
                    {"lock_identity": lock_identity},
                )
            rows = (await connection.execute(_SELECT_CURRENT, query_parameters)).mappings()
            current = {
                state.manifest_type: state
                for state in (_CheckpointState.from_mapping(row) for row in rows)
            }
            decision = _classify_batch(current, candidates)
            if decision == "rejected":
                return _rejected()
            if decision == "advanced":
                for candidate in candidates:
                    await connection.execute(_INSERT_HISTORY, candidate.parameters())
                for candidate in candidates:
                    persisted = current.get(candidate.manifest_type)
                    if persisted is None:
                        await connection.execute(_INSERT_CURRENT, candidate.parameters())
                        continue
                    parameters = candidate.parameters()
                    parameters.update(
                        {
                            "expected_checkpoint_generation": (persisted.checkpoint_generation),
                            "expected_checkpoint_envelope_sha256": (
                                persisted.checkpoint_envelope_sha256
                            ),
                            "expected_source_snapshot_sequence": (
                                persisted.source_snapshot_sequence
                            ),
                            "expected_required_as_of": persisted.required_as_of,
                            "expected_checkpoint_batch_sha256": (persisted.checkpoint_batch_sha256),
                        }
                    )
                    result = await connection.execute(_UPDATE_CURRENT, parameters)
                    if result.rowcount != 1:
                        raise RuntimeError("EPO checkpoint CAS lost its locked predecessor")
            return EPCheckpointBatchResult(
                status=decision,
                persisted_checkpoint_envelope_sha256=tuple(
                    candidate.checkpoint_envelope_sha256 for candidate in candidates
                ),
                persisted_checkpoint_batch_sha256=authority.checkpoint_batch_sha256,
            )


__all__ = [
    "EPCheckpointKeyProvider",
    "PostgresEPAtomicCheckpointStore",
]
