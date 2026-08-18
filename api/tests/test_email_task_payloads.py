from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from api.workers.email_task_payloads import (
    build_analysis_complete_send_kwargs,
    build_monitor_alert_send_kwargs,
    build_weekly_digest_send_kwargs,
    build_welcome_send_kwargs,
    map_email_task_result,
    weekly_digest_cutoff,
)


def test_build_analysis_complete_send_kwargs_uses_expected_fallbacks():
    user = SimpleNamespace(
        email="user@example.com",
        full_name="",
        role="attorney",
    )
    analysis = SimpleNamespace(
        compound_name="",
        compound_input="C" * 80,
        overall_risk=None,
    )

    payload = build_analysis_complete_send_kwargs(
        user=user,
        analysis=analysis,
        analysis_id="analysis-1",
    )

    assert payload == {
        "user_email": "user@example.com",
        "user_name": "user@example.com",
        "analysis_id": "analysis-1",
        "compound_name": "C" * 50,
        "risk_level": "UNKNOWN",
        "report_cta_label": "View Full Report",
        "report_url": "/analyses/analysis-1/report",
        "risk_restricted": False,
    }


def test_build_analysis_complete_send_kwargs_hides_governed_risk():
    user = SimpleNamespace(
        email="scientist@example.com",
        full_name="Scientist",
        role="scientist",
    )
    analysis = SimpleNamespace(
        compound_name="aspirin",
        compound_input="aspirin",
        overall_risk="HIGH",
    )

    payload = build_analysis_complete_send_kwargs(
        user=user,
        analysis=analysis,
        analysis_id="analysis-2",
    )

    assert payload["risk_level"] == "COUNSEL ONLY"
    assert payload["compound_name"] == "Governed analysis"
    assert payload["report_cta_label"] == "View Governed Summary"
    assert payload["report_url"] == "/analyses/analysis-2/report/summary"
    assert payload["risk_restricted"] is True


def test_build_monitor_alert_send_kwargs_uses_expected_fallbacks():
    user = SimpleNamespace(email="user@example.com", full_name=None)
    monitor = SimpleNamespace(
        id="monitor-1",
        compound_name="",
        compound_smiles="N" * 80,
    )
    alert = SimpleNamespace(
        new_patent_count=3,
        new_event_ids=["US123:assignment:2026-07-23"],
    )

    payload = build_monitor_alert_send_kwargs(
        user=user,
        monitor=monitor,
        alert=alert,
    )

    assert payload == {
        "user_email": "user@example.com",
        "user_name": "user@example.com",
        "compound_name": "N" * 30,
        "new_patent_count": 3,
        "new_event_ids": ["US123:assignment:2026-07-23"],
        "monitor_url": "/monitors",
    }


def test_build_welcome_send_kwargs_uses_email_fallback():
    user = SimpleNamespace(email="user@example.com", full_name="")

    payload = build_welcome_send_kwargs(user=user)

    assert payload == {
        "user_email": "user@example.com",
        "user_name": "user@example.com",
        "role": "client",
    }


def test_build_weekly_digest_send_kwargs_includes_counts_and_risks():
    user = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        email="user@example.com",
        full_name="Ada",
    )
    payload = build_weekly_digest_send_kwargs(
        user=user,
        analyses_completed=4,
        alerts_count=2,
        top_risks=[{"compound_name": "aspirin", "risk_level": "HIGH"}],
        unsubscribe_token="du1." + "t" * 86,
    )

    assert payload == {
        "user_email": "user@example.com",
        "user_name": "Ada",
        "analyses_completed": 4,
        "alerts_count": 2,
        "top_risks": [{"compound_name": "aspirin", "risk_level": "HIGH"}],
        "risk_restricted": False,
        "unsubscribe_token": payload["unsubscribe_token"],
    }
    assert len(payload["unsubscribe_token"]) >= 80


def test_build_weekly_digest_send_kwargs_hides_risks_for_restricted_role():
    user = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        email="scientist@example.com",
        full_name="Scientist",
    )

    payload = build_weekly_digest_send_kwargs(
        user=user,
        analyses_completed=4,
        alerts_count=2,
        top_risks=[{"compound_name": "aspirin", "risk_level": "HIGH"}],
        unsubscribe_token="du1." + "t" * 86,
        risk_restricted=True,
    )

    assert payload["top_risks"] == []
    assert payload["risk_restricted"] is True


def test_map_email_task_result_normalizes_client_response():
    result = SimpleNamespace(success=True, message_id="msg-1", error=None)

    assert map_email_task_result(result) == {
        "status": "sent",
        "message_id": "msg-1",
        "error": None,
    }


def test_weekly_digest_cutoff_uses_provided_time():
    now = datetime(2026, 4, 13, 12, tzinfo=UTC)

    assert weekly_digest_cutoff(now) == datetime(2026, 4, 6, 9, tzinfo=UTC)


def test_weekly_digest_cutoff_does_not_open_current_period_before_monday_schedule():
    now = datetime(2026, 4, 13, 8, 59, tzinfo=UTC)

    assert weekly_digest_cutoff(now) == datetime(2026, 3, 30, 9, tzinfo=UTC)
