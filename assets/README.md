# Project kit

`assets/project/` mirrors a repository root. The bootstrap copies it into a new
project (`bootstrap/README.md` step 3), and the files then belong to the project
and run in its CI.

| Path | What it is | Adapt |
|---|---|---|
| `pyproject.toml` | ruff, strict mypy, coverage (85% branch), bandit | Add every package to `coverage.run.source` |
| `config/architecture.py` | Apps, layer order, model/event rules, queues, doc paths | Fill in the project's apps and queues |
| `config/test_egress.py`, `config/test_runner.py` | Blocks real network access in tests | Set `TEST_ALLOWED_EGRESS_HOSTS` in test settings |
| `common/model_bases.py` | `PublicModel`, `TimestampedModel`, `AppendOnlyModel` | none |
| `common/errors.py` | `ErrorCategory`, `DomainError` (unique codes), `DependencyUnavailable`, `PolicyDenied` | none |
| `common/api_errors.py` | The DRF exception handler and error envelope | Set `REST_FRAMEWORK["EXCEPTION_HANDLER"]` |
| `common/constraint_errors.py` | `raise_for_constraint` | none |
| `common/external_errors.py` | Retryable / permanent / ambiguous error classes | none |
| `common/observability.py` | `request_id_var`, `job_id_var`, JSON formatter, correlation filter | Reference them from `LOGGING` |
| `common/durable_jobs.py` | Claim, lease, fence, retry, dead-letter | none |
| `common/migration_operations.py` | `PostgresOnlySQL` | none |
| `common/tests/` | Enforcement tests (boundaries, models, events, docs) and infrastructure tests | none; they read `config/architecture.py` |
| `events/` | `DomainEvent`, `emit`, handler registry, `OutboxEvent`, `EventDelivery`, dispatcher, tasks, migration, tests | Add a beat entry for `events.dispatch_due_deliveries` |
| `deploy/_django.py` | Django setup for scripts run by path | none |
| `deploy/run_quality_gates.py` | The single quality gate | Set `QUALITY_GATE_TEST_SETTINGS` if the test settings module differs |
| `deploy/check_migration_safety.py` | Expand-only unless `CONTRACT_APPROVED` | none |
| `deploy/generate_docs.py` | Data dictionary, error catalog, event catalog, OpenAPI | none |

Required settings: `DURABLE_JOB_MAX_ATTEMPTS`, `DURABLE_JOB_BACKOFF_SECONDS`,
`DURABLE_JOB_BACKOFF_MAX_SECONDS`, `DURABLE_JOB_LEASE_SECONDS`,
`DURABLE_JOB_SWEEP_BATCH_SIZE`, and `CELERY_BROKER_URL` (`memory://` in tests).

The kit expects `prometheus-client` and `celery` to be installed, and Python 3.12+.
