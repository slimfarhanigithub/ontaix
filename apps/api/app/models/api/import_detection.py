"""Response of `POST /import/detect`."""

from __future__ import annotations

from typing import Literal

from app.models.api.base import ApiModel
from app.models.api.origin import ImportMediaType
from app.models.ontology_import.parsed_ontology import OntologyFormat


class ImportDetection(ApiModel):
    kind: Literal["document", "ontology"]
    # The ontology format when `kind` is ontology, else None.
    format: OntologyFormat | None
    # The document media type the bytes read as, for reading the file as a document.
    media_type: ImportMediaType
