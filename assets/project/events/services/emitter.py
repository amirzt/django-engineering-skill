"""Emit domain events into the transactional outbox.

`emit()` must run inside the transaction that made the change, so the change and
its event commit together or not at all. SYNC handlers run immediately in that
transaction, ON_COMMIT handlers run after commit, and each ASYNC handler gets one
durable `EventDelivery` that a worker executes.
"""

from __future__ import annotations

import logging
import uuid
from functools import partial

from django.db import transaction

from common.observability import request_id_var
from events.domain import DomainEvent
from events.exceptions import EventOutsideTransaction
from events.models import EventDelivery, OutboxEvent
from events.services.registry import HandlerMode, registry

logger = logging.getLogger(__name__)


def emit(event: DomainEvent) -> uuid.UUID:
    """Record `event` and run or schedule its handlers.

    Raises `EventOutsideTransaction` when called outside an atomic block. A SYNC
    handler's exception propagates and rolls back the caller's transaction.
    """
    if not transaction.get_connection().in_atomic_block:
        raise EventOutsideTransaction(event.name)
    row = OutboxEvent.objects.create(
        name=event.name,
        version=event.version,
        organization_id=event.organization_id,
        subject_id=str(event.subject_id),
        payload=event.to_payload(),
        request_id=request_id_var.get(),
    )
    for handler in registry.handlers_for(event.name, mode=HandlerMode.SYNC):
        handler.function(event)
    if registry.has(event.name, HandlerMode.ON_COMMIT):
        transaction.on_commit(partial(run_on_commit_handlers, event), robust=True)
    async_handlers = registry.handlers_for(event.name, mode=HandlerMode.ASYNC)
    if async_handlers:
        EventDelivery.objects.bulk_create(
            EventDelivery(event=row, handler=handler.key, queue=handler.queue)
            for handler in async_handlers
        )
        transaction.on_commit(nudge_event_dispatch, robust=True)
    return row.id


def run_on_commit_handlers(event: DomainEvent) -> None:
    for handler in registry.handlers_for(event.name, mode=HandlerMode.ON_COMMIT):
        try:
            handler.function(event)
        except Exception:
            logger.exception(
                "on_commit_handler_failed",
                extra={"handler": handler.key, "event_name": event.name},
            )


def nudge_event_dispatch() -> None:
    """Ask a worker to dispatch due deliveries now instead of at the next sweep."""
    from events.tasks import dispatch_due_deliveries

    dispatch_due_deliveries.apply_async()
