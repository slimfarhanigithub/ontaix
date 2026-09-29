"""Database access for the `concept_expansion` table: stored model suggestions.

The submit claim is one conditional `UPDATE ... RETURNING` run inside the caller's transaction:
zero rows returned means the claim failed, so two concurrent submits can never both succeed.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.concept_expansion import ConceptExpansion


async def create(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    company_id: uuid.UUID,
    concept_id: uuid.UUID,
    session_id: uuid.UUID | None,
    depth: int | None,
    max_children: int | None,
    drafts: list[dict[str, Any]],
    notes: list[dict[str, Any]],
) -> ConceptExpansion:
    """Store one expansion; `created_at` and `expires_at` come from the database defaults."""
    row = ConceptExpansion(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        company_id=company_id,
        concept_id=concept_id,
        session_id=session_id,
        depth=depth,
        max_children=max_children,
        draft_count=len(drafts),
        drafts=drafts,
        notes=notes,
    )
    session.add(row)
    await session.flush()
    return row


async def get(
    session: AsyncSession, tenant_id: uuid.UUID, expansion_id: uuid.UUID
) -> ConceptExpansion | None:
    return await session.scalar(
        select(ConceptExpansion).where(
            ConceptExpansion.tenant_id == tenant_id, ConceptExpansion.id == expansion_id
        )
    )


async def claim_submit(
    session: AsyncSession, tenant_id: uuid.UUID, expansion_id: uuid.UUID
) -> bool:
    """Mark the expansion submitted unless it was submitted already or has expired."""
    claimed = await session.scalar(
        update(ConceptExpansion)
        .where(
            ConceptExpansion.tenant_id == tenant_id,
            ConceptExpansion.id == expansion_id,
            ConceptExpansion.submitted_at.is_(None),
            ConceptExpansion.expires_at > func.now(),
        )
        .values(submitted_at=func.now())
        .execution_options(synchronize_session=False)
        .returning(ConceptExpansion.id)
    )
    return claimed is not None


async def delete_expired_before(session: AsyncSession, cutoff: datetime) -> int:
    result = await session.execute(
        delete(ConceptExpansion).where(ConceptExpansion.expires_at < cutoff)
    )
    return result.rowcount or 0
