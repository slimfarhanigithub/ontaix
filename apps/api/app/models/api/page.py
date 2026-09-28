"""One page of a large list: `{ items, page, pageSize, total }`."""

from __future__ import annotations

from app.models.api.base import ApiModel


class PageOf[T](ApiModel):
    items: list[T]
    page: int
    page_size: int
    total: int
