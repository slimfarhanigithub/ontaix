# Ontaix Gateway

Python 3.12 FastAPI service managed by uv. It exposes the ontology to agents over MCP: read and propose, never write. Every agent proposal enters the same approval queue as a human proposal and is applied only by the API after a human approves it.

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

## Conventions

Same as `apps/api`: absolute imports from `app.`, built-in generics, empty `__init__.py` files, module file order docstring, imports, logger, constants, public symbols, private helpers.

## Run Locally

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8100
uv run pytest
uv run ruff check
```
