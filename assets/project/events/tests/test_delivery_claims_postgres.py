"""Claim contention and constraint names, which need real PostgreSQL behavior."""

from __future__ import annotations

import threading
import uuid
from unittest import skipUnless

from django.db import IntegrityError, connection, transaction
from django.test import TransactionTestCase

from common import durable_jobs
from events.models import EventDelivery, OutboxEvent


def make_deliveries(count: int) -> None:
    event = OutboxEvent.objects.create(
        name="probe.happened", version=1, subject_id=str(uuid.uuid4())
    )
    EventDelivery.objects.bulk_create(
        EventDelivery(event=event, handler=f"probe.handler_{i}", queue="events")
        for i in range(count)
    )


@skipUnless(
    connection.vendor == "postgresql", "requires SELECT ... FOR UPDATE SKIP LOCKED"
)
class DeliveryClaimConcurrencyTests(TransactionTestCase):
    def test_concurrent_claimers_never_claim_the_same_delivery(self):
        make_deliveries(20)
        barrier = threading.Barrier(2)
        results: list[list[tuple[object, int]]] = []

        def claim() -> None:
            try:
                barrier.wait()
                results.append(
                    durable_jobs.claim_due(EventDelivery, limit=20, lease_seconds=60)
                )
            finally:
                connection.close()

        threads = [threading.Thread(target=claim) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        claimed = [pk for batch in results for pk, _ in batch]
        self.assertEqual(len(claimed), len(set(claimed)))
        self.assertEqual(len(claimed), 20)


@skipUnless(
    connection.vendor == "postgresql", "requires psycopg constraint diagnostics"
)
class ConstraintNameTests(TransactionTestCase):
    def test_violation_reports_the_named_constraint(self):
        make_deliveries(1)
        delivery = EventDelivery.objects.get()
        with self.assertRaises(IntegrityError) as caught, transaction.atomic():
            EventDelivery.objects.create(
                event=delivery.event, handler=delivery.handler, queue="events"
            )
        self.assertEqual(
            caught.exception.__cause__.diag.constraint_name,
            "events_eventdelivery_event_handler_uniq",
        )
