"""The shared list convention: `page`, `pageSize`, `q`, `filter[field]=a,b`, `sort`, `order`."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from app.utilities.problems import bad_request

FILTER_KEY = re.compile(r"^filter\[(\w+)\]$")
DEFAULT_PAGE_SIZE = 40
MAX_PAGE_SIZE = 200


@dataclass(frozen=True)
class ListQuery:
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE
    q: str | None = None
    filters: dict[str, list[str]] = field(default_factory=dict)
    sort: str | None = None
    order: str = "asc"


def parse_list_query(
    params: Mapping[str, str],
    filterable: Iterable[str],
    sortable: Iterable[str],
) -> ListQuery:
    """Read the list parameters, refusing unknown filter and sort fields with 400."""
    filterable_set, sortable_set = set(filterable), set(sortable)
    filters: dict[str, list[str]] = {}
    for key, value in params.items():
        match = FILTER_KEY.match(key)
        if match is None:
            continue
        name = match.group(1)
        if name not in filterable_set:
            raise bad_request(f"unknown filter field: {name}")
        filters[name] = [v.strip() for v in value.split(",") if v.strip()]
    sort = params.get("sort")
    if sort is not None and sort not in sortable_set:
        raise bad_request(f"unknown sort field: {sort}")
    order = params.get("order", "asc")
    if order not in {"asc", "desc"}:
        raise bad_request("order must be asc or desc")
    page = _int_param(params, "page", 1)
    page_size = _int_param(params, "pageSize", DEFAULT_PAGE_SIZE)
    if page < 1:
        raise bad_request("page must be at least 1")
    if not 1 <= page_size <= MAX_PAGE_SIZE:
        raise bad_request(f"pageSize must be between 1 and {MAX_PAGE_SIZE}")
    q = params.get("q") or None
    return ListQuery(page=page, page_size=page_size, q=q, filters=filters, sort=sort, order=order)


def paginate[T](
    items: list[T],
    query: ListQuery,
    sort_keys: Mapping[str, Callable[[T], Any]],
    default_sort: str,
) -> tuple[list[T], int]:
    """Sort in memory with the named key and slice one page; returns the page and the total."""
    key = sort_keys[query.sort or default_sort]
    ordered = sorted(items, key=lambda item: _sortable(key(item)), reverse=query.order == "desc")
    start = (query.page - 1) * query.page_size
    return ordered[start : start + query.page_size], len(ordered)


def matches_search(q: str | None, *values: str | None) -> bool:
    """Case-insensitive containment over the list's search keys."""
    if not q:
        return True
    needle = q.lower()
    return any(v is not None and needle in v.lower() for v in values)


def _int_param(params: Mapping[str, str], name: str, default: int) -> int:
    raw = params.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise bad_request(f"{name} must be an integer") from exc


def _sortable(value: Any) -> Any:
    if isinstance(value, str):
        return value.lower()
    return value
