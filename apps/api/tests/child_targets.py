"""Module-level jobs for the file-reading child process, used by the isolation tests."""

from __future__ import annotations

import socket


def try_connect(port: int) -> list[str]:
    """What each way of reaching the network does in the child: the error type, or `connected`."""
    import _socket

    outcomes: list[str] = []
    attempts = (
        lambda: socket.create_connection(("127.0.0.1", port), timeout=2),
        lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM),
        lambda: _socket.socket(),
        lambda: socket.getaddrinfo("localhost", port),
    )
    for attempt in attempts:
        try:
            attempt()
            outcomes.append("connected")
        except OSError as exc:
            outcomes.append(type(exc).__name__)
    return outcomes


def allocate(megabytes: int) -> int:
    """Hold `megabytes` of memory at once."""
    return len(bytearray(megabytes * 1024 * 1024))


def run_out_of_memory() -> None:
    raise MemoryError
