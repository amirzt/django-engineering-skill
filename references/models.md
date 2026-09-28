# Models

How models are designed, documented, and checked, plus deletion, retention, and
reference data. Concurrency and state transitions are in `data-integrity.md`.
Migrations are in `migrations-and-deployment.md`.

## Contents

1. Abstract bases
2. Layout inside a model class
3. The model contract (required docstring)
4. Fields and types
5. Relations
6. Meta
7. Constraints and indexes
8. Methods
9. QuerySets and managers
10. Status fields
11. Tenant-owned models
12. Evidence models
13. Deletion and retention
14. Reference data and seeds
15. Data dictionary
16. Enforcement
17. Complete example
18. Recipe: add or change a model or field
19. Recipe: change reference data

---

## 1. Abstract bases

`common/model_bases.py` (from `assets/project/`) provides:
- `PublicModel`: UUID `id`, `created_at`, `updated_at`. The default for every model.
- `TimestampedModel`: integer key, for internal lookup tables listed in
  `INTEGER_PK_MODELS` with a reason.
- `AppendOnlyModel`: UUID `id` and `created_at`. `save()` refuses updates, and its
  QuerySet refuses `update()`/`delete()`. For evidence.

Rules:
- Every concrete model inherits one of these.
- No multi-table inheritance: abstract bases only.
- No `GenericForeignKey`: use explicit foreign keys, or `target_type` +
  `target_id` strings for audit-style references.

## 2. Layout inside a model class

1. The class docstring: the model contract (§3).
2. Nested `TextChoices` classes.
3. Fields, in groups separated by a blank line:
   1. identity (only if not inherited);
   2. ownership and tenant (`organization`, `project`, `created_by`);
   3. relations to other aggregates;
   4. business fields;
   5. status and lifecycle (`status`, `<event>_at`, `attempt_count`, `lease_expires_at`);
   6. metadata (`metadata`, `error_code`).
4. The manager (`objects = OrderQuerySet.as_manager()`).
5. `class Meta`.
6. `__str__`.
7. `clean()`.
8. `save()`, only when needed (§8).
9. Properties.
10. Other small row-level methods.

## 3. The model contract (required docstring)

```python
class Order(PublicModel):
    """A customer's order for catalog items.

    Owner: orders.
    Tenant scope: organization.
    Lifecycle: pending -> paid -> fulfilled; pending or paid -> cancelled.
        Terminal: fulfilled, cancelled. Transitions only through
        `orders.services.order_states.transition_order`.
    Invariants:
        - total_irr is never negative (orders_order_total_non_negative_chk).
        - An idempotency key is unique per organization
          (orders_order_org_idempotency_key_uniq).
    Data classification: internal; shipping_phone is personal.
    Append-only: no.
    Events: order.placed, order.paid, order.cancelled, order.fulfilled.
    """
```

All seven headings are required ("none" is a valid value): `Owner:`,
`Tenant scope:`, `Lifecycle:`, `Invariants:`, `Data classification:`,
`Append-only:`, `Events:`. The data classes are in `security.md` §7.

## 4. Fields and types

| Data | Field |
|---|---|
| Short text | `CharField(max_length=N, blank=True, default="")`, never `null=True` |
| Long text | `TextField(blank=True, default="")`, bounded in the service |
| Status | `CharField(max_length=30, choices=X.Status.choices, default=...)` |
| Lifecycle time | `DateTimeField(null=True, blank=True)` named `<event>_at` |
| Money in minor or whole units | `BigIntegerField` named with the unit suffix from `MONEY_INTEGER_SUFFIXES` (e.g. `total_irr`) |
| Money with decimals | `DecimalField(max_digits=20, decimal_places=6)` plus a `currency` field (`CharField(max_length=3)`) on the model |
| Rates and percentages | `DecimalField(max_digits=9, decimal_places=6)` |
| Metadata | `JSONField(default=dict, blank=True)`, bounded and validated (`security.md` §10) |
| Flags | `BooleanField(default=...)`, never nullable |
| Counters | `PositiveIntegerField(default=0)` |
| Hashes and fingerprints | `CharField(max_length=64)`, `editable=False` |

- No `FloatField`, anywhere.
- Mutable defaults are callables (`default=dict`).
- Server-computed fields are `editable=False`.
- `help_text` is required when a field's meaning or unit is not obvious from its
  name (it feeds the data dictionary).
- `null=True` on a foreign key is deliberate, and the contract says what `NULL` means.

## 5. Relations

- Every `ForeignKey`, `OneToOneField`, and `ManyToManyField` declares
  `related_name` (plural snake_case, or `"+"`), unless the model sets
  `Meta.default_related_name`.
- Choose `on_delete` deliberately:
  - `PROTECT` for financial and evidence links;
  - `RESTRICT` for join rows that must block deletion;
  - `SET_NULL` for audit identity (`created_by`);
  - `CASCADE` only for true children that have no meaning without the parent.
- A many-to-many relation with any attribute uses an explicit `through` model.

## 6. Meta

| Option | Rule |
|---|---|
| `verbose_name`, `verbose_name_plural` | Always, with `gettext_lazy` |
| `constraints` | Every invariant that can be one, each named |
| `indexes` | Every index, named |
| `ordering` | Only on small tables. Large tables never set it; list queries order explicitly |
| `default_related_name` | When most relations share one reverse name |
| `db_table` | Never set, except for a legacy table with an ADR |

## 7. Constraints and indexes

- **Constraints are the source of truth** for uniqueness and value rules. A service
  may check first for a friendly message, but the constraint decides, and the
  service maps the violation to a domain error (`api.md` §8).
- Use conditional `UniqueConstraint(condition=...)` for "unique among active rows",
  and `CheckConstraint(condition=...)` for ranges and cross-field rules. The keyword
  is `condition=` in Django 5.1+ (`check=` before).
- Every constraint and index has an explicit `name=`:
  - constraints: `<app>_<model>_<rule>_(uniq|chk)`;
  - indexes: at most **30 characters**, a Django limit.
- **Every index is justified by a query**: a comment above it names the query or
  endpoint.
- On tenant-owned tables, composite indexes start with the tenant column.
- Hot filtered lists use partial indexes (`condition=~Q(status="deleted")`).
- Large existing tables get indexes with `AddIndexConcurrently` in a non-atomic
  migration (`migrations-and-deployment.md` §1).

## 8. Methods

| On the model | In a service |
|---|---|
| `__str__` (short, no queries) | Anything touching another model |
| `clean()` for single-row invariants, mirroring constraints for the admin | Transactions and locks |
| `save()` override only for row invariants, always calling `super().save()` | External calls and file I/O |
| Pure derived properties that **never query** | Emitting events, writing audit |
| Small pure helpers on the row's own fields | Permission checks and state transitions |

`save()` does not call `clean()`. Services rely on constraints and their own checks.

## 9. QuerySets and managers

- A `<Model>QuerySet` holds reusable queries, assigned with
  `objects = <Model>QuerySet.as_manager()`.
- QuerySet methods are **filters** named as phrases (`active()`,
  `for_organization(org_id)`, `due(now)`). They never write, except guard overrides.
- **Never-bypass guards** override `update`, `bulk_update`, or `delete` on the
  QuerySet (for example "a project never changes organization").
- A queryset reachable by a caller is built only through the owning app's scoping
  function (`security.md` §3).

## 10. Status fields

- `status` is a `TextChoices` field, read-only in serializers and admin forms.
- States and legal transitions live in `<thing>_states.py`, and **status changes only
  through the transition function**, which is where events are emitted
  (`data-integrity.md` §5).

## 11. Tenant-owned models

- Every tenant-owned model has an `organization` foreign key (and `project` where
  applicable). `created_by` is audit identity only.
- `save()`, or a constraint where expressible, ensures that related rows belong to
  the same tenant.
- Composite indexes start with the tenant column.

## 12. Evidence models

Ledger entries, payment records, audit events, and similar evidence inherit
`AppendOnlyModel` and are listed in `EVIDENCE_MODELS`. A correction is a
compensating row with its own idempotency key (`data-integrity.md` §6). They are
read-only in the admin.

## 13. Deletion and retention

- Every model is **content** (user-owned, deletable), **evidence** (append-only,
  retained), or **operational** (jobs, outbox, idempotency records; expires). The
  contract states which.
- A user-facing delete of referenced content is a **tombstone**: clear the content
  fields, set `status=deleted`, keep the ID. Evidence is never deleted by a user action.
- Deletion is refused while work is active on the object
  (`deletion_blocked_active_work`).
- External side effects run after commit: `on_commit(robust=True)` for best effort,
  or a durable job when they must be guaranteed (`events-and-jobs.md` §10).
- Retention periods are settings. A periodic purge selects IDs in bounded batches,
  and deletes or redacts each batch in its own short transaction. Never an
  unbounded `delete()`.
- If the product offers "delete my data", it truly deletes. The feature document
  states what is removed, what is kept, and why.

## 14. Reference data and seeds

- Reference data (roles, plans, lookup tables, holiday calendars) is loaded by one
  idempotent command, `seed_reference_data`, from versioned JSON in `deploy/seeds/`.
  It upserts by natural key and never deletes rows it did not create.
- Seeds never contain secrets, credentials, user data, or tenant data.
- Tests load the same seed (through a `post_migrate` hook or the test runner).

## 15. Data dictionary

`deploy/generate_docs.py` writes `docs/data-model.md` from the models: each model's
contract, its fields (type, null, default, help text), constraints, and indexes.
Never edit it by hand. `--check` fails in CI when it is stale.

## 16. Enforcement

`common/tests/test_model_conventions.py` fails when a project model:
- lacks a contract heading;
- lacks `verbose_name` or `verbose_name_plural`;
- lacks `__str__` or `created_at`;
- has a non-UUID primary key and is not listed in `INTEGER_PK_MODELS`;
- has a `FloatField`, or nullable text;
- has a relation without `related_name`;
- has a `status` field without choices;
- has a money field without its unit;
- is an evidence model that is not append-only;
- declares an index or constraint without `name=`.

## 17. Complete example

```python
class Order(PublicModel):
    """<contract as in section 3>"""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        PAID = "paid", _("Paid")
        FULFILLED = "fulfilled", _("Fulfilled")
        CANCELLED = "cancelled", _("Cancelled")

    organization = models.ForeignKey("access.Organization", on_delete=models.CASCADE,
                                     related_name="orders")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="created_orders",
                                   help_text=_("Audit identity only; NULL after the user is deleted."))

    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT,
                                 related_name="orders")

    total_irr = models.BigIntegerField(help_text=_("Order total in whole Rials."))
    idempotency_key = models.CharField(max_length=255, blank=True, default="")

    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING)
    paid_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason_code = models.CharField(max_length=50, blank=True, default="")

    metadata = models.JSONField(default=dict, blank=True)

    objects = OrderQuerySet.as_manager()

    class Meta:
        verbose_name = _("order")
        verbose_name_plural = _("orders")
        constraints = [
            models.CheckConstraint(condition=models.Q(total_irr__gte=0),
                                   name="orders_order_total_non_negative_chk"),
            models.UniqueConstraint(fields=["organization", "idempotency_key"],
                                    condition=~models.Q(idempotency_key=""),
                                    name="orders_order_org_idempotency_key_uniq"),
        ]
        indexes = [
            # GET /orders: organization list, newest first.
            models.Index(fields=["organization", "-created_at", "-id"], name="ord_org_created_idx"),
            # Expiry sweeper: unpaid orders by age.
            models.Index(fields=["status", "created_at"], condition=models.Q(status="pending"),
                         name="ord_pending_created_idx"),
        ]

    def __str__(self) -> str:
        return f"Order {self.id} ({self.status})"

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_ORDER_STATES
```

## 18. Recipe: add or change a model or field

1. Design per §1–§11, and give every field a data class (`security.md` §7).
2. Write or update the contract docstring (§3).
3. Add QuerySet guards (§9), and a transition function if the model is stateful
   (`data-integrity.md` §10).
4. Run `makemigrations`, then **read the migration line by line**. Hand-edit it when
   needed: concurrent indexes, data steps using historical models,
   `PostgresOnlySQL`.
5. Run `deploy/check_migration_safety.py`. A contract operation needs the owner's
   approval and a `CONTRACT_APPROVED` marker (`migrations-and-deployment.md` §2).
6. **Ask before applying** to a database whose data matters (`workflow.md` §3).
   Take a backup, then apply.
7. Update the admin, serializers, and services that read or write the field.
8. Run `deploy/generate_docs.py` (data dictionary).
9. Tests: the model conventions pass, constraint behavior (PostgreSQL tier for
   constraint names), service behavior, and the migration against populated data.

## 19. Recipe: change reference data

1. Edit the versioned JSON in `deploy/seeds/` (§14).
2. Make sure `seed_reference_data` upserts it by natural key.
3. Run the seed twice locally (it must be idempotent), then run the tests.
4. Ship it as its own change.
