"""Shared freshness rules for authoritative SSO status."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

SSO_STATUS_MAX_AGE = timedelta(minutes=5)


def sso_status_is_fresh(
    *,
    available: bool,
    last_synced_at: datetime | None,
    now: datetime | None = None,
) -> bool:
    """Return whether SSO state is authoritative and recent enough to act on."""
    if (
        not available
        or last_synced_at is None
        or last_synced_at.tzinfo is None
        or last_synced_at.utcoffset() is None
    ):
        return False
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        return False
    age = current_time - last_synced_at
    return timedelta(0) <= age <= SSO_STATUS_MAX_AGE
