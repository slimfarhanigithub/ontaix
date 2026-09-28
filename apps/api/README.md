# Ontaix API

Python 3.12 FastAPI modular monolith managed by uv. It is the only process that writes to the ontology store; every write is a proposal that a human approves or rejects.

## Layout

```text
alembic.ini              Alembic configuration; the URL comes from ONTAIX_DATABASE_URL
app/
  main.py                FastAPI entry point: routers under /api/v1, Problem+JSON handlers
  config.py              single pydantic-settings Settings class, env prefix ONTAIX_
  auth.py                caller resolution (dev header X-Ontaix-User) and role grants
  clients/db_client.py   async SQLAlchemy engine and session factory over psycopg 3
  migrations/            Alembic env, runner and versions; 0001 executes contracts/schema.sql
  models/api/            Pydantic DTOs, camelCase on the wire, one file per shape
  models/storage/        SQLAlchemy mappings, one file per table
  repositories/          DB access, one module per table; the only users of the session
  services/              orchestration: proposals, decisions, scene, companies, seed
  seed/                  seed data constants and the `python -m app.seed` command
  utilities/             pure helpers: permissions, layout maths, listing, problems
tests/                   pytest against a real PostgreSQL (embedded pgserver or CI service)
```

## Conventions

- Absolute imports from `app.` only; ruff bans relative imports.
- Built-in generics (`list[str]`, `str | None`), never `typing.List` or `Optional`.
- Module file order: docstring, imports, logger, constants, public symbols, private helpers.
- `__init__.py` files stay empty.

## Run Locally

```bash
uv sync
uv run python -m app.seed            # migrate, then load the demo tenant (idempotent)
uv run uvicorn app.main:app --reload --port 8000
uv run pytest
uv run ruff check
```

`ONTAIX_DATABASE_URL` must point at a PostgreSQL 16 database. In the `dev` environment a request identifies its user with the header `X-Ontaix-User: <email>` (the seeded users live in `app/seed/directory.py`). On Windows the async driver needs a selector event loop: run uvicorn with `--loop asyncio` after setting `asyncio.WindowsSelectorEventLoopPolicy`, as the seed command does.

## Tests

Tests use a real PostgreSQL. With `ONTAIX_TEST_DATABASE_URL` set (CI: the `postgres:16` service) they run there; otherwise the `pgserver` package starts an embedded PostgreSQL 16 in a temporary directory for the session. Each test module works in its own tenant.
