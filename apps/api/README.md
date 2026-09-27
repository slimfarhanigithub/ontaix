# Ontaix API

Python 3.12 FastAPI modular monolith managed by uv. It is the only process that writes to the ontology store; every write is a proposal that a human approves or rejects.

## Layout

```text
app/
  main.py          FastAPI entry point: builds the app and mounts routers
  config.py        single pydantic-settings Settings class, env prefix ONTAIX_
  routers/
    health.py      GET /healthz -> {"status": "ok"}
tests/
  test_health.py
```

## Planned Module Boundaries

The following module packages are future work and do not exist yet. Each becomes a folder under `app/` with its own routers, services and repositories: `ontology` (companies, domain products, concepts, relations, equivalences, versioning), `proposals` (propose, approve, reject, cascade, events), `identity` (OIDC login, native groups and roles, permissions), `bindings` (sources, discovery, bindings, coverage, lineage), `audit` (audit log).

## Conventions

- Absolute imports from `app.` only; ruff bans relative imports.
- Built-in generics (`list[str]`, `str | None`), never `typing.List` or `Optional`.
- Module file order: docstring, imports, logger, constants, public symbols, private helpers.
- `__init__.py` files stay empty.

## Run Locally

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8000
uv run pytest
uv run ruff check
```
