"""Runs document extraction in a child process with a wall-clock limit and a memory cap.

The child returns the document's text blocks and, for a PDF, its image-only pages; sentences
are split once any recognised page text is in place. Slots, limits and refusals are those of
`child_process_service`.
"""

from __future__ import annotations

import logging

from app.services import child_process_service
from app.utilities.document_text import ExtractedDocument, extract_document

logger = logging.getLogger(__name__)

EXTRACTION_TIMEOUT_SECONDS = 20.0


async def extract(data: bytes, media_type: str) -> ExtractedDocument:
    """The text blocks of a document, read in a child process.

    Raises `DocumentTooLargeError` past a limit or past `EXTRACTION_TIMEOUT_SECONDS`,
    `DocumentUnreadableError` when the document cannot be read, and `503 busy` when every
    reading slot is taken.
    """
    return await child_process_service.run(
        extract_document, (data, media_type), EXTRACTION_TIMEOUT_SECONDS, f"a {media_type} document"
    )
