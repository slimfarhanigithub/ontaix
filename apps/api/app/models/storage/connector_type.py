"""Storage mapping for the `connector_type` reference table."""

from __future__ import annotations

from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base


class ConnectorType(Base):
    __tablename__ = "connector_type"

    code: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    category: Mapped[str]
    scope_text: Mapped[str]
    position: Mapped[int] = mapped_column(Integer)
