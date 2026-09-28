"""Connector catalogue DTO."""

from __future__ import annotations

from app.models.api.base import ApiModel


class ConnectorType(ApiModel):
    code: str
    name: str
    category: str
    scope_text: str
