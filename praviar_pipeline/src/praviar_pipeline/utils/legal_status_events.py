"""Fail-closed legal-status event ordering and replay."""

from __future__ import annotations

from datetime import date, datetime

from praviar_pipeline.models.patent_lineage import LegalStatus

_FINAL_EVENT_STATUSES = {
    "GRANT": LegalStatus.ACTIVE,
    "B1": LegalStatus.ACTIVE,
    "B2": LegalStatus.ACTIVE,
    "REINSTATED_FINAL": LegalStatus.ACTIVE,
    "RESTORED_FINAL": LegalStatus.ACTIVE,
    "LAPSED_FINAL": LegalStatus.LAPSED,
    "REVOKED_FINAL": LegalStatus.REVOKED,
    "EXPIRED_FINAL": LegalStatus.EXPIRED,
    "WITHDRAWN_FINAL": LegalStatus.LAPSED,
    "PENDING_CONFIRMED": LegalStatus.PENDING,
}
_STATUS_BEARING_TOKENS = (
    "abandon",
    "expir",
    "grant",
    "lapse",
    "pending",
    "reinstat",
    "restor",
    "revok",
    "withdraw",
)


def derive_legal_status_from_events(events: list[dict]) -> LegalStatus:
    """Derive status from the latest unambiguous dated status-bearing event."""
    observations: list[tuple[date, LegalStatus]] = []
    unresolved_status_dates: list[date] = []
    for event in events or []:
        if not isinstance(event, dict):
            return LegalStatus.UNKNOWN
        status = _event_status(event)
        if status is None:
            if not _looks_status_bearing(event):
                continue
            unresolved_date = _parse_event_date(event.get("event_date"))
            if unresolved_date is None:
                return LegalStatus.UNKNOWN
            unresolved_status_dates.append(unresolved_date)
            continue
        event_date = _parse_event_date(event.get("event_date"))
        if event_date is None:
            return LegalStatus.UNKNOWN
        observations.append((event_date, status))
    if not observations:
        return LegalStatus.UNKNOWN
    latest_date = max(event_date for event_date, _status in observations)
    if any(event_date >= latest_date for event_date in unresolved_status_dates):
        return LegalStatus.UNKNOWN
    latest_statuses = {status for event_date, status in observations if event_date == latest_date}
    if len(latest_statuses) != 1:
        return LegalStatus.UNKNOWN
    return next(iter(latest_statuses))


def _event_status(event: dict) -> LegalStatus | None:
    code = str(event.get("event_code") or "").strip().upper()
    return _FINAL_EVENT_STATUSES.get(code)


def _looks_status_bearing(event: dict) -> bool:
    description = str(event.get("event_description") or "").strip().lower()
    code = str(event.get("event_code") or "").strip().lower()
    text = f"{code} {description}"
    return any(token in text for token in _STATUS_BEARING_TOKENS)


def _parse_event_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if len(text) == 8 and text.isdigit():
            return datetime.strptime(text, "%Y%m%d").date()
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


__all__ = ["derive_legal_status_from_events"]
