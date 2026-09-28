# Testing

What every change must test, how tests are organized, the database tiers, the
egress guard, fakes, concurrency tests, the enforcement tests, and the quality
gate. The test runner (Django's or pytest) and the coverage floor come from the
profile.

## Contents

1. Principles
2. Organization and naming
3. Factories
4. Database tiers
5. The egress guard
6. Fakes, not deep patches; time control
7. Enforcement tests
8. Concurrency tests
9. Coverage and typing
10. The quality gate

---

## 1. Principles

- Every change ships with tests for:
  - the happy path and invalid input;
  - authorization, horizontal (other tenant) and vertical (role);
  - idempotency and retries;
  - concurrency where state is contended;
  - emitted events;
  - failure paths: dependency down, timeout, ambiguous outcome.
- Tests assert **durable effects** (rows, states, outbox rows, audit rows, files),
  not only HTTP bodies.
- Use the cheapest adequate base class: `SimpleTestCase` (no DB), `TestCase`, and
  `TransactionTestCase` only when real commits, `on_commit`, or cross-connection
  locks matter.
- Test `on_commit` behavior with `self.captureOnCommitCallbacks(execute=True)`.

## 2. Organization and naming

File layout and names: `file-organization.md` §12.
- Class and method names state behavior:
  `test_cancel_twice_returns_same_result_without_second_stock_release`.
- Never name tests after tickets or plan steps.

## 3. Factories

Factories in `tests/support.py` are plain functions with keyword-only arguments and
sensible defaults:

```python
def make_order(*, organization, status=Order.Status.PENDING, total_irr=100_000) -> Order:
    return Order.objects.create(organization=organization, status=status, total_irr=total_irr)
```

They create only what the test needs, and never call external services.
Production code never imports test support modules.

## 4. Database tiers

| Tier | Database | Runs |
|---|---|---|
| **Hermetic** | SQLite in memory, locmem caches, `memory://` broker | Every test not guarded for PostgreSQL; on every commit, in parallel |
| **PostgreSQL** | The production PostgreSQL major version | The whole suite, including `@skipUnless(connection.vendor == "postgresql", "<reason>")` tests |

- Tests that depend on PostgreSQL behavior carry the guard **with a reason**: row
  locks, `skip_locked`, constraint names, partial indexes, extensions, concurrency.
- One migration history serves both tiers. PostgreSQL-only SQL uses
  `common.migration_operations.PostgresOnlySQL`, which does nothing on SQLite.
- CI runs both tiers. A change is done only when both pass.
- If the profile uses PostgreSQL for every tier, apply its override.

## 5. The egress guard

No test may reach the real network. `config/test_egress.py` (from
`assets/project/`) patches DNS resolution and socket connects for the whole run.
Only `TEST_ALLOWED_EGRESS_HOSTS`, `localhost`, and loopback addresses are allowed.
- Django runner: `TEST_RUNNER = "config.test_runner.ProjectTestRunner"`.
- pytest: call `install_egress_guard()` from a session-scoped fixture in `conftest.py`.
- The rare test that needs a socket opts in visibly with `@allow_network_egress`.

## 6. Fakes, not deep patches; time control

- External systems are replaced at their gateway `Protocol` by a fake implementation
  registered in the gateway registry (`file-organization.md` §10). Never patch deep
  inside a third-party library.
- Control time with one helper in `common/tests/support.py` that patches
  `django.utils.timezone.now`. Never let a test depend on the wall clock.

## 7. Enforcement tests

Copied from `assets/project/common/tests/`. They read `config/architecture.py`:

| Test module | Fails when |
|---|---|
| `test_module_boundaries.py` | a layer is violated, an app is missing from `ALLOWED_IMPORTS`, a view mentions `transaction`, or `utils.py`/`helpers.py`/`misc.py` exists |
| `test_model_conventions.py` | a model breaks `models.md` §16 |
| `test_event_registry.py` | an event name is duplicate or malformed, an event is never emitted, an emitted name is unknown, a handler's event or queue is unknown, a signal receiver is unapproved, or `emit()` works outside a transaction |
| `test_code_documentation.py` | a required docstring is missing, a `noqa`/`type: ignore`/`TODO` lacks its code or reason, an env var read in settings is missing from `.env.example`, a Celery task is missing from the task map, or a relative doc link is broken |
| `test_api_errors.py`, `test_infrastructure.py` | the error envelope, the status mapping, append-only models, JSON logging, or `PostgresOnlySQL` regress |

## 8. Concurrency tests

```python
@skipUnless(connection.vendor == "postgresql", "requires real row locks")
class StockReservationConcurrencyTests(TransactionTestCase):
    def test_two_reservations_cannot_oversell_the_last_item(self):
        product = make_product(stock=1)
        barrier = threading.Barrier(2)
        results: list[str] = []

        def attempt() -> None:
            try:
                barrier.wait()
                reserve_stock(product_id=product.id, quantity=1, idempotency_key=str(uuid.uuid4()))
                results.append("reserved")
            except OutOfStock:
                results.append("refused")
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertCountEqual(results, ["reserved", "refused"])
```

`events/tests/test_delivery_claims_postgres.py` is a working example (claim contention).

## 9. Coverage and typing

- Branch coverage, with a floor that never goes down (the profile sets it).
- Strict mypy with the Django and DRF plugins. A greenfield project is strict
  everywhere, and a new module is strict on the day it lands.

## 10. The quality gate

`deploy/run_quality_gates.py` is the single entry point for developers and CI. It
fails when a pinned tool is missing, and runs in order:
1. ruff check and format check;
2. mypy;
3. `manage.py check`, and `makemigrations --check --dry-run`;
4. `deploy/check_migration_safety.py`;
5. `deploy/generate_docs.py --check`;
6. the tests with coverage, then the coverage floor;
7. bandit;
8. pip-audit.

`--list` shows the steps, and naming steps runs only those (for local iteration;
CI always runs everything). CI also runs:
- the PostgreSQL tier;
- the git-history secret scan;
- `check --deploy` with production settings;
- `deploy/check_version_drift.py` and `deploy/validate_project_policy.py`
  (copied from this skill's `scripts/` at bootstrap);

all inside the image that ships.
