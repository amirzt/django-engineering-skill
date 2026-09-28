"""Errors raised by the domain event machinery."""

from __future__ import annotations


class EventOutsideTransaction(RuntimeError):
    """`emit()` was called outside the transaction that made the change."""


class DuplicateEventName(RuntimeError):
    """Two DomainEvent classes declare the same name."""
