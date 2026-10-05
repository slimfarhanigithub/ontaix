"""Storage mapping for the `tenant_settings` table."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Text, Uuid, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.storage.base import Base, RefreshInterval, ThemeName, pg_enum


class TenantSettings(Base):
    __tablename__ = "tenant_settings"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenant.id", ondelete="CASCADE"), primary_key=True
    )
    theme: Mapped[ThemeName] = mapped_column(
        pg_enum(ThemeName, "theme_name"), server_default=text("'light'")
    )
    colors: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    accent: Mapped[str] = mapped_column(server_default=text("'#d30c55'"))
    source_colour: Mapped[str] = mapped_column(server_default=text("'#d6bd8a'"))
    voice: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    import_docs: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    live_teaching: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    everyone_teaches: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    approval_required: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    two_approvers: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    auto_attrs: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    notify_owners: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    multi_company: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    company_creation: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    cross_company: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    animations: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    coverage_default: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    legend: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    read_only_connectors: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    refresh: Mapped[RefreshInterval] = mapped_column(
        pg_enum(RefreshInterval, "refresh_interval"), server_default=text("'15 min'")
    )
    agent_access: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    cost_cap: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    llm_monthly_token_cap: Mapped[int] = mapped_column(BigInteger, server_default=text("2000000"))
    ocr_monthly_page_cap: Mapped[int] = mapped_column(Integer, server_default=text("1000"))
    egress_allowlist: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
