"""Read-only connector contract.

A connector lets Ontaix look at an external source in two ways only: discover the objects and
attributes the source exposes, and read records from one of those objects. There is no write,
update or delete path in this contract, and connectors must not add one; the read-only rule is
enforced by a test in this package.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

Record = dict[str, object]
"""One row or document read from a source object, keyed by attribute name."""


class Attribute(BaseModel):
    """A discovered attribute (column, field) of a source object."""

    name: str
    type_name: str
    nullable: bool = True


class SourceObject(BaseModel):
    """A discovered object (table, view, collection, file) in an external source."""

    name: str
    attributes: list[Attribute] = Field(default_factory=list)
    record_count: int | None = None


@runtime_checkable
class Connector(Protocol):
    """Read-only access to one external source.

    Implementations expose exactly two operations: discover and read. Nothing in this contract
    can change the source.
    """

    name: str

    def discover(self) -> list[SourceObject]:
        """Return the objects and attributes the source exposes."""
        ...

    def read(self, object_name: str, limit: int | None = None) -> Iterator[Record]:
        """Yield records from one discovered object, stopping after `limit` if given."""
        ...
