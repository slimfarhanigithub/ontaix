"""Database access for the `document_import_sentence` table.

The parse counter and the draft claim are single conditional `UPDATE ... RETURNING` statements
run inside the caller's transaction: zero rows returned means the claim failed, so two
concurrent calls can never both succeed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.document_import_sentence import DocumentImportSentence

MAX_PARSES = 3


@dataclass(frozen=True)
class SentenceRow:
    text: str
    position_unit: str | None
    position_index: int | None
    position_row: int | None = None


async def create_many(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    import_id: uuid.UUID,
    sentences: list[tuple[str, str | None, int | None, int | None]],
) -> None:
    """Insert the sentences of one import in document order: `(text, unit, index, row)` each."""
    if not sentences:
        return
    await session.execute(
        insert(DocumentImportSentence),
        [
            {
                "tenant_id": tenant_id,
                "import_id": import_id,
                "sentence_index": i,
                "text": text,
                "position_unit": unit,
                "position_index": index,
                "position_row": row,
            }
            for i, (text, unit, index, row) in enumerate(sentences)
        ],
    )


async def exists(
    session: AsyncSession, tenant_id: uuid.UUID, import_id: uuid.UUID, sentence_index: int
) -> bool:
    found = await session.scalar(
        select(DocumentImportSentence.sentence_index).where(
            *_key(tenant_id, import_id, sentence_index)
        )
    )
    return found is not None


async def texts_between(
    session: AsyncSession, tenant_id: uuid.UUID, import_id: uuid.UUID, first: int, last: int
) -> dict[int, str]:
    """The texts of the import's sentences with an index from `first` to `last`."""
    result = await session.execute(
        select(DocumentImportSentence.sentence_index, DocumentImportSentence.text).where(
            DocumentImportSentence.tenant_id == tenant_id,
            DocumentImportSentence.import_id == import_id,
            DocumentImportSentence.sentence_index.between(first, last),
        )
    )
    return {int(index): text for index, text in result.all()}


async def claim_parse(
    session: AsyncSession, tenant_id: uuid.UUID, import_id: uuid.UUID, sentence_index: int
) -> SentenceRow | None:
    """Count one parse of the sentence unless it was parsed `MAX_PARSES` times already."""
    row = (
        await session.execute(
            update(DocumentImportSentence)
            .where(
                *_key(tenant_id, import_id, sentence_index),
                DocumentImportSentence.parse_count < MAX_PARSES,
            )
            .values(parse_count=DocumentImportSentence.parse_count + 1)
            .execution_options(synchronize_session=False)
            .returning(
                DocumentImportSentence.text,
                DocumentImportSentence.position_unit,
                DocumentImportSentence.position_index,
                DocumentImportSentence.position_row,
            )
        )
    ).first()
    return SentenceRow(*row) if row else None


async def claim_draft(
    session: AsyncSession, tenant_id: uuid.UUID, import_id: uuid.UUID, sentence_index: int
) -> SentenceRow | None:
    """Mark the sentence drafted unless an earlier call drafted it already."""
    row = (
        await session.execute(
            update(DocumentImportSentence)
            .where(
                *_key(tenant_id, import_id, sentence_index),
                DocumentImportSentence.drafted_at.is_(None),
            )
            .values(drafted_at=func.now())
            .execution_options(synchronize_session=False)
            .returning(
                DocumentImportSentence.text,
                DocumentImportSentence.position_unit,
                DocumentImportSentence.position_index,
                DocumentImportSentence.position_row,
            )
        )
    ).first()
    return SentenceRow(*row) if row else None


def _key(tenant_id: uuid.UUID, import_id: uuid.UUID, sentence_index: int) -> tuple:
    return (
        DocumentImportSentence.tenant_id == tenant_id,
        DocumentImportSentence.import_id == import_id,
        DocumentImportSentence.sentence_index == sentence_index,
    )
