"""The base class of every domain event.

A domain event is a fact that already happened, published by the service that
caused it, inside the same transaction. Fields are identifiers and small
scalars only - never personal, sensitive, or secret data. Names are
`<resource>.<past_participle>` and unique. `version` increases when a field
changes meaning or a required field is added; handlers must accept every
version still present in the outbox.

Event classes are plain frozen dataclasses (`frozen=True, kw_only=True`).
`slots=True` is deliberately not used: it recreates the class, which would make
subclass discovery see two classes per event.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import decimal
import enum
import typing
import uuid
from collections.abc import Mapping
from typing import Any, ClassVar, Self

from events.exceptions import DuplicateEventName


@dataclasses.dataclass(frozen=True, kw_only=True)
class DomainEvent:
    name: ClassVar[str] = ""
    version: ClassVar[int] = 1

    subject_id: uuid.UUID
    organization_id: uuid.UUID | None = None
    actor_type: str = "system"
    actor_id: str = ""

    @classmethod
    def from_principal(cls, principal: Any, **fields: Any) -> Self:
        """Build the event with the actor taken from a request or service principal."""
        user = getattr(principal, "user", None)
        actor_type = getattr(principal, "actor_type", "") or (
            "api_key" if getattr(principal, "credential_id", None) else "user"
        )
        actor_id = str(
            getattr(principal, "actor_id", "") or getattr(user, "pk", "") or ""
        )
        return cls(actor_type=actor_type, actor_id=actor_id, **fields)

    def to_payload(self) -> dict[str, Any]:
        return {
            field.name: _encode(getattr(self, field.name))
            for field in dataclasses.fields(self)
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> Self:
        hints = typing.get_type_hints(cls)
        known = {field.name for field in dataclasses.fields(cls)}
        values = {
            key: _decode(hints.get(key), value)
            for key, value in payload.items()
            if key in known
        }
        return cls(**values)


def _encode(value: Any) -> Any:
    if isinstance(value, uuid.UUID | decimal.Decimal):
        return str(value)
    if isinstance(value, dt.datetime | dt.date):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return value.value
    return value


def _decode(hint: Any, value: Any) -> Any:
    if value is None or hint is None:
        return value
    candidates = typing.get_args(hint) or (hint,)
    if uuid.UUID in candidates:
        return uuid.UUID(str(value))
    if decimal.Decimal in candidates:
        return decimal.Decimal(str(value))
    if dt.datetime in candidates:
        return dt.datetime.fromisoformat(value)
    if dt.date in candidates:
        return dt.date.fromisoformat(value)
    return value


def event_classes(*, include_tests: bool = False) -> dict[str, type[DomainEvent]]:
    """Every concrete event class by name, discovered from loaded subclasses."""
    found: dict[str, type[DomainEvent]] = {}
    pending = list(DomainEvent.__subclasses__())
    while pending:
        cls = pending.pop()
        pending.extend(cls.__subclasses__())
        if not cls.name:
            continue
        if not include_tests and ".tests." in f"{cls.__module__}.":
            continue
        other = found.get(cls.name)
        if other is not None and other is not cls:
            raise DuplicateEventName(
                f"{cls.name!r}: {other.__qualname__} and {cls.__qualname__}"
            )
        found[cls.name] = cls
    return found
