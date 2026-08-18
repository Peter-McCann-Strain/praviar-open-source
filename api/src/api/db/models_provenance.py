"""Global provenance persistence models."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Integer,
    LargeBinary,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .models_base import Base


def _checkpoint_table_args(prefix: str) -> tuple[CheckConstraint, ...]:
    return (
        CheckConstraint(
            "source_stream_id ~ '^[a-z0-9][a-z0-9._-]{2,127}$'",
            name=f"ck_{prefix}_source_stream",
        ),
        CheckConstraint("schema_epoch >= 1", name=f"ck_{prefix}_schema_epoch"),
        CheckConstraint(
            "manifest_type IN ('authority', 'register')",
            name=f"ck_{prefix}_manifest_type",
        ),
        CheckConstraint(
            "(manifest_type = 'authority' AND canonical_subject ~ '^[0-9]{7}$') OR "
            "(manifest_type = 'register' AND canonical_subject ~ '^EP[0-9]{7}$')",
            name=f"ck_{prefix}_subject",
        ),
        CheckConstraint(
            "checkpoint_generation >= 1 "
            "AND source_snapshot_sequence >= minimum_snapshot_sequence "
            "AND minimum_snapshot_sequence >= 1 "
            "AND key_revocation_epoch >= 0",
            name=f"ck_{prefix}_positive_counters",
        ),
        CheckConstraint(
            "(checkpoint_generation = 1) = (prior_checkpoint_envelope_sha256 IS NULL)",
            name=f"ck_{prefix}_lineage",
        ),
    )


class _EPOCheckpointColumns:
    source_stream_id: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest_type: Mapped[str] = mapped_column(String(16), nullable=False)
    canonical_subject: Mapped[str] = mapped_column(String(9), nullable=False)
    required_as_of: Mapped[date] = mapped_column(Date, nullable=False)
    checkpoint_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checkpoint_envelope_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    prior_checkpoint_envelope_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    source_snapshot_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    minimum_snapshot_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_acquisition_envelope_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    counterpart_source_acquisition_envelope_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    checkpoint_batch_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    signing_key_id: Mapped[str] = mapped_column(String(64), nullable=False)
    key_revocation_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    checkpoint_signature: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class EPOAtomicCheckpoint(_EPOCheckpointColumns, Base):
    """Current durable high-water state; advanced only as an atomic pair."""

    __tablename__ = "epo_atomic_checkpoints"
    __table_args__ = (
        PrimaryKeyConstraint(
            "source_stream_id",
            "schema_epoch",
            "manifest_type",
            "canonical_subject",
            name="pk_epo_atomic_checkpoints",
        ),
        UniqueConstraint(
            "source_stream_id",
            "schema_epoch",
            "manifest_type",
            "checkpoint_batch_sha256",
            name="uq_epo_atomic_checkpoints_manifest_batch",
        ),
        *_checkpoint_table_args("epo_atomic_checkpoints"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class EPOAtomicCheckpointHistory(_EPOCheckpointColumns, Base):
    """Append-only evidence for every accepted two-row advance."""

    __tablename__ = "epo_atomic_checkpoint_history"
    __table_args__ = (
        PrimaryKeyConstraint(
            "source_stream_id",
            "schema_epoch",
            "manifest_type",
            "canonical_subject",
            "checkpoint_generation",
            name="pk_epo_atomic_checkpoint_history",
        ),
        UniqueConstraint(
            "source_stream_id",
            "schema_epoch",
            "manifest_type",
            "checkpoint_batch_sha256",
            name="uq_epo_atomic_checkpoint_history_manifest_batch",
        ),
        UniqueConstraint(
            "source_stream_id",
            "schema_epoch",
            "manifest_type",
            "canonical_subject",
            "checkpoint_envelope_sha256",
            name="uq_epo_atomic_checkpoint_history_envelope",
        ),
        *_checkpoint_table_args("epo_atomic_checkpoint_history"),
    )

    persisted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


__all__ = ["EPOAtomicCheckpoint", "EPOAtomicCheckpointHistory"]
