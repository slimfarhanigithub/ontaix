"""Database access for the `document_import` table."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.base import ActorKind
from app.models.storage.document_import import DocumentImport


async def create(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    file_name: str,
    media_type: str,
    sha256: bytes,
    sentence_count: int,
    extracted_chars: int,
) -> DocumentImport:
    """Store one import; `created_at` and `expires_at` come from the database defaults."""
    row = DocumentImport(
        tenant_id=tenant_id,
        actor_kind=ActorKind.USER,
        actor_user_id=actor_user_id,
        file_name=file_name,
        media_type=media_type,
        sha256=sha256,
        sentence_count=sentence_count,
        extracted_chars=extracted_chars,
    )
    session.add(row)
    await session.flush()
    return row


async def get(
    session: AsyncSession, tenant_id: uuid.UUID, import_id: uuid.UUID
) -> DocumentImport | None:
    return await session.scalar(
        select(DocumentImport).where(
            DocumentImport.tenant_id == tenant_id, DocumentImport.id == import_id
        )
    )


async def delete_expired_before(session: AsyncSession, cutoff: datetime) -> int:
    """Delete every import whose `expires_at` is older than `cutoff`; sentences cascade."""
    result = await session.execute(delete(DocumentImport).where(DocumentImport.expires_at < cutoff))
    return result.rowcount or 0
