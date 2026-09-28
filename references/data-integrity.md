# Data integrity and concurrency

Constraints, locks, guarded updates, leases, state transitions, evidence, error
classification, money, and idempotency. Read whenever state can be contended,
money moves, or a request must be safe to repeat.

## Contents

1. Constraints first
2. Locking and transactions
3. Guarded conditional updates
4. Leases and fencing tokens
5. State transitions
6. Append-only evidence
7. Error classification for external and side-effecting work
8. Money
9. Idempotency
10. Recipe: add a state transition

---

## 1. Constraints first

- Every invariant that can be a database constraint is one (`models.md` §7).
- A Python check followed by a write is **not** concurrency-safe. Use a
  constraint, a lock, or a guarded update.
- A limit that affects money, security, or resource usage is enforced in the
  service or the database, never only in a serializer.

## 2. Locking and transactions

- `select_for_update()` serializes decisions on a row. All paths that make the
  same decision lock the **same owning row** (for example the account row for
  balance changes).
- `transaction.atomic()` blocks are as small as possible. **Never** perform
  network, storage, email, or other slow I/O while holding a lock or an open
  transaction.
- Work that depends on committed state runs after commit: `transaction.on_commit`,
  or a durable row that a worker picks up (`events-and-jobs.md` §8).
- `ATOMIC_REQUESTS` is off; services own their transactions.

## 3. Guarded conditional updates

State changes on rows that competing workers may touch are single conditional
updates:

```python
updated = Job.objects.filter(
    id=job.id,
    status=Job.Status.RUNNING,          # expected prior state
    attempt_count=expected_attempt,     # fencing token
).update(status=Job.Status.SUCCEEDED, lease_expires_at=None)
if updated == 0:
    logger.info("stale_worker_write_ignored", extra={"job_id": str(job.id)})
    return
```

Two legitimate shapes, chosen deliberately:
- **Guarded queryset update**: `filter(pk, state guard, fence).update(...)`, for
  workers and sweepers.
- **Locked compare-and-swap**: `select_for_update()`, compare in Python, then
  `save(update_fields=[...])`, when the transaction already holds the row lock.

## 4. Leases and fencing tokens

- A background claim sets `lease_expires_at`, after which another worker may take
  over.
- A **fencing token** (an `attempt_count` incremented once per claim, or a
  `claim_id` UUID per claim) is part of every write made on behalf of the claim,
  so a stale worker's writes become no-ops.
- `common/durable_jobs.py` implements both (`events-and-jobs.md` §10).

## 5. State transitions

```python
TERMINAL_ORDER_STATES = frozenset({Order.Status.FULFILLED, Order.Status.CANCELLED})
ALLOWED_ORDER_TRANSITIONS: dict[str, frozenset[str]] = {
    Order.Status.PENDING: frozenset({Order.Status.PAID, Order.Status.CANCELLED}),
    Order.Status.PAID: frozenset({Order.Status.FULFILLED, Order.Status.CANCELLED}),
}


def transition_order(order: Order, *, to: str, **fields: object) -> None:
    """Move a locked order to `to`, or raise `InvalidOrderTransition`.

    The caller holds the row lock and emits the matching domain event in the same
    transaction.
    """
    if to not in ALLOWED_ORDER_TRANSITIONS.get(order.status, frozenset()):
        raise InvalidOrderTransition(current_status=order.status, target_status=to)
    order.status = to
    for name, value in fields.items():
        setattr(order, name, value)
    order.save(update_fields=["status", *fields, "updated_at"])
```

- One transition function per stateful model, in `<thing>_states.py`. No other
  code assigns `status`.
- Terminal rows are never modified again.
- The service that calls the transition emits the event inside the same
  transaction, and the test asserts the new state **and** the outbox row.

## 6. Append-only evidence

- Evidence rows (ledger entries, payments, audit events, usage records) are never
  edited or deleted to correct them. A correction is a compensating row with its
  own unique idempotency key.
- The owning party (payer, tenant, team) is **pinned at admission** on the record,
  never re-derived later from current memberships.

## 7. Error classification for external and side-effecting work

| Class (`common/external_errors.py`) | Meaning | Action |
|---|---|---|
| `RetryableError` | Transient, and known not to have taken effect | Bounded retry with backoff and jitter |
| `PermanentError` | Will not succeed on retry | Fail, record `error_code`, no retry |
| `AmbiguousOutcomeError` | The outcome is unknown (timeout after sending, connection lost mid-response) | **Never auto-retry.** Mark `reconciliation_required` and reconcile (`operations.md` §8) |

Gateways raise these classes, and callers branch on the class, never on message text.

## 8. Money

- Integer amounts in whole or minor units, or `Decimal` with a currency; never
  floats (`models.md` §4). The currency and unit convention comes from the profile.
- Normalize and quantize at the boundary, never mid-calculation.
- Anything that must not be oversubscribed (balances, stock, seats) follows
  reserve → commit(actual) → release. Available means settled **plus** open
  reservations, computed under the owning row's lock.

## 9. Idempotency

### 9.1 Contract

- Every mutating `POST` with side effects accepts an `Idempotency-Key` header.
  Endpoints that move money or cause external side effects **require** it.
- Key: 1–255 visible ASCII characters (`^[\x21-\x7e]{1,255}$`); otherwise
  400 `invalid_idempotency_key`.
- Scope: unique per principal scope and operation (`org:<id>:orders.create`), never global.
- Fingerprint: HMAC-SHA256 of the method, path, and canonical JSON body
  (`sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False`).

| Situation | Response |
|---|---|
| Same key, same fingerprint, completed | Replay the stored result (same status and body) |
| Same key, different fingerprint | 400 `idempotency_key_reused` |
| Same key, still in progress | 409 `idempotency_request_in_progress` |

### 9.2 Implementation

- Prefer the key **on the resource row** when one request creates exactly one
  resource: a unique constraint on `(tenant, idempotency_key)`, and replay by
  rendering that resource.
- Otherwise use an `IdempotencyRecord` model:
  - fields: `scope`, `key`, `request_fingerprint`, `state` (`in_progress`/`completed`),
    `response_status`, `response_body`, `expires_at`;
  - a unique constraint on `(scope, key)`;
  - rows purged after the retention period.
- Flow: inside a transaction, `get_or_create` (catch the `IntegrityError` of a
  concurrent insert and re-read), compare fingerprints, then execute or replay.
- The service doing the work writes its own effects idempotently (unique keys on
  ledger rows, deliveries, and so on).

## 10. Recipe: add a state transition

1. Add the state to the model's `TextChoices`, and the transition to the table in
   `<thing>_states.py`. Update the terminal states if needed.
2. Update the model contract's `Lifecycle:` and `Events:` lines.
3. Add the event class (`events-and-jobs.md` §13).
4. Write the service: lock → authorize → transition → audit → emit, in one transaction.
5. Add the illegal-transition error (`api.md` §16.4).
6. Tests:
   - a legal transition (state + outbox row + audit row);
   - an illegal transition (409, nothing written);
   - a repeated call (idempotent);
   - concurrent transitions (PostgreSQL tier).
