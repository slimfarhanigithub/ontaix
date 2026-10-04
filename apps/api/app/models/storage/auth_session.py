"""Storage mapping for the `auth_session` table: a server-side browser session.

Only the SHA-256 of the cookie token is stored, never the token itself.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, Uuid, text
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base, SessionEndReason, pg_enum


class AuthSession(Base):
    __tablename__ = "auth_session"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary)
    csrf_token: Mapped[str]
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("account.id", ondelete="CASCADE")
    )
    support_tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tenant.id", ondelete="CASCADE")
    )
    support_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acting_tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tenant.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_reason: Mapped[SessionEndReason | None] = mapped_column(
        pg_enum(SessionEndReason, "session_end_reason")
    )
    client_ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None]

    def __repr__(self) -> str:
        return f"AuthSession(id={self.id!r}, account_id={self.account_id!r})"
