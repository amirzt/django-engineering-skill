# File organization

The main rule of the codebase: **one responsibility per file, and the file is named
after that responsibility.** When anyone opens a folder, they know where everything
lives before reading a line of code. Read this before creating any module.

## Contents

1. Project layout
2. App anatomy
3. What each kind of file may do
4. Naming service modules
5. Writing a service module
6. Writing a view
7. Serializers
8. Tasks and management commands
9. Exceptions, metrics, checks
10. Growing a domain: sub-packages, protocols, registries, facades
11. Resource-oriented packages
12. Test organization
13. When to split a file
14. Forbidden patterns
15. Recipe: add a management command

---

## 1. Project layout

```text
<repo>/
├── AGENTS.md   CLAUDE.md          # repository instructions (CLAUDE.md imports AGENTS.md)
├── manage.py   pyproject.toml   requirements*.txt   pylock.toml   .env.example
├── Dockerfile   docker-compose*.yml
├── config/                        # composition root: settings/, urls, asgi, celery,
│                                  # architecture.py, test_runner.py, test_egress.py
├── common/                        # infrastructure primitives (not a Django app)
│   ├── model_bases.py  errors.py  external_errors.py  api_errors.py
│   ├── constraint_errors.py  observability.py  durable_jobs.py
│   ├── migration_operations.py  ...one module per primitive
│   └── tests/                     # architecture, model, event, documentation checks
├── events/                        # domain events: outbox, deliveries, emit, registry
├── <foundational apps>/           # e.g. accounts, access, files, notifications
├── <feature apps>/                # e.g. orders, catalog
├── deploy/                        # run_quality_gates.py, check_migration_safety.py,
│                                  # generate_docs.py, seeds/, infrastructure config
├── monitoring/                    # alert rules, dashboards
└── docs/
    ├── engineering/project-policy.md
    ├── decisions/  features/  runbooks/  api/
    └── data-model.md              # generated
```

- `common/` holds only infrastructure primitives, each in a module named for its
  job. It **never** imports a first-party app. It has no concrete models (abstract
  bases only), no migrations, and no management commands.
- App names are lowercase domain nouns.

## 2. App anatomy

```text
orders/
├── apps.py                    # ready() imports handlers.py (and signals.py if approved)
├── admin.py | admin/
├── models/
│   ├── __init__.py            # re-exports every model with __all__
│   └── order_models.py        # one aggregate per file
├── querysets.py               # optional, when model files grow
├── events.py                  # this app's DomainEvent classes
├── handlers.py                # this app's reactions to any app's events
├── serializers/  order_serializers.py
├── views/        order_views.py         # one file per resource
├── urls/         v1.py
├── services/                  # business logic, one job per module
│   ├── order_placement.py
│   ├── order_cancellation.py
│   └── order_states.py        # vocabulary: states and transitions
├── tasks.py                   # thin Celery entry points
├── management/commands/       # operator tools
├── exceptions.py              # DomainError subclasses
├── metrics.py   checks.py
├── signals.py                 # only for an approved receiver
├── migrations/
└── tests/  support.py  test_<behavior>.py
```

- `models/__init__.py` re-exports every model and defines `__all__`, so moving a
  model between files never breaks an import.
- A very small app may start flat (`models.py`, `services.py`, `views.py`). Split
  it into packages as soon as a file covers more than one aggregate or workflow.
- File suffixes are plural and consistent: `*_models.py`, `*_serializers.py`,
  `*_views.py`.

## 3. What each kind of file may do

| File | Its only job | Never contains |
|---|---|---|
| **View** | Parse HTTP, resolve the principal, call **one** service, render the result | Business rules, `transaction.atomic`, multi-step queries, external calls |
| **Serializer** | Shape, type, format, and length validation; unknown-field rejection; output fields | Workflows, permission checks, side effects, business queries |
| **Service** | One workflow or rule: transactions, locks, events, audit, calls to other services | `request`, `Response`, HTTP status codes |
| **Model** | Fields, Meta, row invariants, pure derived properties (`models.md` §8) | Cross-model workflows, queries in properties, I/O, events |
| **QuerySet / Manager** | Reusable filters and never-bypass guards | Business decisions |
| **`events.py`** | Frozen `DomainEvent` dataclasses | Logic |
| **`handlers.py`** | Thin handlers that call this app's services | Business logic of their own |
| **Presenter** | Domain result → wire dict | Writes, permission checks |
| **`tasks.py`** | Receive IDs, call a service | Business logic, large payloads |
| **Management command** | Operator entry point calling the same service | Its own copy of the logic |
| **`exceptions.py`** | `DomainError` subclasses | HTTP codes, DRF imports |
| **`metrics.py`** | Metric declarations and DB-snapshot exporters | Business logic |
| **`checks.py`** | Django system checks for configuration | Runtime logic |
| **`signals.py`** | Approved receivers only (`events-and-jobs.md` §7) | Business effects |

## 4. Naming service modules

| Pattern | Use for | Examples |
|---|---|---|
| `<noun>_<verb-ing>.py`, `<thing>_service.py` | A workflow | `order_placement.py`, `refund_service.py` |
| `<thing>_<aspect>.py` | One concept split by concern | `asset_service.py`, `asset_delivery.py`, `asset_purposes.py` |
| A plain noun | A policy or decision | `policy.py`, `scoping.py`, `concurrency.py` |
| `<thing>_states.py`, `<thing>_types.py` | Vocabulary: enums, allowlists, transitions | `order_states.py` |
| `base.py`, `protocol.py`, `registry.py` | Interface and implementation lookup | `gateways/registry.py` |

Forbidden: `utils.py`, `helpers.py`, `misc.py`, `common.py` inside an app, and a
`services.py` holding more than one workflow once the app has grown. A test
enforces the first three (`testing.md` §7).

## 5. Writing a service module

1. A module docstring in the house style (`comments-and-docs.md` §2).
2. Keyword-only arguments, principal or tenant first: `def cancel_order(*, principal, order_id, reason_code)`.
3. Typed results: a frozen dataclass or a model instance, never a loose tuple or dict.
4. Domain errors from the app's `exceptions.py` (`api.md` §6).
5. Vocabulary separate from logic (`*_states.py`, `*_types.py`).
6. Pure validation separate from persistence (`inspect_upload()` versus `save_validated_upload()`).
7. Small `transaction.atomic()` scopes, no I/O inside, events emitted inside.
8. Full type hints.

```python
"""Cancel an order and release its reserved stock.

An order is cancelled at most once: a repeated call returns the same result
without releasing stock twice. The status change, the stock release, the audit
event, and the `order.cancelled` event commit together or not at all.

The order row is locked because a payment callback may complete the same order
concurrently; whichever transition commits first wins and the other observes
the new state.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from django.db import transaction

from access.services import audit
from access.services.policy import require
from access.services.scoping import scope_by_organization
from events.services.emitter import emit
from orders.events import OrderCancelled
from orders.models import Order
from orders.services.order_states import transition_order


@dataclass(frozen=True, slots=True)
class CancellationResult:
    order_id: uuid.UUID
    already_cancelled: bool


def cancel_order(*, principal, order_id: uuid.UUID, reason_code: str) -> CancellationResult:
    """Cancel an order on behalf of the principal.

    Raises `InvalidOrderTransition` when the order is past cancellation. Emits
    `order.cancelled` and writes an `order.cancel` audit event.
    """
    with transaction.atomic():
        order = (
            scope_by_organization(Order.objects.all(), principal)
            .select_for_update()
            .get(id=order_id)
        )
        require(principal, action="order.cancel", resource=order)
        if order.status == Order.Status.CANCELLED:
            return CancellationResult(order_id=order.id, already_cancelled=True)
        transition_order(order, to=Order.Status.CANCELLED, cancel_reason_code=reason_code)
        audit.record(principal=principal, action="order.cancel", target=order,
                     metadata={"reason_code": reason_code})
        emit(OrderCancelled.from_principal(principal, subject_id=order.id,
                                           organization_id=order.organization_id,
                                           reason_code=reason_code))
    return CancellationResult(order_id=order.id, already_cancelled=False)
```

## 6. Writing a view

```python
class OrderCancelView(APIView):
    throttle_scope = "orders.write"

    @extend_schema(**ORDER_CANCEL_SCHEMA)
    def post(self, request, order_id):
        serializer = OrderCancelRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = cancel_order(
            principal=principal_from_request(request),
            order_id=order_id,
            reason_code=serializer.validated_data["reason_code"],
        )
        return Response(present_order_cancellation(result))
```

- Errors are rendered by the project exception handler (`api.md` §7). Views do not
  catch and re-render domain errors.
- A view never imports `django.db.transaction` (enforced).
- Sensitive routes declare `authentication_classes`, `permission_classes`, and
  `throttle_classes` explicitly.
- `APIView` versus `ViewSet`, URL shape, and pagination style come from the profile
  (`api.md` §1).

## 7. Serializers

- Input and output serializers are separate classes for any resource with
  server-controlled fields (`OrderCreateRequestSerializer`, `OrderSerializer`).
- Every input serializer rejects unknown fields through one shared mixin:

```python
class StrictFieldsMixin:
    """Reject request fields the serializer does not declare.

    A client that misspells a field must be told, not have the field silently
    ignored and the request processed with a default it did not ask for.
    """

    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            unknown = set(data.keys()) - set(self.fields)
            if unknown:
                raise serializers.ValidationError(
                    {name: [_("Unknown field.")] for name in sorted(unknown)},
                    code="unknown_field",
                )
        return super().to_internal_value(data)
```

- Server-controlled fields are read-only. `fields = "__all__"` is forbidden on input.
- What a serializer validates, and what it leaves to other layers: `api.md` §5.

## 8. Tasks and management commands

```python
@shared_task(name="orders.expire_unpaid_order", acks_late=True, reject_on_worker_lost=True)
def expire_unpaid_order(order_id: str) -> None:
    """Expire an unpaid order; the service decides everything from durable state."""
    expire_order_if_unpaid(order_id=uuid.UUID(order_id))
```

- The first argument is the owning record's ID as a string. Never pass model
  instances or large payloads.
- Task names and arguments are contracts: renaming one strands queued messages.
- Management commands support `--dry-run` and bounded batches, print a summary,
  call the same service as the rest of the code, and write an audit event for data
  changes.

## 9. Exceptions, metrics, checks

- `exceptions.py`: `DomainError` subclasses only (`api.md` §6).
- `metrics.py`: counters and histograms incremented by the working process, plus
  DB-snapshot metrics (backlog, stuck rows, dead jobs) computed on scrape.
- `checks.py`: `@register()` system checks for configuration that must be valid
  before serving.

## 10. Growing a domain: sub-packages, protocols, registries, facades

```text
payments/services/
├── gateways/
│   ├── base.py            # typing.Protocol: the interface
│   ├── registry.py        # key -> implementation; no if/elif chains elsewhere
│   ├── exceptions.py      # retryable / permanent / ambiguous
│   ├── <provider>_gateway.py
│   └── fake_gateway.py    # the test implementation
└── payment_initiation.py
```

- **Protocol + registry**: implementations are chosen by configuration or key,
  never by `if provider == "x"` scattered through the code.
- **Dependency inversion**: a lower layer that needs something from a higher layer
  defines a `Protocol`, or emits a domain event, instead of importing upward.
- **Facades**: when a module is split, the old module re-exports the public names,
  and a test asserts each name's real `__module__`.
- **Domain / service / presentation**: services return dataclasses; presenters
  build wire dicts.

## 11. Resource-oriented packages

For a back-office API with many resources:

```text
backoffice/
├── core/         capabilities.py permissions.py principal.py errors.py
│                 pagination.py filters.py idempotency.py audit.py redaction.py
└── resources/
    ├── users/    views.py serializers.py services.py policy.py
    └── orders/   views.py serializers.py services.py policy.py
```

Every resource folder has the same file set. Large registries are split by area
(`registry_orders.py`), with shared types in `registry_base.py`.

## 12. Test organization

- One `tests/` package per app, with `support.py` for factories and base classes
  (no runnable tests in it).
- One test file per behavior or feature, never one per source file.

| File pattern | Kind |
|---|---|
| `test_<feature>.py` | Service and integration tests |
| `test_<feature>_postgres.py` | Needs PostgreSQL behavior (`testing.md` §4) |
| `test_<feature>_concurrency.py` | Races with real commits |
| `test_<resource>_access_matrix.py` | Foreign IDs × endpoints; roles × actions |
| `test_<resource>_api_contract.py` | Wire shapes, statuses, error envelopes |
| `test_<app>_events.py` | Events emitted and handled |
| `common/tests/test_*.py` | Architecture and convention enforcement |

- Class and method names read like a specification: `ListingsNeverLeakTests`,
  `test_cancel_twice_returns_same_result_without_second_stock_release`.
- Never name tests after a ticket, plan step, sprint, or review round.

## 13. When to split a file

Split a module when any of these is true:
- it holds more than one aggregate or workflow;
- two unrelated reasons would make you edit it;
- it passes about 400–500 lines and is not one cohesive concept;
- its tests naturally fall into separate files.

Keep a facade if other modules import the old path, and update every dotted-path
string in the same change.

## 14. Forbidden patterns

- `utils.py` / `helpers.py` catch-alls.
- Business logic in views, serializers, signals, or models.
- A second implementation of an existing workflow "for this endpoint only".
- Direct owner-ID comparisons instead of the policy service (`security.md` §2).
- Tests outside `tests/`, or test factories in production modules.
- Inconsistent suffixes, and ticket- or step-named files.

## 15. Recipe: add a management command

1. Name it `<verb>_<object>`, in the owning app's `management/commands/`.
2. Call the same service as the rest of the code. The command parses arguments and
   prints a summary.
3. Support `--dry-run`, a bounded `--batch-size`, and filters.
4. Write an audit event for data changes (actor type `system` or `staff`).
5. Tests: the dry run changes nothing, and a real run changes exactly the selected rows.
