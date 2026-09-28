"""Structured logging primitives shared by web and worker processes.

The correlation identifiers live in `ContextVar`s so synchronous views, async
code, and Celery tasks see the same value without threading it through every
call. This module is referenced from `settings.LOGGING` and must stay free of
settings access and model imports.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
from contextvars import ContextVar

#: Correlation identifier of the request or task being executed.
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
#: Identifier of the durable job a worker is executing, when there is one.
job_id_var: ContextVar[str] = ContextVar("job_id", default="")

_STANDARD_RECORD_FIELDS = frozenset(
    vars(logging.makeLogRecord({})).keys() | {"message", "asctime"}
)


class CorrelationFilter(logging.Filter):
    """Attach the active correlation identifiers to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "request_id", ""):
            record.request_id = request_id_var.get()
        if not getattr(record, "job_id", ""):
            record.job_id = job_id_var.get()
        return True


class JSONFormatter(logging.Formatter):
    """One JSON object per line: fixed fields first, then the `extra=` data."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": dt.datetime.fromtimestamp(
                record.created, tz=dt.UTC
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", ""),
            "job_id": getattr(record, "job_id", ""),
            "process": os.getpid(),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD_RECORD_FIELDS and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)
