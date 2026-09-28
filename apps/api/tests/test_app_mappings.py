"""The application process maps every table a foreign key points at."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]

# Runs in a fresh interpreter: the test session itself imports every repository through the
# fixtures, which would hide a table that only the application's import graph misses.
CHECK = """
import app.main
from app.models.storage.base import Base
for table in Base.metadata.tables.values():
    for fk in table.foreign_keys:
        fk.column
print("ok")
"""


def test_every_foreign_key_target_is_mapped_by_the_app() -> None:
    result = subprocess.run(
        [sys.executable, "-c", CHECK],
        cwd=API_ROOT,
        env={**os.environ, "ONTAIX_ENVIRONMENT": "test"},
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
