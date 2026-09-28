# Observability and performance

Structured logs with correlation, metrics, alerts and runbooks, health endpoints,
runtime performance rules, and how to measure performance before claiming it.
Log fields, ports, and tool versions come from the profile.

## Contents

1. Structured logs
2. Correlation
3. Metrics
4. Alerts and runbooks
5. Health endpoints
6. Performance and runtime rules
7. Measuring performance
8. Recipe: add a metric and alert

---

## 1. Structured logs

- JSON, one object per line, on stdout, in every process (web, workers, beat).
  `common/observability.py` provides `JSONFormatter` and `CorrelationFilter`.
- The message is a **constant snake_case event name**, and data goes in `extra=`:
  `logger.info("order_cancelled", extra={"order_id": str(order.id)})`.
- Log **state transitions and failure points**, with IDs, statuses, and error codes.
- Never log payloads, or anything classified personal (unmasked), sensitive, or
  secret (`security.md` §7).
- In Celery workers, connect `setup_logging` so Django's `LOGGING` stays
  authoritative (`events-and-jobs.md` §9).

## 2. Correlation

- `request_id_var` and `job_id_var` are `ContextVar`s attached to every record.
- A request-ID middleware:
  - validates or creates the ID (`security.md` §9);
  - sets the variable and echoes `X-Request-ID` on the response;
  - resets the variable in `finally`.
- The ID travels to Celery in task headers (`before_task_publish`), is rebound in
  `task_prerun`, and appears in every error response (`api.md` §7).

## 3. Metrics

- Prometheus through `prometheus_client`, in multiprocess mode for gunicorn and
  Celery. Each worker container serves its own metrics port.
- Outcome counters (`*_total{result=...}`) and latency histograms, incremented by
  the working process.
- **DB-snapshot metrics** computed on scrape for backlogs, stuck rows, the oldest
  pending age, and dead-lettered jobs.
- Labels are bounded: never user IDs, raw paths, or free text.
- Metric names follow `<app>_<noun>_<unit or total>`.

## 4. Alerts and runbooks

Every important workflow has an **alert** in `monitoring/rules/`, and each alert
links to a **runbook** in `docs/runbooks/` (template: `comments-and-docs.md` §4). A
log line alone is not a recovery path.

## 5. Health endpoints

- `/health/live`: no I/O. It answers whether the process can serve, and is used for
  restarts.
- `/health/ready`: checks the database (`SELECT 1`), each Redis (`PING`), and
  whether migrations are applied. A healthy migration result may be memoized; an
  unhealthy one never is.
  - It returns a status per component.
  - It is token-authenticated, because it exposes topology and is expensive.

## 6. Performance and runtime rules

- A connection pooler (PgBouncer in transaction mode) sits in front of PostgreSQL
  when the profile says so. Its Django settings are in the profile.
- Workers **release database connections before slow external I/O**, and recover
  once on a lost connection by re-reading durable state. They never assume an
  outcome and never re-send an external request.
- Every outbound call has explicit connect, read, and overall deadlines.
- Pools are bounded everywhere: database, Redis, HTTP clients, thread pools.
- `select_related` / `prefetch_related` follow the serializer's and service's access
  patterns. Important list and detail endpoints have `assertNumQueries` tests.
- Prefer set-based work (`update`, `bulk_create`, aggregates) over ORM loops.
- Indexes come from real query patterns (`models.md` §7).
- Large binary data never goes into JSON fields, logs, or Redis; it goes through the
  file subsystem (`files.md`).
- Do not add a cache without the discipline in `redis-and-caching.md` §7.

## 7. Measuring performance

When a change touches a hot path, or claims an improvement:

1. **Queries**: `assertNumQueries` with 1 and N items proves the count does not grow
   with N.
2. **Realistic data**: generate a realistic volume locally with a script or command
   (never real personal data), for example 100k rows in the table under test.
3. **Plans**: run `EXPLAIN (ANALYZE, BUFFERS)` for each important query. Confirm the
   intended index is used, and look for sequential scans and bad row estimates.
4. **Timing**: repeat the real request (for example 50 times). Compare the median and
   the slowest before and after, on the same data.
5. **Record** the numbers, the data volume, and the commands in the handoff.

## 8. Recipe: add a metric and alert

1. Declare the metric in the app's `metrics.py`, with bounded labels.
2. Increment it at the state transition or failure point, or compute it on scrape
   from the database.
3. Add an alert rule with a threshold and duration, and a link to its runbook.
4. Write the runbook (`comments-and-docs.md` §4).
5. Tests: the metric changes when the event happens.
