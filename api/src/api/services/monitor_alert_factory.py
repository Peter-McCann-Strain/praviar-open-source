"""Construct ``MonitorAlert`` rows from a computed run delta."""

from __future__ import annotations

from datetime import datetime

from api.db.models import Monitor, MonitorAlert
from api.services.monitor_delta_computation import MonitorRunDelta, severity_for_delta


def build_monitor_alert(
    monitor: Monitor,
    *,
    delta: MonitorRunDelta,
    summary: str,
    run_mode: str,
    run_at: datetime,
) -> MonitorAlert:
    """Build (but do not persist) a ``MonitorAlert`` for the given delta.

    Caller is responsible for adding to the session and flushing — keeping
    DB orchestration out of this factory makes the alert shape easy to
    unit-test in isolation.
    """
    return MonitorAlert(
        org_id=monitor.org_id,
        monitor_id=monitor.id,
        alert_type=(
            "conclusion_review_required"
            if delta.affected_conclusions
            else ("new_patent_delta" if delta.new_patent_ids else "monitor_event_delta")
        ),
        severity=severity_for_delta(delta),
        summary=summary,
        strategy_mode=run_mode,
        new_patent_ids=delta.new_patent_ids,
        new_event_ids=delta.new_event_ids,
        jurisdiction_deltas=delta.jurisdiction_deltas,
        affected_conclusions=delta.affected_conclusions,
        new_patent_count=len(delta.new_patent_ids),
        run_at=run_at,
    )


def alert_warranted(*, previous_snapshot: dict, delta: MonitorRunDelta) -> bool:
    """Decide whether this run produced an alertable change.

    Bootstrap runs (no previous snapshot) never alert — they only seed the
    baseline. Subsequent runs alert iff there is at least one new patent or
    new event.
    """
    if not previous_snapshot:
        return False
    return bool(delta.new_patent_ids or delta.new_event_ids)
