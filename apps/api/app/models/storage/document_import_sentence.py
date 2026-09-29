"""Storage mapping for the `document_import_sentence` table."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKeyConstraint, Integer, SmallInteger, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base


class DocumentImportSentence(Base):
    __tablename__ = "document_import_sentence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "import_id"],
            ["document_import.tenant_id", "document_import.id"],
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    import_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    sentence_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str]
    position_unit: Mapped[str | None]
    position_index: Mapped[int | None] = mapped_column(Integer)
    position_row: Mapped[int | None] = mapped_column(Integer)
    parse_count: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    drafted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
