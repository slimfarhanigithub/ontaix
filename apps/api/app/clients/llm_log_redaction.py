"""Log hygiene for the language model SDKs: no request body, key or token ever reaches a log.

`protect_loggers` holds the named SDK and HTTP loggers at WARNING and attaches one filter that
drops records below INFO (they carry request bodies) and masks API keys, `Authorization`
values, bearer tokens and JSON Web Tokens in every remaining message. A logger's filters do not
apply to records of its child loggers, so the filter is attached to every child logger already
registered too.
"""

from __future__ import annotations

import logging
import re

_HEADER_PATTERN = re.compile(
    r"(?i)(x-api-key|api-key|authorization)(['\"]?\s*[:=]\s*['\"]?)(bearer\s+)?[^'\",\s}]+"
)
_BEARER_PATTERN = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]+")
_JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")


class RedactingFilter(logging.Filter):
    """Drops debug records and masks credentials in the formatted message."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno < logging.INFO:
            return False
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        # The message is formatted before it is masked, so a value passed as an argument is
        # masked too.
        record.msg = redact(message)
        record.args = None
        return True


REDACTING_FILTER = RedactingFilter()


def redact(message: str) -> str:
    """The message with every key, authorization value, bearer token and JWT masked."""
    message = _HEADER_PATTERN.sub(r"\1\2[redacted]", message)
    message = _BEARER_PATTERN.sub(r"\1[redacted]", message)
    return _JWT_PATTERN.sub("[redacted]", message)


def protect_loggers(names: tuple[str, ...]) -> RedactingFilter:
    """Holds the named top-level loggers at WARNING and filters them and their registered
    children."""
    for name in names:
        logging.getLogger(name).setLevel(logging.WARNING)
    for name in (*names, *list(logging.root.manager.loggerDict)):
        if name.split(".")[0] in names:
            target = logging.getLogger(name)
            if REDACTING_FILTER not in target.filters:
                target.addFilter(REDACTING_FILTER)
    return REDACTING_FILTER
