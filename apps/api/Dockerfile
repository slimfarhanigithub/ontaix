# Build context is the repository root: the image carries contracts/schema.sql, which the first
# migration executes. The compose file and the deploy workflow set the context.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY apps/api/app ./app
COPY apps/api/README.md apps/api/alembic.ini ./
RUN uv sync --frozen --no-dev
COPY contracts/schema.sql ./contracts/schema.sql

FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app
# A fixed, unprivileged uid and gid, so a pod can require a non-root user by number. The code
# and the virtual environment stay owned by root: the process reads them and writes only /tmp.
RUN groupadd --system --gid 10001 ontaix && useradd --system --uid 10001 --gid 10001 --no-create-home ontaix
COPY --from=build /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 HOME=/tmp \
    ONTAIX_SCHEMA_SQL=/app/contracts/schema.sql
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status == 200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
