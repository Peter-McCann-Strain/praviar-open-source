"""Deterministic EPO checkpoint CAS tests.

These pure tests exercise classification only. They are not presented as live
PostgreSQL, transaction-isolation, or restart evidence.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from praviar_pipeline.clients.epo_publication_server import EPCheckpointAdvance
from praviar_pipeline.models.epo_publication import (
    EP_CHECKPOINT_SCHEMA_EPOCH,
    EP_CHECKPOINT_SOURCE_STREAM_ID,
    EPSignedSnapshotHighWaterReceipt,
    build_ep_snapshot_checkpoint_batch_sha256,
    build_ep_snapshot_checkpoint_envelope_sha256,
)

from api.db.epo_checkpoint_store import (
    _CheckpointState,
    _classify_batch,
    _validate_candidate_pair,
)

AUTHORITY_SUBJECT = "1234567"
REGISTER_SUBJECT = "EP1234567"
AS_OF = date(2026, 7, 27)


def _advances(
    *,
    generation: int = 1,
    prior: tuple[str | None, str | None] = (None, None),
    snapshot_sequence: int = 10,
    minimum_snapshot_sequence: int = 10,
    required_as_of: date = AS_OF,
    source_stream_id: str = EP_CHECKPOINT_SOURCE_STREAM_ID,
    schema_epoch: int = EP_CHECKPOINT_SCHEMA_EPOCH,
    authority_source: str = "a" * 64,
    register_source: str = "b" * 64,
) -> tuple[EPCheckpointAdvance, EPCheckpointAdvance]:
    batch = build_ep_snapshot_checkpoint_batch_sha256(
        source_stream_id=source_stream_id,
        schema_epoch=schema_epoch,
        authority_subject=AUTHORITY_SUBJECT,
        register_subject=REGISTER_SUBJECT,
        required_as_of=required_as_of,
        authority_checkpoint_generation=generation,
        register_checkpoint_generation=generation,
        authority_prior_checkpoint_envelope_sha256=prior[0],
        register_prior_checkpoint_envelope_sha256=prior[1],
        authority_minimum_snapshot_sequence=minimum_snapshot_sequence,
        register_minimum_snapshot_sequence=minimum_snapshot_sequence,
        authority_source_acquisition_envelope_sha256=authority_source,
        register_source_acquisition_envelope_sha256=register_source,
    )

    def make(manifest_type: str) -> EPCheckpointAdvance:
        is_authority = manifest_type == "authority"
        receipt = EPSignedSnapshotHighWaterReceipt(
            envelope_version="praviar-epo-high-water-envelope-v1",
            source_stream_id=source_stream_id,
            schema_epoch=schema_epoch,
            manifest_type=manifest_type,
            subject=AUTHORITY_SUBJECT if is_authority else REGISTER_SUBJECT,
            required_as_of=required_as_of,
            checkpoint_batch_sha256=batch,
            checkpoint_generation=generation,
            counterpart_source_acquisition_envelope_sha256=(
                register_source if is_authority else authority_source
            ),
            prior_checkpoint_envelope_sha256=prior[0 if is_authority else 1],
            minimum_snapshot_sequence=minimum_snapshot_sequence,
            source_acquisition_envelope_sha256=(
                authority_source if is_authority else register_source
            ),
            signing_key_id=(
                "test-authority-checkpoint-v1" if is_authority else "test-register-checkpoint-v1"
            ),
            key_revocation_epoch=0,
            signed_at=datetime(2026, 7, 27, 12, tzinfo=UTC),
            signature=(b"\x31" if is_authority else b"\x32") * 64,
        )
        return EPCheckpointAdvance(
            checkpoint=receipt,
            checkpoint_envelope_sha256=build_ep_snapshot_checkpoint_envelope_sha256(receipt),
            source_snapshot_sequence=snapshot_sequence,
        )

    return make("authority"), make("register")


def _states(
    advances: tuple[EPCheckpointAdvance, EPCheckpointAdvance],
) -> tuple[_CheckpointState, _CheckpointState]:
    return tuple(_CheckpointState.from_advance(value) for value in advances)  # type: ignore[return-value]


def _current(
    states: tuple[_CheckpointState, _CheckpointState],
) -> dict[str, _CheckpointState]:
    return {state.manifest_type: state for state in states}


def test_initial_pair_advances_and_exact_restart_replay_is_idempotent() -> None:
    candidates = _states(_advances())

    assert _classify_batch({}, candidates) == "advanced"
    assert _classify_batch(_current(candidates), candidates) == "idempotent"


def test_next_generation_requires_both_exact_predecessor_digests() -> None:
    first = _states(_advances())
    second = _states(
        _advances(
            generation=2,
            prior=(
                first[0].checkpoint_envelope_sha256,
                first[1].checkpoint_envelope_sha256,
            ),
            snapshot_sequence=11,
            minimum_snapshot_sequence=11,
        )
    )

    assert _classify_batch(_current(first), second) == "advanced"

    wrong_prior = _states(
        _advances(
            generation=2,
            prior=("f" * 64, first[1].checkpoint_envelope_sha256),
            snapshot_sequence=11,
            minimum_snapshot_sequence=11,
        )
    )
    assert _classify_batch(_current(first), wrong_prior) == "rejected"


def test_torn_persisted_state_and_mixed_idempotent_advance_are_rejected() -> None:
    first = _states(_advances())
    assert _classify_batch({"authority": first[0]}, first) == "rejected"

    second = _states(
        _advances(
            generation=2,
            prior=(
                first[0].checkpoint_envelope_sha256,
                first[1].checkpoint_envelope_sha256,
            ),
            snapshot_sequence=11,
            minimum_snapshot_sequence=11,
        )
    )
    mixed = first[0], second[1]
    assert _classify_batch(_current(first), mixed) == "rejected"


def test_sequence_as_of_generation_and_minimum_floor_cannot_move_backwards() -> None:
    first = _states(_advances())
    prior = (
        first[0].checkpoint_envelope_sha256,
        first[1].checkpoint_envelope_sha256,
    )

    for candidate in (
        _states(_advances(generation=3, prior=prior, snapshot_sequence=12)),
        _states(_advances(generation=2, prior=prior, snapshot_sequence=10)),
        _states(
            _advances(
                generation=2,
                prior=prior,
                snapshot_sequence=11,
                minimum_snapshot_sequence=9,
            )
        ),
        _states(
            _advances(
                generation=2,
                prior=prior,
                snapshot_sequence=11,
                required_as_of=date(2026, 7, 26),
            )
        ),
    ):
        assert _classify_batch(_current(first), candidate) == "rejected"


def test_candidate_pair_is_bound_to_configured_stream_epoch_and_causal_subject() -> None:
    advances = _advances(source_stream_id="other-stream", schema_epoch=2)
    assert (
        _validate_candidate_pair(
            advances,
            source_stream_id=EP_CHECKPOINT_SOURCE_STREAM_ID,
            schema_epoch=EP_CHECKPOINT_SCHEMA_EPOCH,
        )
        is None
    )

    authority, register = _advances()
    tampered_register = register.model_copy(
        update={"checkpoint": register.checkpoint.model_copy(update={"subject": "EP7654321"})}
    )
    assert (
        _validate_candidate_pair(
            (authority, tampered_register),
            source_stream_id=EP_CHECKPOINT_SOURCE_STREAM_ID,
            schema_epoch=EP_CHECKPOINT_SCHEMA_EPOCH,
        )
        is None
    )


def test_candidate_pair_recomputes_batch_and_envelope_digests() -> None:
    authority, register = _advances()
    assert (
        _validate_candidate_pair(
            (
                authority.model_copy(update={"checkpoint_envelope_sha256": "f" * 64}),
                register,
            ),
            source_stream_id=EP_CHECKPOINT_SOURCE_STREAM_ID,
            schema_epoch=EP_CHECKPOINT_SCHEMA_EPOCH,
        )
        is None
    )

    tampered_authority = authority.model_copy(
        update={
            "checkpoint": authority.checkpoint.model_copy(
                update={"checkpoint_batch_sha256": "e" * 64}
            )
        }
    )
    assert (
        _validate_candidate_pair(
            (tampered_authority, register),
            source_stream_id=EP_CHECKPOINT_SOURCE_STREAM_ID,
            schema_epoch=EP_CHECKPOINT_SCHEMA_EPOCH,
        )
        is None
    )
