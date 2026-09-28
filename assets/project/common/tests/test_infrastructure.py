"""Model bases, structured logging, and migration helpers."""

from __future__ import annotations

import json
import logging
import uuid

from django.db import connection
from django.test import SimpleTestCase

from common.migration_operations import PostgresOnlySQL
from common.model_bases import AppendOnlyModel, AppendOnlyQuerySet
from common.observability import CorrelationFilter, JSONFormatter, request_id_var


class AppendOnlyTests(SimpleTestCase):
    def test_saved_rows_cannot_be_saved_again_or_deleted(self):
        row = AppendOnlyModel.__new__(AppendOnlyModel)
        row._state = type("State", (), {"adding": False})()
        with self.assertRaises(TypeError):
            row.save()
        with self.assertRaises(TypeError):
            row.delete()

    def test_querysets_refuse_bulk_update_and_delete(self):
        queryset = AppendOnlyQuerySet(
            model=type("Evidence", (), {"__name__": "Evidence"})
        )
        with self.assertRaises(TypeError):
            queryset.update(amount=1)
        with self.assertRaises(TypeError):
            queryset.delete()


class StructuredLoggingTests(SimpleTestCase):
    def test_records_are_json_with_correlation_and_extra_fields(self):
        record = logging.LogRecord(
            "orders", logging.INFO, __file__, 1, "order_placed", None, None
        )
        record.order_id = str(uuid.uuid4())
        token = request_id_var.set("req_abc")
        try:
            CorrelationFilter().filter(record)
        finally:
            request_id_var.reset(token)
        payload = json.loads(JSONFormatter().format(record))
        self.assertEqual(
            (payload["message"], payload["request_id"], payload["order_id"]),
            ("order_placed", "req_abc", record.order_id),
        )


class PostgresOnlySQLTests(SimpleTestCase):
    def test_statements_are_skipped_on_other_backends(self):
        operation = PostgresOnlySQL("SELECT definitely_not_valid_sql(")
        editor = type(
            "Editor", (), {"connection": type("C", (), {"vendor": "sqlite"})()}
        )()
        operation.database_forwards("app", editor, None, None)
        operation.database_backwards("app", editor, None, None)
        self.assertNotEqual(connection.vendor, "")
