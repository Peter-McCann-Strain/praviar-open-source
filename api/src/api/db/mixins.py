"""Reusable SQLAlchemy mixin classes shared across ORM models.

The :class:`TimestampMixin` consolidates the ``created_at`` / ``updated_at``
columns that previously appeared (with identical definitions) on roughly a
dozen models.  Mixing it in is purely a deduplication: the resulting columns
have the exact same DDL — ``DateTime(timezone=True)`` with
``server_default=now()`` and (for ``updated_at``) ``onupdate=now()`` — so the
change is database-compatible and requires no migration.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """Adds ``created_at`` and ``updated_at`` timestamp columns.

    Both columns use a server-side ``now()`` default; ``updated_at`` is
    refreshed automatically on every UPDATE via ``onupdate``.  Models that
    intentionally lack ``updated_at`` (append-only audit tables, idempotency
    logs, etc.) should NOT use this mixin.
    """

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
