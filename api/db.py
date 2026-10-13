# ════════════════════════════════════════════════════════════════════════
#  db.py — read ALL matching rows from Supabase
#
#  Supabase (PostgREST) returns at most 1,000 rows per request, silently.
#  Every list query must go through fetch_all(), which asks page by page
#  (ordered by id, the sheet's row order) until a short page comes back.
# ════════════════════════════════════════════════════════════════════════

from __future__ import annotations

from typing import Callable

PAGE = 1000


def fetch_all(make_query: Callable, order: str | None = "id") -> list[dict]:
    """make_query() must return a NEW query builder each call (filters applied, no range).
    Rows come back in `order` order (default: id = original sheet order)."""
    rows: list[dict] = []
    start = 0
    while True:
        q = make_query()
        if order:
            q = q.order(order)
        page = q.range(start, start + PAGE - 1).execute().data or []
        rows.extend(page)
        if len(page) < PAGE:
            return rows
        start += PAGE


def first_value(make_query: Callable, column: str, desc: bool = False):
    """Smallest (or largest) non-null value of a column — one row, no paging needed."""
    data = make_query().not_.is_(column, 'null').order(column, desc=desc).limit(1).execute().data or []
    return data[0][column] if data else ''
