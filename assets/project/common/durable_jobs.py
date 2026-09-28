"""Claim, lease, fence, retry, and dead-letter durable job rows.

Work that must happen eventually and at least once is a row, not only a broker
message: a lost message or a dead worker then leaves durable evidence that the
work is still owed. Every job model provides `status`, `attempt_count`,
`lease_expires_at`, `next_attempt_at`, `dead_at`, `last_error_code`, and
`updated_at`, with the status values used below.

Workers claim rows with `SELECT ... FOR UPDATE SKIP LOCKED`, increment the
attempt counter (the fencing token), and set a lease. Every later write filters
on the expected attempt, so a stale worker's write matches no row. An ambiguous
outcome is never retried automatically: it goes to `reconciliation_required`.
"""

from __future__ import annotations

import logging
import random
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from django.db import models, transaction
from django.db.models import F
from django.utils import timezone
from prometheus_client import Counter

from common.external_errors import AmbiguousOutcomeError, PermanentError

logger = logging.getLogger(__name__)

PENDING = "pending"
RUNNING = "running"
SUCCEEDED = "succeeded"
DEAD = "dead"
RECONCILIATION_REQUIRED = "reconciliation_required"

durable_jobs_dead_total = Counter(
    "durable_jobs_dead_total", "Jobs moved to the dead-letter state.", ["model"]
)


def claim_due(
    model: type[models.Model], *, limit: int, lease_seconds: int
) -> list[tuple[Any, int]]:
    """Claim up to `limit` due jobs and return (id, attempt) pairs to execute."""
    now = timezone.now()
    manager = model._default_manager
    with transaction.atomic():
        ids = list(
            manager.select_for_update(skip_locked=True)
            .filter(status=PENDING, next_attempt_at__lte=now)
            .order_by("next_attempt_at")
            .values_list("pk", flat=True)[:limit]
        )
        manager.filter(pk__in=ids).update(
            status=RUNNING,
            attempt_count=F("attempt_count") + 1,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            updated_at=now,
        )
        return list(manager.filter(pk__in=ids).values_list("pk", "attempt_count"))


def release_expired_leases(
    model: type[models.Model], *, limit: int, idempotent: bool
) -> int:
    """Return abandoned running jobs to pending, or to reconciliation.

    Only idempotent work may simply run again. When a previous attempt may have
    performed a side effect that must not happen twice, the row goes to
    `reconciliation_required` for an operator instead.
    """
    target = PENDING if idempotent else RECONCILIATION_REQUIRED
    with transaction.atomic():
        ids = list(
            model._default_manager.select_for_update(skip_locked=True)
            .filter(status=RUNNING, lease_expires_at__lt=timezone.now())
            .values_list("pk", flat=True)[:limit]
        )
        released = model._default_manager.filter(pk__in=ids, status=RUNNING).update(
            status=target,
            lease_expires_at=None,
            last_error_code="lease_expired",
            updated_at=timezone.now(),
        )
    if released:
        logger.warning(
            "durable_job_leases_released",
            extra={"model": model._meta.label, "count": released, "target": target},
        )
    return released


def guarded(
    model: type[models.Model], job_id: Any, expected_attempt: int
) -> models.QuerySet[Any]:
    return model._default_manager.filter(
        pk=job_id, status=RUNNING, attempt_count=expected_attempt
    )


def mark_succeeded(
    model: type[models.Model], job_id: Any, expected_attempt: int
) -> bool:
    updated = guarded(model, job_id, expected_attempt).update(
        status=SUCCEEDED,
        lease_expires_at=None,
        last_error_code="",
        updated_at=timezone.now(),
    )
    if not updated:
        logger.info("stale_worker_write_ignored", extra={"job_id": str(job_id)})
    return bool(updated)


def mark_failed(
    model: type[models.Model],
    job_id: Any,
    expected_attempt: int,
    error: Exception,
    *,
    max_attempts: int,
    backoff: Callable[[int], timedelta],
) -> str:
    """Record a failed attempt and return the job's new status."""
    now = timezone.now()
    code = str(getattr(error, "error_code", "unexpected_error"))
    if isinstance(error, AmbiguousOutcomeError):
        status, fields = RECONCILIATION_REQUIRED, {}
    elif isinstance(error, PermanentError) or expected_attempt >= max_attempts:
        status, fields = DEAD, {"dead_at": now}
    else:
        status, fields = PENDING, {"next_attempt_at": now + backoff(expected_attempt)}
    updated = guarded(model, job_id, expected_attempt).update(
        status=status,
        lease_expires_at=None,
        last_error_code=code,
        updated_at=now,
        **fields,
    )
    if not updated:
        logger.info("stale_worker_write_ignored", extra={"job_id": str(job_id)})
        return "stale"
    if status == DEAD:
        durable_jobs_dead_total.labels(model=model._meta.label).inc()
        logger.error(
            "durable_job_dead", extra={"job_id": str(job_id), "error_code": code}
        )
    return status


def exponential_backoff(
    *, base_seconds: int, cap_seconds: int
) -> Callable[[int], timedelta]:
    """Exponential backoff with 50-100% jitter, capped."""

    def delay(attempt: int) -> timedelta:
        seconds = min(cap_seconds, base_seconds * 2 ** max(0, attempt - 1))
        return timedelta(seconds=seconds * random.uniform(0.5, 1.0))  # noqa: S311 - jitter, not security

    return delay
