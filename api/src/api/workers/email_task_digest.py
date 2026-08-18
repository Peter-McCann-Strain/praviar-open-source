"""Digest helper functions for email worker tasks."""

from __future__ import annotations

from typing import Any, Protocol


class DigestAnalysis(Protocol):
    compound_name: str | None
    compound_input: str
    overall_risk: str | None


def weekly_digest_enabled(preferences: dict[str, Any] | None) -> bool:
    """Return whether a user's preferences opt into the weekly digest."""
    prefs = preferences or {}
    return bool(prefs.get("email_digest_frequency", "weekly") == "weekly")


def build_top_risks_payload(analyses: list[DigestAnalysis]) -> list[dict[str, str]]:
    """Serialize top-risk analyses into the email payload shape."""
    return [
        {
            "compound_name": analysis.compound_name or analysis.compound_input[:40],
            "risk_level": analysis.overall_risk or "UNKNOWN",
        }
        for analysis in analyses
    ]
