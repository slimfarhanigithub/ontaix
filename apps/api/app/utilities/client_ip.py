"""The client IP of a request, trusting `X-Forwarded-For` only as far as the configured proxies."""

from __future__ import annotations

import ipaddress

FORWARDED_FOR = "x-forwarded-for"


def client_ip(forwarded_for: str | None, peer: str | None, trusted_hops: int) -> str | None:
    """With no trusted proxy, the socket peer. With `trusted_hops` proxies, the address the
    outermost trusted proxy saw: the entry `trusted_hops` from the right of `X-Forwarded-For`,
    since each proxy appends the address it received the request from. Anything that is not an
    IP address is dropped, so a forged header can only name an address, never inject text."""
    candidate = peer
    if trusted_hops > 0 and forwarded_for:
        entries = [e.strip() for e in forwarded_for.split(",") if e.strip()]
        if len(entries) >= trusted_hops:
            candidate = entries[-trusted_hops]
    if not candidate:
        return None
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None
