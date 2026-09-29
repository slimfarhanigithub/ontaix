"""Database access for the `ontology_import` table.

The submit claim is one conditional `UPDATE ... RETURNING` inside the caller's transaction: zero
rows returned means the claim failed, so two concurrent submissions can never both succeed.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.base import ActorKind
from app.models.storage.ontology_import import OntologyImport


async def create(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    company_id: uuid.UUID,
    parent_concept_id: uuid.UUID | None,
    file_name: str,
    format: str,
    sha256: bytes,
    languages: list[str],
    individuals: str,
    drafts: list[dict[str, Any]],
    notes: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
) -> OntologyImport:
    """Store one mapped tree; `created_at` and `expires_at` come from the database defaults."""
    row = OntologyImport(
        tenant_id=tenant_id,
        actor_kind=ActorKind.USER,
        actor_user_id=actor_user_id,
        company_id=company_id,
        parent_concept_id=parent_concept_id,
        file_name=file_name,
        format=format,
        sha256=sha256,
        languages=languages,
        individuals=individuals,
        draft_count=len(drafts),
        drafts=drafts,
        notes=notes,
        skipped=skipped,
    )
    session.add(row)
    await session.flush()
    return row


async def get(
    session: AsyncSession, tenant_id: uuid.UUID, import_id: uuid.UUID
) -> OntologyImport | None:
    return await session.scalar(
        select(OntologyImport).where(
            OntologyImport.tenant_id == tenant_id, OntologyImport.id == import_id
        )
    )


async def claim_submission(
    session: AsyncSession, tenant_id: uuid.UUID, import_id: uuid.UUID
) -> bool:
    """Mark the import submitted unless it was submitted already or has expired."""
    claimed = await session.scalar(
        update(OntologyImport)
        .where(
            OntologyImport.tenant_id == tenant_id,
            OntologyImport.id == import_id,
            OntologyImport.submitted_at.is_(None),
            OntologyImport.expires_at > func.now(),
        )
        .values(submitted_at=func.now())
        .execution_options(synchronize_session=False)
        .returning(OntologyImport.id)
    )
    return claimed is not None


async def delete_expired_before(session: AsyncSession, cutoff: datetime) -> int:
    """Delete every ontology import whose `expires_at` is older than `cutoff`."""
    result = await session.execute(delete(OntologyImport).where(OntologyImport.expires_at < cutoff))
    return result.rowcount or 0
