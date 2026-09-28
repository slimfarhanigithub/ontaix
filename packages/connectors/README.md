# Ontaix Connectors

Read-only connector SDK, Python 3.12 managed by uv. Python is used so the API can import the same source and record types later.

A connector exposes exactly two operations: `discover()` returns the objects and attributes a source has, and `read(object_name, limit)` yields records from one of them. There is no write path by contract; `tests/test_connector_is_read_only.py` fails if a write-like member is ever added to the `Connector` protocol.

## Layout

```text
ontaix_connectors/
  connector.py     Connector protocol, SourceObject, Attribute, Record
tests/
  test_connector_is_read_only.py
```

## Run Locally

```bash
uv sync
uv run pytest
uv run ruff check
```
