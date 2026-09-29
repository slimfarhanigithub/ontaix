"""The adapter's log filter masks authentication headers on the SDK's child loggers too."""

from __future__ import annotations

import logging


def test_the_redacting_filter_covers_the_sdks_child_loggers() -> None:
    import app.clients.anthropic_llm_client as adapter

    for name in ("anthropic", "anthropic._base_client"):
        assert adapter._REDACTING_FILTER in logging.getLogger(name).filters
    record = logging.LogRecord(
        "anthropic._base_client", logging.WARNING, "", 0, "X-Api-Key: %s", ("v",), None
    )
    assert adapter._REDACTING_FILTER.filter(record)
    assert "v" not in record.getMessage() and "[redacted]" in record.getMessage()
