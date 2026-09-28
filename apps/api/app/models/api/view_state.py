"""Shared canvas view state DTO."""

from __future__ import annotations

from pydantic import Field

from app.models.api.base import ApiModel


class ViewState(ApiModel):
    coverage: bool
    scene_idx: int = Field(ge=0)
