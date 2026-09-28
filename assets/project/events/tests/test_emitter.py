"""Emission, handler modes, and durable delivery of domain events."""

from __future__ import annotations

import dataclasses
import uuid
from unittest import mock

from django.db import transaction
from django.test import TestCase, override_settings

from common.external_errors import AmbiguousOutcomeError, PermanentError
from events.domain import DomainEvent
from events.models import EventDelivery, OutboxEvent
from events.services import dispatcher
from events.services.emitter import emit
from events.services.registry import HandlerMode, handles

CALLS: list[tuple[str, uuid.UUID]] = []
FAILURES: dict[str, Exception] = {}


@dataclasses.dataclass(frozen=True, kw_only=True)
class WidgetShipped(DomainEvent):
    name = "widget.shipped"

    carrier_code: str


@handles(WidgetShipped, mode=HandlerMode.SYNC)
def record_shipment_sync(event: WidgetShipped) -> None:
    if "sync" in FAILURES:
        raise FAILURES["sync"]
    CALLS.append(("sync", event.subject_id))


@handles(WidgetShipped, mode=HandlerMode.ON_COMMIT)
def record_shipment_after_commit(event: WidgetShipped) -> None:
    CALLS.append(("on_commit", event.subject_id))


@handles(WidgetShipped, mode=HandlerMode.ASYNC, queue="events")
def notify_shipment(event: WidgetShipped) -> None:
    if "async" in FAILURES:
        raise FAILURES["async"]
    CALLS.append(("async", event.subject_id))


@override_settings(
    DURABLE_JOB_MAX_ATTEMPTS=3,
    DURABLE_JOB_BACKOFF_SECONDS=1,
    DURABLE_JOB_BACKOFF_MAX_SECONDS=10,
    DURABLE_JOB_LEASE_SECONDS=60,
    DURABLE_JOB_SWEEP_BATCH_SIZE=10,
)
class EmitterTests(TestCase):
    def setUp(self):
        CALLS.clear()
        FAILURES.clear()

    def emit_shipment(self) -> uuid.UUID:
        subject = uuid.uuid4()
        with self.captureOnCommitCallbacks(execute=False), transaction.atomic():
            emit(WidgetShipped(subject_id=subject, carrier_code="post"))
        return subject

    def test_emit_records_the_event_and_runs_sync_handlers_in_the_transaction(self):
        subject = self.emit_shipment()
        row = OutboxEvent.objects.get()
        self.assertEqual((row.name, row.subject_id), ("widget.shipped", str(subject)))
        self.assertEqual(row.payload["carrier_code"], "post")
        self.assertIn(("sync", subject), CALLS)

    def test_a_failing_sync_handler_rolls_back_the_change_and_the_event(self):
        FAILURES["sync"] = RuntimeError("boom")
        with self.assertRaises(RuntimeError), transaction.atomic():
            emit(WidgetShipped(subject_id=uuid.uuid4(), carrier_code="post"))
        self.assertFalse(OutboxEvent.objects.exists())

    def test_on_commit_handlers_run_only_after_commit(self):
        subject = uuid.uuid4()
        with (
            self.captureOnCommitCallbacks(execute=True),
            transaction.atomic(),
            mock.patch("events.services.emitter.nudge_event_dispatch"),
        ):
            emit(WidgetShipped(subject_id=subject, carrier_code="post"))
            self.assertNotIn(("on_commit", subject), CALLS)
        self.assertIn(("on_commit", subject), CALLS)

    def test_async_handler_gets_one_durable_delivery_that_a_worker_completes(self):
        subject = self.emit_shipment()
        delivery = EventDelivery.objects.get()
        with mock.patch("events.tasks.deliver_event.apply_async") as enqueue:
            self.assertEqual(dispatcher.dispatch_due(), 1)
        delivery_id, attempt = enqueue.call_args.kwargs["args"]
        self.assertEqual(
            dispatcher.deliver(
                delivery_id=uuid.UUID(delivery_id), expected_attempt=attempt
            ),
            "succeeded",
        )
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, EventDelivery.Status.SUCCEEDED)
        self.assertIn(("async", subject), CALLS)

    def test_a_duplicate_task_for_a_finished_delivery_changes_nothing(self):
        self.emit_shipment()
        with mock.patch("events.tasks.deliver_event.apply_async") as enqueue:
            dispatcher.dispatch_due()
        delivery_id, attempt = enqueue.call_args.kwargs["args"]
        dispatcher.deliver(delivery_id=uuid.UUID(delivery_id), expected_attempt=attempt)
        self.assertEqual(
            dispatcher.deliver(
                delivery_id=uuid.UUID(delivery_id), expected_attempt=attempt
            ),
            "stale",
        )
        self.assertEqual(sum(1 for kind, _ in CALLS if kind == "async"), 1)

    def test_failures_retry_then_dead_letter_and_ambiguous_outcomes_wait_for_reconciliation(
        self,
    ):
        cases = [
            (RuntimeError("transient"), EventDelivery.Status.PENDING),
            (PermanentError("rejected"), EventDelivery.Status.DEAD),
            (
                AmbiguousOutcomeError("timeout_after_send"),
                EventDelivery.Status.RECONCILIATION_REQUIRED,
            ),
        ]
        for error, expected in cases:
            with self.subTest(error=type(error).__name__):
                EventDelivery.objects.all().delete()
                OutboxEvent.objects.all().delete()
                FAILURES["async"] = error
                self.emit_shipment()
                with mock.patch("events.tasks.deliver_event.apply_async") as enqueue:
                    dispatcher.dispatch_due()
                delivery_id, attempt = enqueue.call_args.kwargs["args"]
                dispatcher.deliver(
                    delivery_id=uuid.UUID(delivery_id), expected_attempt=attempt
                )
                self.assertEqual(EventDelivery.objects.get().status, expected)
