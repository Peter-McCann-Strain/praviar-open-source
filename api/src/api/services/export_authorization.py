"""Shared role-and-format authorization policy for report exports."""

from __future__ import annotations

from api.db.models import ExportFormat, UserRole

_FULL_REPORT_EXPORT_ROLES = frozenset(
    {
        UserRole.ADMIN,
        UserRole.ATTORNEY,
        UserRole.SCIENTIST,
    }
)
_SCIENTIST_EXPORT_FORMATS = frozenset(
    {
        ExportFormat.PDF,
        ExportFormat.JSON,
        ExportFormat.CSV,
        ExportFormat.XLSX,
    }
)


def is_export_format_allowed_for_role(
    role: UserRole,
    export_format: ExportFormat,
) -> bool:
    """Return whether the current role may render this full-report format."""
    if role not in _FULL_REPORT_EXPORT_ROLES:
        return False
    if role == UserRole.SCIENTIST:
        return export_format in _SCIENTIST_EXPORT_FORMATS
    return True
