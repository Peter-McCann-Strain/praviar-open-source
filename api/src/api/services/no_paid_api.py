"""No-credit guards for live provider paths."""

from __future__ import annotations

import os
from collections.abc import Mapping

_TRUTHY = {"1", "true", "yes", "on"}


class PaidApiBlockedError(RuntimeError):
    """Raised when a live paid provider path is used in no-credit mode."""


def no_paid_api_enabled(env: Mapping[str, str] | None = None) -> bool:
    values = env if env is not None else os.environ
    return values.get("NO_PAID_API", "").strip().lower() in _TRUTHY


def assert_paid_api_allowed(provider: str) -> None:
    if no_paid_api_enabled():
        raise PaidApiBlockedError(
            f"NO_PAID_API=true blocks live {provider} calls. "
            "Inject a mock client or run the paid lane explicitly."
        )
