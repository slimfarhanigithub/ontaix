"""Shared canvas view state DTO."""

from __future__ import annotations

from app.models.api.base import ApiModel


class ViewState(ApiModel):
    coverage: bool
