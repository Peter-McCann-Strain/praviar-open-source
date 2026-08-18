"""Maintenance fee status helpers for deterministic patent term calculation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from datetime import date

_FINAL_MAINTENANCE_LAPSE_DESCRIPTIONS = frozenset(
    {
        "patent expired due to failure to pay maintenance fee",
        "patent lapsed due to non-payment of maintenance fee",
    }
)
_FINAL_MAINTENANCE_LAPSE_CODES = frozenset({"EXP", "LAPS"})


def _check_maintenance_fee_lapse(
    legal_events: list[dict],
) -> tuple[Literal["paid", "lapsed", "grace_period", "unknown"], date | None]:
    """Retain only an explicit final maintenance-lapse disposition."""
    for evt in reversed(legal_events):
        desc = " ".join(str(evt.get("event_description", "")).strip().casefold().split())
        code = str(evt.get("event_code", "")).strip().upper()
        if code in _FINAL_MAINTENANCE_LAPSE_CODES and desc in _FINAL_MAINTENANCE_LAPSE_DESCRIPTIONS:
            return "lapsed", evt.get("event_date")

    return "unknown", None


def resolve_maintenance_status(
    *,
    app_data: dict,
    legal_events: list[dict] | None,
) -> tuple[Literal["paid", "lapsed", "grace_period", "unknown"], date | None, list[str], float]:
    """Detect an explicit lapse; current payment always requires Storefront evidence."""
    notes: list[str] = []
    confidence_delta = 0.0
    maint_status: Literal["paid", "lapsed", "grace_period", "unknown"] = "unknown"
    maint_next_due: date | None = None

    events = list(app_data.get("eventDataBag", []) or [])
    for evt in reversed(events):
        code = str(evt.get("eventCode", "")).strip().upper()
        desc = " ".join(str(evt.get("eventDescriptionText", "")).strip().casefold().split())
        if code in _FINAL_MAINTENANCE_LAPSE_CODES and desc in _FINAL_MAINTENANCE_LAPSE_DESCRIPTIONS:
            maint_status = "lapsed"
            evt_date_str = evt.get("eventDate", "")
            if evt_date_str:
                notes.append(f"Maintenance fee lapsed (USPTO event: {evt_date_str})")
            break

    if maint_status == "unknown" and legal_events:
        maint_status, lapse_date = _check_maintenance_fee_lapse(legal_events)
        maint_next_due = lapse_date
        if maint_status == "lapsed":
            notes.append(
                "Maintenance fee lapsed (INPADOC)"
                + (f" on {lapse_date.isoformat()}" if lapse_date else "")
            )

    return maint_status, maint_next_due, notes, confidence_delta
