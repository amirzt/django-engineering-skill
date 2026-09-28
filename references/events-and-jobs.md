# Domain events and background work

How a change in one place causes effects elsewhere (domain events and the
transactional outbox), how background work is dispatched (Celery), and how work
that must happen eventually is made durable (durable jobs with a dead-letter state).
The `events` app and `common/durable_jobs.py` in `assets/project/` implement all of this.

## Contents

1. Why explicit domain events, not signals
2. Event classes
3. Emitting
4. Handlers and modes
5. Async delivery
6. The event catalog
7. Django signals: the closed list
8. Celery rules
9. Correlation across HTTP and workers
10. Durable jobs
11. Notifications and outgoing webhooks
12. Enforcement
13. Recipe: add a domain event and its handlers
14. Recipe: add a Celery task
15. Recipe: add a durable job or sweeper
16. Recipe: add a notification or outgoing webhook event type

---

## 1. Why explicit domain events, not signals

Business reactions to changes ("when an order is cancelled, release stock, notify
the customer, clear the cache") are **domain events emitted by the service that
makes the change**. They are never Django model signals, because:
- `post_save`/`pre_save` do not fire for `QuerySet.update()`, `bulk_create()`, or
  `bulk_update()`, and guarded updates use exactly those;
- a signal does not know *why* a row changed;
- receivers are invisible when reading the service;
- signals also fire during fixtures, data migrations, and test setup.

Events also let a lower layer notify a higher one without importing it.

## 2. Event classes

In the emitting app's `events.py`:

```python
"""Domain events of the orders app."""

from __future__ import annotations

import dataclasses

from events.domain import DomainEvent


@dataclasses.dataclass(frozen=True, kw_only=True)
class OrderCancelled(DomainEvent):
    """An order moved to cancelled."""

    name = "order.cancelled"
    version = 1

    reason_code: str
```

- The base carries `subject_id`, `organization_id`, `actor_type`, and `actor_id`.
  `from_principal(principal, **fields)` fills the actor.
- Always decorate with `@dataclasses.dataclass(frozen=True, kw_only=True)`. Do not
  use `slots=True`: it recreates the class and breaks subclass discovery.
- Names are `<resource>.<past_participle>` and unique.
- **Thin payloads**: IDs, codes, small scalars. Never personal, sensitive, or secret
  data (`security.md` §7), never large blobs.
- Changing fields is a contract change: bump `version`, and keep handlers able to
  read every version still in the outbox.

## 3. Emitting

```python
with transaction.atomic():
    ...  # lock, authorize, transition
    emit(OrderCancelled.from_principal(principal, subject_id=order.id,
                                       organization_id=order.organization_id,
                                       reason_code=reason_code))
```

- `emit()` (`events.services.emitter`) must run **inside** the transaction that made
  the change. Outside one it raises `EventOutsideTransaction`.
- It writes an `OutboxEvent`, runs SYNC handlers immediately, schedules ON_COMMIT
  handlers, and creates one `EventDelivery` per ASYNC handler.
- Pass the event class **inline** (`emit(EventClass(...))` or
  `emit(EventClass.from_principal(...))`). The registry test and the catalog
  generator find emitters by that pattern.
- Only services emit: never models, views, serializers, signal receivers, or
  handlers of the same event.
- Audit records are not events: `audit.record()` is called directly, because a
  failed audit write must fail the change (`security.md` §11).

## 4. Handlers and modes

In the **reacting** app's `handlers.py`, imported by its `apps.py` `ready()`:

```python
"""Reactions of the notifications app to other apps' events."""

from events.services.registry import HandlerMode, handles
from orders.events import OrderCancelled


@handles(OrderCancelled, mode=HandlerMode.SYNC)
def create_order_cancelled_notification(event: OrderCancelled) -> None:
    """Create the customer's notification row in the cancelling transaction."""
    create_notification(organization_id=event.organization_id,
                        kind="order_cancelled", subject_id=event.subject_id)
```

| Mode | Runs | Allowed work | On failure |
|---|---|---|---|
| **SYNC** | Inside the emitting transaction | DB writes through the handling app's services; **no network I/O** | Raises; the whole change rolls back |
| **ON_COMMIT** | After commit, in-process, best effort | Cache invalidation, metrics | Logged; never retried |
| **ASYNC** | In a worker, through a durable `EventDelivery` | External I/O, slow or retryable work | Retried with backoff, then dead-lettered |

- A handler is **thin**: it calls one service of the handling app.
- Handlers are **idempotent**: an ASYNC handler may receive the same event again.
- The handler key `<module>.<function>` is stored on pending deliveries. Renaming it
  is a contract change.
- Choose SYNC when the reaction is part of the same business fact, ASYNC otherwise.
  ON_COMMIT only when losing the effect is harmless.

## 5. Async delivery

- `EventDelivery` rows (unique on event and handler) follow the durable job
  pattern (§10).
- `events.dispatch_due_deliveries` runs from beat every minute and from a
  post-commit nudge. It releases abandoned leases, claims due deliveries, and
  enqueues `events.deliver_event` on each delivery's queue.
- `events.deliver_event` runs the handler with `EventClass.from_payload(...)` and
  records the outcome with the claim's fencing token:
  - success → `succeeded`;
  - `PermanentError` or too many attempts → `dead`;
  - `AmbiguousOutcomeError` → `reconciliation_required`;
  - anything else → back to `pending` with backoff.
- Settings: `DURABLE_JOB_MAX_ATTEMPTS`, `DURABLE_JOB_BACKOFF_SECONDS`,
  `DURABLE_JOB_BACKOFF_MAX_SECONDS`, `DURABLE_JOB_LEASE_SECONDS`,
  `DURABLE_JOB_SWEEP_BATCH_SIZE`. Values come from the profile.
- `OutboxEvent` rows are operational data. Once all their deliveries have succeeded,
  a bounded purge removes them after the retention period.

## 6. The event catalog

`deploy/generate_docs.py` writes `docs/features/domain-events.md` from the event
classes, the handler registry, and an AST scan of `emit(...)` calls. For each event
it lists the name, version, class, fields, emitting sites, and handlers (mode and
queue). Never edit it by hand; `--check` fails in CI when it is stale.

## 7. Django signals: the closed list

Signal receivers are allowed only for:
1. framework hooks: `post_migrate` (seeding), `user_logged_in` /
   `user_login_failed` (auth audit), `request_finished` (cleanup);
2. third-party integrations that offer no other hook.

Every receiver is listed in `APPROVED_SIGNAL_RECEIVERS` in `config/architecture.py`
with its reason, lives in the app's `signals.py`, is idempotent, does no network
I/O, and never produces business effects.

## 8. Celery rules

The concrete values (settings, queues, worker flags) come from the profile.

- **PostgreSQL is the source of truth; Celery is only transport.** Task results
  are ignored.
- Delivery is **at-least-once**: late acknowledgement, reject on worker loss,
  prefetch 1. Every task reads durable state, claims or guards, and exits early if
  the work is already done.
- Enqueue only after commit (`transaction.on_commit`), or let a sweeper pick up a
  durable row. When losing a message is unacceptable, **the durable row is the
  dispatch record**, and a sweeper re-dispatches rows that were never processed.
- **Ambiguous outcomes are never retried automatically** (`data-integrity.md` §7).
- **One queue per workload, one worker service per queue.** Only the queues listed
  in `CELERY_QUEUES` exist.
- JSON serialization only. Task names are explicit and stable (`<app>.<verb>_<object>`).
- `visibility_timeout` exceeds every task's hard time limit.
- Processing of untrusted content runs in an isolated container without network or
  credentials.
- Exactly one beat scheduler; every periodic task is a bounded sweeper.

## 9. Correlation across HTTP and workers

In `config/celery.py`:

```python
@setup_logging.connect
def configure_worker_logging(**_kwargs):
    import logging.config
    from django.conf import settings
    logging.config.dictConfig(settings.LOGGING)   # keep JSON logs in workers


@before_task_publish.connect
def attach_request_id(headers=None, **_kwargs):
    from common.observability import request_id_var
    if headers is not None and request_id_var.get():
        headers["request_id"] = request_id_var.get()


@task_prerun.connect
def bind_task_correlation(task_id=None, task=None, **_kwargs):
    from common.observability import request_id_var
    request = getattr(task, "request", None)
    value = getattr(request, "request_id", None) or (getattr(request, "headers", None) or {}).get("request_id")
    request_id_var.set(str(value or f"task_{task_id}"))
```

These Celery signals are infrastructure hooks, not model signals.

## 10. Durable jobs

Use a durable job whenever work must happen **eventually and at least once**, even
if a broker message or a worker is lost. Examples: event deliveries, notification
and webhook deliveries, cleanup of external resources, reconciliation, exports.

**Model shape** (a `PublicModel` with a contract docstring):
- identifying fields: `kind`, `target_type`, `target_id`, and typed inputs (never a
  large payload blob);
- `status` with the choices `pending`, `running`, `succeeded`, `dead`,
  `reconciliation_required`;
- `attempt_count` (the fencing token), `lease_expires_at`, `next_attempt_at`,
  `dead_at`, `last_error_code`;
- an index on `(status, next_attempt_at)`;
- a conditional unique constraint so a target has at most one open job.

**The shared primitive** (`common/durable_jobs.py`); never copy claim logic into a service:
- `claim_due(Model, limit=, lease_seconds=)`: `SELECT ... FOR UPDATE SKIP LOCKED`,
  increments `attempt_count`, sets the lease, returns `(id, attempt)` pairs.
- `release_expired_leases(Model, limit=, idempotent=)`: abandoned `running` rows go
  back to `pending` (idempotent work) or to `reconciliation_required`.
- `mark_succeeded(Model, id, attempt)` and `mark_failed(Model, id, attempt, error,
  max_attempts=, backoff=)`: guarded by the fencing token, so a stale worker's
  write is ignored.
- `exponential_backoff(base_seconds=, cap_seconds=)`: capped exponential backoff
  with 50–100% jitter.

**Operations**
- Tasks take `(job_id, expected_attempt)`, and a beat sweeper claims and dispatches.
- A `requeue_dead_jobs --model=... --since=... --dry-run` command resets selected
  `dead` rows to `pending`, keeps `attempt_count`, and writes an audit event.
- The metric `durable_jobs_dead_total{model}`, plus DB-snapshot metrics for backlog
  and the oldest pending age. Alert on new dead jobs and on backlog age, with a
  runbook (`operations.md` §6).

## 11. Notifications and outgoing webhooks

- A notification row is created by a **SYNC handler** of the event that causes it,
  so it commits with the fact it announces. It is readable over the API.
- Delivery through a channel (SMS, email, push) is a durable job that records
  `delivered_at`, `attempt_count`, and `last_error_code`.
- Outgoing webhooks: a SYNC handler creates one `WebhookDelivery` per subscribed
  endpoint, and delivery is a durable job.
  - **Signing**: `Signature: t=<ts>,v1=<hex HMAC-SHA256 of "<ts>.<raw body>">`, with
    two `v1` values during a secret rotation. Receivers compare in constant time.
  - The target is SSRF-checked (`security.md` §10), redirects are disabled, and
    connect/read timeouts are set.
  - Only the response *class* is stored, never the body.
  - The endpoint is **auto-disabled** after N consecutive failures, and the owner
    is notified.
  - Payloads are thin (IDs and status).
  - The secret is shown once, and rotation overlaps.

## 12. Enforcement

`common/tests/test_event_registry.py` checks that:
- event names are unique and match `<resource>.<past_participle>`;
- every event class is emitted somewhere, and every emitted name is a known class;
- every handler's event exists, and every ASYNC handler's queue is in `CELERY_QUEUES`;
- every signal receiver is in `APPROVED_SIGNAL_RECEIVERS`;
- `emit()` outside a transaction is refused.

`events/tests/` covers emission, rollback of SYNC failures, ON_COMMIT timing,
delivery success, duplicate tasks, the retry/dead/reconciliation outcomes, and
(PostgreSQL tier) claim contention and constraint names.

## 13. Recipe: add a domain event and its handlers

1. Define the event class in the emitting app's `events.py` (§2).
2. Emit it inline from the service, inside the transaction (§3).
3. For each reaction, choose a mode (§4) and add a thin handler in the **reacting**
   app's `handlers.py`. ASYNC handlers name a queue from `CELERY_QUEUES`.
4. Make every handler idempotent.
5. Update the model contract's `Events:` line.
6. Run `deploy/generate_docs.py` (event catalog).
7. Tests:
   - the outbox row and its payload;
   - SYNC effects commit and roll back with the change;
   - each ASYNC handler through a real delivery, and a duplicate delivery;
   - the registry tests pass.

## 14. Recipe: add a Celery task

1. Put the logic in a service. The task is a thin wrapper
   (`file-organization.md` §8).
2. Give it an explicit, stable name, and route it to an existing queue (a new queue
   is a policy change).
3. Dispatch it with `transaction.on_commit`, or from a durable row by a sweeper.
4. Make it safe under duplicate delivery: a claim, a guard, or an early exit.
5. Add it to `docs/features/celery.md` (the documentation test checks this).
6. Add metrics and an alert if it matters operationally.
7. Tests: the service logic, the duplicate-delivery no-op, and a run through the
   real worker.

## 15. Recipe: add a durable job or sweeper

1. Create the job model with the fields in §10, a contract docstring, the partial
   unique constraint, and the sweeper index.
2. Write the executing service, raising the classified errors
   (`data-integrity.md` §7).
3. Add a task taking `(job_id, expected_attempt)`, and a beat sweeper that calls
   `release_expired_leases`, `claim_due`, and dispatches.
4. Make sure `requeue_dead_jobs` covers the model.
5. Add metrics, an alert, and a runbook link.
6. Tests:
   - claim contention (PostgreSQL tier);
   - success;
   - retryable → backoff;
   - permanent → dead;
   - ambiguous → reconciliation;
   - a stale worker's write is a no-op.

## 16. Recipe: add a notification or outgoing webhook event type

1. The triggering fact is a domain event (§13).
2. Add a SYNC handler in `notifications` that creates the notification row, and for
   webhooks one delivery row per subscribed endpoint.
3. Add the user-facing texts in every configured language. Keep SMS texts short
   (a Persian SMS segment is 70 characters).
4. Delivery is a durable job, and webhook payloads are thin.
5. Document the event type for receivers in the feature document.
6. Tests:
   - the rows are created with the event;
   - delivery succeeds, retries, and dead-letters;
   - signatures verify with both secrets during a rotation.
