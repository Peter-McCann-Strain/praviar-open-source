"""Shared pagination and lookup helpers for admin query services."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select


def build_page_window(page: int, per_page: int) -> tuple[int, int]:
    """Return the offset/limit pair for a paginated query."""
    return (page - 1) * per_page, per_page


async def execute_paged_query(
    db: AsyncSession,
    *,
    base_query: Select[Any],
    count_query: Select[Any],
    order_by: Any,
    page: int,
    per_page: int,
) -> tuple[int, list[Any]]:
    """Execute a count query and paged list query using a shared window."""
    offset, limit = build_page_window(page, per_page)
    total = (await db.execute(count_query)).scalar_one()
    rows = (
        (await db.execute(base_query.order_by(order_by).offset(offset).limit(limit)))
        .scalars()
        .all()
    )
    return int(total), list(rows)


async def load_id_map(
    db: AsyncSession,
    *,
    model: Any,
    id_column: Any,
    value_column: Any,
    ids: set[Any],
) -> dict[Any, Any]:
    """Load a simple ID-to-value mapping for a given model and ID set."""
    if not ids:
        return {}
    result = await db.execute(select(id_column, value_column).where(id_column.in_(ids)))
    return {row[0]: row[1] for row in result.all()}
