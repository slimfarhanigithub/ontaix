"""The refusals of reading an uploaded file, shared by document import and ontology import."""

from __future__ import annotations


class DocumentTooLargeError(Exception):
    """The document passes one of the import limits (`413`)."""


class DocumentUnreadableError(Exception):
    """The document is not a readable file of its media type (`422`)."""


class UnsupportedDocumentError(Exception):
    """The bytes are a kind of file that is never read, or disagree with the declared type
    (`415`)."""
