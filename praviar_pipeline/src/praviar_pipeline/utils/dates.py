"""Date parsing utilities for patent and scholarly API responses."""

from __future__ import annotations

from datetime import date, datetime


def parse_date(date_str: str | None) -> date | None:
    """Parse date strings from various API formats.

    Supports: ISO 8601 (2024-01-15), compact (20240115),
              US slash (01/15/2024), YYYY/MM/DD (2024/01/15).
    Returns None for unparseable or missing values.
    """
    if not date_str:
        return None
    cleaned = str(date_str).strip()[:10]
    try:
        return date.fromisoformat(cleaned)
    except (ValueError, TypeError):
        pass
    for fmt in ("%Y%m%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None
