"""A contention answer logs the SQLSTATE and the error class, never the statement's values."""

from __future__ import annotations

import logging

import psycopg.errors
import pytest
from sqlalchemy.exc import OperationalError
from starlette.requests import Request

from app.clients import db_client
from app.main import _database_error_handler

pytestmark = pytest.mark.asyncio(loop_scope="session")

SECRET = "secret.person@example.com"


async def test_contention_log_has_no_bound_parameters(caplog: pytest.LogCaptureFixture) -> None:
    exc = OperationalError(
        "SELECT * FROM app_user WHERE email = %(email)s FOR UPDATE",
        {"email": SECRET},
        psycopg.errors.LockNotAvailable("canceling statement due to lock timeout"),
    )
    request = Request({"type": "http", "method": "POST", "path": "/api/v1/x", "headers": []})

    with caplog.at_level(logging.WARNING, logger="app.main"):
        response = await _database_error_handler(request, exc)

    assert response.status_code == 503
    assert "55P03" in caplog.text
    assert "OperationalError" in caplog.text
    assert SECRET not in caplog.text
    assert "SELECT" not in caplog.text


async def test_engine_hides_bound_parameters(migrated_database: str) -> None:
    assert db_client.get_engine().sync_engine.hide_parameters is True
