"""The Connector protocol must expose read operations only."""

from __future__ import annotations

import re

from ontaix_connectors.connector import Connector

WRITE_LIKE = re.compile(
    r"(write|insert|update|upsert|delete|remove|create|drop|truncate|alter|put|patch|post|"
    r"save|store|commit|execute|mutate|set_)",
    re.IGNORECASE,
)


def _public_members(protocol: type) -> set[str]:
    annotated = set(getattr(protocol, "__annotations__", {}))
    callables = {
        name
        for name, value in vars(protocol).items()
        if callable(value) and not name.startswith("_")
    }
    return annotated | callables


def test_connector_exposes_discover_and_read() -> None:
    assert {"discover", "read"} <= _public_members(Connector)


def test_connector_exposes_no_write_like_member() -> None:
    offenders = [name for name in _public_members(Connector) if WRITE_LIKE.search(name)]

    assert offenders == []
