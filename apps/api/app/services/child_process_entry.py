"""The entry of a file-reading child process, importing nothing but the standard library.

The child first makes every socket, connection and name lookup fail and caps its own address
space, and only then unpickles the job - which imports the parser's modules - and runs it, so
no parser and no import-time code of a third-party library can reach the network. It sends one
`(status, payload)` tuple back: `ok` with the result, or `refused` with the refusal to raise.
"""

from __future__ import annotations

import pickle
import sys
from multiprocessing.connection import Connection
from typing import Any

OK = "ok"
REFUSED = "refused"


def child_main(sender: Connection, job: bytes, memory_limit: int) -> None:
    """Block the network, cap memory, then run the pickled `(target, args)` job."""
    refuse_network()
    limit_memory(memory_limit)
    from app.utilities.document_errors import (
        DocumentTooLargeError,
        DocumentUnreadableError,
        UnsupportedDocumentError,
    )

    try:
        target, args = pickle.loads(job)
        sender.send((OK, target(*args)))
    except (DocumentTooLargeError, DocumentUnreadableError, UnsupportedDocumentError) as exc:
        sender.send((REFUSED, type(exc)(str(exc))))
    except MemoryError:
        sender.send((REFUSED, DocumentTooLargeError("the file needs more memory than allowed")))
    except RecursionError:
        sender.send((REFUSED, DocumentTooLargeError("the file nests too deeply")))
    except Exception:
        sender.send((REFUSED, DocumentUnreadableError("the file could not be read")))
    finally:
        sender.close()


def refuse_network() -> None:
    """Every socket, connection and name lookup fails, through `socket` and `_socket` alike.

    The socket classes are replaced by subclasses that refuse to be created, so modules that
    subclass them at import time (such as `ssl`) still import, and nothing can open a socket.
    """
    import _socket
    import socket

    def refuse(*_: object, **__: object) -> Any:
        raise OSError("network access is disabled while a file is read")

    class _NoSocket(socket.socket):
        def __init__(self, *_: object, **__: object) -> None:
            refuse()

    class _NoRawSocket(_socket.socket):
        def __init__(self, *_: object, **__: object) -> None:
            refuse()

    socket.socket = _NoSocket  # type: ignore[misc]
    _socket.socket = _NoRawSocket  # type: ignore[misc]
    for module in (socket, _socket):
        for name in ("create_connection", "getaddrinfo", "gethostbyname", "socketpair"):
            if hasattr(module, name):
                setattr(module, name, refuse)


def limit_memory(limit: int) -> None:
    """Cap the address space so one file cannot exhaust the host's memory; past it an allocation
    fails. Windows has no `RLIMIT_AS`, so there the cap is skipped and only the time limit and
    slot count apply."""
    if sys.platform == "win32" or limit <= 0:
        return
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
