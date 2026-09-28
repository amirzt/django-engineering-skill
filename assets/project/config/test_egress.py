"""Suite-wide test egress policy. Production code never imports this module.

The project test runner installs the guard for the whole run, so no test can
reach the real network by accident. Allowed hosts are the local test services
(`TEST_ALLOWED_EGRESS_HOSTS`) and loopback addresses. A test that truly needs a
socket opts in with `allow_network_egress`, which makes the exception visible
in review.
"""

from __future__ import annotations

import contextvars
import functools
import ipaddress
import socket
from collections.abc import Callable
from typing import Any

from django.conf import settings

_allow_egress: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "allow_test_egress", default=False
)
_installed = False


class TestEgressDenied(RuntimeError):
    """A test attempted DNS resolution or a connection to a non-approved host."""


def _is_allowed(host: object) -> bool:
    if _allow_egress.get():
        return True
    text = str(host)
    if text in set(getattr(settings, "TEST_ALLOWED_EGRESS_HOSTS", ())) | {"localhost"}:
        return True
    try:
        return ipaddress.ip_address(text).is_loopback
    except ValueError:
        return False


def install_egress_guard() -> None:
    global _installed
    if _installed:
        return
    original_connect = socket.socket.connect
    original_getaddrinfo = socket.getaddrinfo

    def guarded_connect(sock: socket.socket, address: Any) -> Any:
        if isinstance(address, tuple) and not _is_allowed(address[0]):
            raise TestEgressDenied(f"Test attempted network egress to {address[0]!r}.")
        return original_connect(sock, address)

    def guarded_getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if host is not None and not _is_allowed(host):
            raise TestEgressDenied(f"Test attempted DNS lookup of {host!r}.")
        return original_getaddrinfo(host, *args, **kwargs)

    socket.socket.connect = guarded_connect  # type: ignore[method-assign, assignment]  # test-only monkeypatch
    socket.getaddrinfo = guarded_getaddrinfo
    _installed = True


def allow_network_egress(test: Callable[..., Any]) -> Callable[..., Any]:
    """Explicit, reviewable opt-in for the rare test that needs a real socket."""

    @functools.wraps(test)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        token = _allow_egress.set(True)
        try:
            return test(*args, **kwargs)
        finally:
            _allow_egress.reset(token)

    return wrapper
