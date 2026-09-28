"""Celery entry points for domain event delivery. Logic lives in the dispatcher."""

from __future__ import annotations

import uuid

from celery import shared_task

from events.services import dispatcher


@shared_task(
    name="events.dispatch_due_deliveries", acks_late=True, reject_on_worker_lost=True
)
def dispatch_due_deliveries() -> int:
    return dispatcher.dispatch_due()


@shared_task(name="events.deliver_event", acks_late=True, reject_on_worker_lost=True)
def deliver_event(delivery_id: str, expected_attempt: int) -> str:
    return dispatcher.deliver(
        delivery_id=uuid.UUID(delivery_id), expected_attempt=expected_attempt
    )
