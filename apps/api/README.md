# Ontaix API

Python 3.12 FastAPI modular monolith managed by uv. It is the only process that writes to the ontology store; every write is a proposal that a human approves or rejects.

## Layout

```text
alembic.ini              Alembic configuration; the URL comes from ONTAIX_DATABASE_URL
app/
  main.py                FastAPI entry point: routers under /api/v1, Problem+JSON handlers
  config.py              single pydantic-settings Settings class, env prefix ONTAIX_
  auth.py                caller resolution (session cookie, dev header), CSRF, organization binding
  admin.py               `python -m app.admin`: create the super admin, set a password (getpass)
  clients/db_client.py   async SQLAlchemy engines over psycopg 3, one per database role
  data/                  the hashed list of common breached passwords the password policy checks
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
ONTAIX_SEED=empty uv run python -m app.seed   # the tenant and its users only, no company
uv run uvicorn app.main:app --reload --port 8000
uv run pytest
uv run ruff check
```

`ONTAIX_DATABASE_URL` must point at a PostgreSQL 16 database. Its login must be a member of the NOLOGIN roles `ontaix_app` (organization requests, confined by row-level security to one organization per transaction) and `ontaix_platform` (sign-in, the platform portal, cross-organization jobs), or give the platform login in `ONTAIX_PLATFORM_DATABASE_URL`; the migration creates both roles.

Users sign in with an email and a password at `POST /api/v1/auth/sign-in`, which sets the `__Host-ontaix_session` cookie. There is no sign-up: the only default account is the super admin, created once by the owner in a terminal with the schema owner's login in `ONTAIX_DATABASE_URL` (only that login may grant the platform role):

```bash
uv run python -m app.admin create-super-admin <email>   # prompts twice, no echo
uv run python -m app.admin set-password <email>         # the super admin's own recovery
```

The super admin then creates organizations and their accounts from the platform portal. Only with `ONTAIX_ENVIRONMENT` `dev` or `test` and `ONTAIX_DEV_IDENTITY_HEADER=true` does the header `X-Ontaix-User: <email>` identify a seeded user instead (the seeded users live in `app/seed/directory.py` and have no password); `pnpm dev:stack` and the tests turn it on. On Windows the async driver needs a selector event loop: run uvicorn with `--loop asyncio` after setting `asyncio.WindowsSelectorEventLoopPolicy`, as the seed command does.

## Tests

Tests use a real PostgreSQL. With `ONTAIX_TEST_DATABASE_URL` set (CI: the `postgres:16` service) they run there; otherwise the `pgserver` package starts an embedded PostgreSQL 16 in a temporary directory for the session. Each test module works in its own tenant.
