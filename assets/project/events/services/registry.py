"""The handler registry: which functions react to which domain events, and how.

Handlers register at import time with `@handles(...)`; each app's `apps.py`
`ready()` imports its `handlers.py`, which is the only registration mechanism.
A handler's key (`<module>.<function>`) is stored on pending deliveries, so
renaming a handler is a contract change, like renaming a Celery task.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeVar

from events.domain import DomainEvent

F = TypeVar("F", bound=Callable[..., Any])


class HandlerMode(StrEnum):
    #: Inside the emitting transaction; failure rolls the change back. No I/O.
    SYNC = "sync"
    #: After commit, in-process, best effort; failures are logged, never retried.
    ON_COMMIT = "on_commit"
    #: In a worker through a durable EventDelivery; retried, then dead-lettered.
    ASYNC = "async"


@dataclass(frozen=True)
class Handler:
    key: str
    event_name: str
    mode: HandlerMode
    function: Callable[[Any], None]
    queue: str


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, handler: Handler) -> None:
        existing = self._handlers.get(handler.key)
        if existing is not None and existing.event_name != handler.event_name:
            raise ValueError(
                f"Handler key {handler.key!r} is registered for two events."
            )
        self._handlers[handler.key] = handler

    def get(self, key: str) -> Handler | None:
        return self._handlers.get(key)

    def all(self) -> list[Handler]:
        return list(self._handlers.values())

    def handlers_for(self, event_name: str, *, mode: HandlerMode) -> list[Handler]:
        return [
            h
            for h in self._handlers.values()
            if h.event_name == event_name and h.mode == mode
        ]

    def has(self, event_name: str, mode: HandlerMode) -> bool:
        return bool(self.handlers_for(event_name, mode=mode))


registry = HandlerRegistry()


def handles(
    event_class: type[DomainEvent], *, mode: HandlerMode, queue: str = "events"
) -> Callable[[F], F]:
    """Register the decorated function as a handler of `event_class`."""

    def decorate(function: F) -> F:
        registry.register(
            Handler(
                key=f"{function.__module__}.{function.__qualname__}",
                event_name=event_class.name,
                mode=mode,
                function=function,
                queue=queue,
            )
        )
        return function

    return decorate
