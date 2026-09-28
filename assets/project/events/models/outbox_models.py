"""The transactional outbox: emitted events and their per-handler deliveries."""

from __future__ import annotations

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from common.model_bases import PublicModel


class OutboxEvent(PublicModel):
    """A domain event recorded in the transaction that caused it.

    Owner: events.
    Tenant scope: organization_id (a plain UUID, so this bottom-layer app does not
        depend on the tenancy app).
    Lifecycle: written once by `emit()`; purged after the retention period once
        every delivery has succeeded.
    Invariants:
        - payload is the event's `to_payload()` and is never modified.
    Data classification: internal (events carry identifiers only).
    Append-only: no (operational data with retention).
    Events: none.
    """

    organization_id = models.UUIDField(
        null=True, blank=True, help_text=_("Tenant of the event, if any.")
    )

    name = models.CharField(max_length=100)
    version = models.PositiveSmallIntegerField()
    subject_id = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    request_id = models.CharField(max_length=128, blank=True, default="")

    class Meta:
        verbose_name = _("outbox event")
        verbose_name_plural = _("outbox events")
        indexes = [
            # Event catalog inspection and retention purge by name and age.
            models.Index(fields=["name", "created_at"], name="evt_name_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} {self.subject_id}"


class EventDelivery(PublicModel):
    """One ASYNC handler's pending or finished delivery of one outbox event.

    Owner: events.
    Tenant scope: inherited from the event.
    Lifecycle: pending -> running -> succeeded; running -> pending (retry);
        running -> dead | reconciliation_required. Driven by common.durable_jobs.
    Invariants:
        - One delivery per (event, handler) (events_eventdelivery_event_handler_uniq).
    Data classification: internal.
    Append-only: no.
    Events: none.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        RUNNING = "running", _("Running")
        SUCCEEDED = "succeeded", _("Succeeded")
        DEAD = "dead", _("Dead")
        RECONCILIATION_REQUIRED = (
            "reconciliation_required",
            _("Reconciliation required"),
        )

    event = models.ForeignKey(
        OutboxEvent, on_delete=models.CASCADE, related_name="deliveries"
    )

    handler = models.CharField(
        max_length=200, help_text=_("Registered handler key: <module>.<function>.")
    )
    queue = models.CharField(max_length=50)

    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.PENDING
    )
    attempt_count = models.PositiveIntegerField(
        default=0, help_text=_("Fencing token.")
    )
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    dead_at = models.DateTimeField(null=True, blank=True)

    last_error_code = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        verbose_name = _("event delivery")
        verbose_name_plural = _("event deliveries")
        constraints = [
            models.UniqueConstraint(
                fields=["event", "handler"],
                name="events_eventdelivery_event_handler_uniq",
            ),
        ]
        indexes = [
            # Dispatcher: due pending deliveries.
            models.Index(
                fields=["status", "next_attempt_at"], name="evd_status_next_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.handler} ({self.status})"
