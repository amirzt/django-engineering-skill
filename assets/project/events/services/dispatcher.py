"""Execute ASYNC event deliveries with the durable job primitive.

The beat sweeper (and the post-commit nudge) calls `dispatch_due()`, which
returns abandoned leases to pending, claims due deliveries, and enqueues one
`events.deliver_event` task per claim on the delivery's queue. `deliver()` runs
the handler and records the outcome with the claim's fencing token, so a
duplicate or stale task changes nothing.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import timedelta

from django.conf import settings

from common import durable_jobs
from common.external_errors import PermanentError
from common.observability import job_id_var
from events.domain import event_classes
from events.models import EventDelivery
from events.services.registry import registry

logger = logging.getLogger(__name__)


def _backoff() -> Callable[[int], timedelta]:
    return durable_jobs.exponential_backoff(
        base_seconds=settings.DURABLE_JOB_BACKOFF_SECONDS,
        cap_seconds=settings.DURABLE_JOB_BACKOFF_MAX_SECONDS,
    )


def dispatch_due() -> int:
    """Claim due deliveries and enqueue them; return how many were enqueued."""
    from events.tasks import deliver_event

    limit = settings.DURABLE_JOB_SWEEP_BATCH_SIZE
    # Handlers are idempotent by contract, so an abandoned lease is retried.
    durable_jobs.release_expired_leases(EventDelivery, limit=limit, idempotent=True)
    claimed = durable_jobs.claim_due(
        EventDelivery, limit=limit, lease_seconds=settings.DURABLE_JOB_LEASE_SECONDS
    )
    queues = dict(
        EventDelivery.objects.filter(pk__in=[pk for pk, _ in claimed]).values_list(
            "pk", "queue"
        )
    )
    for delivery_id, attempt in claimed:
        deliver_event.apply_async(
            args=[str(delivery_id), attempt], queue=queues[delivery_id]
        )
    return len(claimed)


def deliver(*, delivery_id: uuid.UUID, expected_attempt: int) -> str:
    """Run one claimed delivery and return its resulting status."""
    delivery = (
        durable_jobs.guarded(EventDelivery, delivery_id, expected_attempt)
        .select_related("event")
        .first()
    )
    if delivery is None:
        logger.info("stale_delivery_ignored", extra={"delivery_id": str(delivery_id)})
        return "stale"
    token = job_id_var.set(str(delivery.pk))
    try:
        return _run(delivery, expected_attempt)
    finally:
        job_id_var.reset(token)


def _run(delivery: EventDelivery, expected_attempt: int) -> str:
    handler = registry.get(delivery.handler)
    event_class = event_classes(include_tests=True).get(delivery.event.name)
    if handler is None or event_class is None:
        return durable_jobs.mark_failed(
            EventDelivery,
            delivery.pk,
            expected_attempt,
            PermanentError("handler_not_registered"),
            max_attempts=settings.DURABLE_JOB_MAX_ATTEMPTS,
            backoff=_backoff(),
        )
    try:
        handler.function(event_class.from_payload(delivery.event.payload))
    except Exception as error:
        logger.warning(
            "event_delivery_failed",
            extra={
                "handler": delivery.handler,
                "error_code": getattr(error, "error_code", ""),
            },
            exc_info=error,
        )
        return durable_jobs.mark_failed(
            EventDelivery,
            delivery.pk,
            expected_attempt,
            error,
            max_attempts=settings.DURABLE_JOB_MAX_ATTEMPTS,
            backoff=_backoff(),
        )
    durable_jobs.mark_succeeded(EventDelivery, delivery.pk, expected_attempt)
    return durable_jobs.SUCCEEDED
