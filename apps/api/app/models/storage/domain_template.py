"""Storage mapping for the `domain_template` reference table."""

from __future__ import annotations

from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base


class DomainTemplate(Base):
    __tablename__ = "domain_template"

    key: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    owner: Mapped[str]
    color: Mapped[str]
    position: Mapped[int] = mapped_column(Integer)
