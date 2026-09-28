"""Event payload round-trips and principal-based construction."""

from __future__ import annotations

import dataclasses
import datetime as dt
import decimal
import uuid
from types import SimpleNamespace

from django.test import SimpleTestCase

from events.domain import DomainEvent, event_classes
from events.exceptions import DuplicateEventName


@dataclasses.dataclass(frozen=True, kw_only=True)
class InvoiceIssued(DomainEvent):
    name = "invoice.issued"

    total: decimal.Decimal
    due_on: dt.date
    issued_at: dt.datetime
    customer_id: uuid.UUID | None = None


class DomainEventTests(SimpleTestCase):
    def test_payload_round_trips_typed_values(self):
        event = InvoiceIssued(
            subject_id=uuid.uuid4(),
            total=decimal.Decimal("12.50"),
            due_on=dt.date(2026, 10, 1),
            issued_at=dt.datetime(2026, 9, 28, 10, 0, tzinfo=dt.UTC),
            customer_id=uuid.uuid4(),
        )
        self.assertEqual(InvoiceIssued.from_payload(event.to_payload()), event)

    def test_actor_comes_from_the_principal(self):
        user = SimpleNamespace(pk=7)
        by_user = InvoiceIssued.from_principal(
            SimpleNamespace(user=user, credential_id=None),
            subject_id=uuid.uuid4(),
            total=decimal.Decimal(1),
            due_on=dt.date(2026, 10, 1),
            issued_at=dt.datetime.now(tz=dt.UTC),
        )
        by_key = InvoiceIssued.from_principal(
            SimpleNamespace(user=user, credential_id=uuid.uuid4()),
            subject_id=uuid.uuid4(),
            total=decimal.Decimal(1),
            due_on=dt.date(2026, 10, 1),
            issued_at=dt.datetime.now(tz=dt.UTC),
        )
        self.assertEqual((by_user.actor_type, by_user.actor_id), ("user", "7"))
        self.assertEqual(by_key.actor_type, "api_key")

    def test_duplicate_event_names_are_rejected(self):
        @dataclasses.dataclass(frozen=True, kw_only=True)
        class InvoiceIssuedAgain(DomainEvent):
            name = "invoice.issued"

        with self.assertRaises(DuplicateEventName):
            event_classes(include_tests=True)
        # Keep later tests independent of this deliberately broken class.
        InvoiceIssuedAgain.name = ""
