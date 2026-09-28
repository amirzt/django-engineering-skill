# opinionated-api: stack

## Contents

1. Pinned versions
2. Allowed extras
3. Forbidden and not used
4. Formatting and code conventions
5. Names
6. Tooling
7. CI
8. Git
9. Canonical commands

---

## 1. Pinned versions

The bootstrap copies this table into the project policy's `## Pinned versions`,
resolving every "pin at bootstrap" entry: the newest stable release that
`pip-audit` reports clean, and image digests from the registry.
`scripts/check_version_drift.py` compares the copied table with the repository.

| Kind | Name | Version |
|---|---|---|
| python | Django | 6.0.8 |
| python | djangorestframework | 3.17.2 |
| python | asgiref | 3.11.1 |
| python | sqlparse | 0.6.0 |
| python | tzdata | 2025.2 |
| python | psycopg | pin at bootstrap (3.x, `psycopg[binary]`) |
| python | djangorestframework-simplejwt | 5.5.1 |
| python | celery | 5.6.3 |
| python | redis | 7.4.1 |
| python | django-redis | 7.0.0 |
| python | gunicorn | 26.0.0 |
| python | uvicorn | 0.52.1 |
| python | django-cors-headers | 4.9.0 |
| python | django-filter | 26.1 |
| python | whitenoise | 6.12.0 |
| python | pillow | 12.3.0 |
| python | orjson | 3.11.9 |
| python | requests | 2.34.2 |
| python | prometheus-client | 0.26.0 |
| python | django-prometheus | 2.5.0 |
| python | sentry-sdk | 2.67.0 |
| python | django-unfold | 0.81.0 |
| python | drf-spectacular | pin at bootstrap |
| python | ruff | 0.15.22 |
| python | mypy | 1.19.1 |
| python | django-stubs | 6.1.0 |
| python | djangorestframework-stubs | 3.18.0 |
| python | coverage | 7.15.4 |
| python | bandit | 1.9.4 |
| python | pip-audit | 2.10.1 |
| python | pip | 26.2.1 |
| image | python | 3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2 |
| image | postgres | pin at bootstrap (17-bookworm@sha256:...) |
| image | edoburu/pgbouncer | v1.25.2-p0@sha256:7d7a27d9e90985cab5cf42256f5c13a3120baa4b055b69df37beb272b89b2340 |
| image | redis | 8.4.6@sha256:8df317692c59703c19ecfa90a8cb17703089f3c8e12c2bd0cd6b3c31005e69d8 |
| image | prom/prometheus | v3.13.1@sha256:3c42b892cf723fa54d2f262c37a0e1f80aa8c8ddb1da7b9b0df9455a35a7f893 |
| image | grafana/grafana | 12.3.1@sha256:2175aaa91c96733d86d31cf270d5310b278654b03f5718c59de12a865380a31f |
| action | actions/checkout | 11d5960a326750d5838078e36cf38b85af677262 |

- Redis 8.4.6 is pinned because it fixes ACL checks that rejected AOF transaction
  replay. Re-qualify session survival across a restart before moving to another 8.x.
- Python 3.12 is required by Django 6.0.

## 2. Allowed extras

Allowed only when a feature needs them, with the owner's approval:
- `django-fernet-encrypted-fields` (encrypted sensitive fields);
- `jdatetime` (Jalali display, `profiles/iran.md`);
- `openpyxl`, `python-docx`, `pypdf`, `xlrd` (document import and export).

Each approved extra is added to the policy's pinned table.

## 3. Forbidden and not used

| Never use | Use instead |
|---|---|
| `pickle` (Celery, cache, files) | JSON |
| SQLite outside the hermetic test tier | PostgreSQL 17 |
| psycopg2 | psycopg 3 |
| Poetry, pipenv, conda, or uv as the project manager | pip + `pylock.toml` |
| pytest | Django's test runner with `config.test_runner.ProjectTestRunner` |
| A second primary database or another broker | PostgreSQL; Redis as broker |
| GraphQL, Channels/WebSockets, gRPC | REST over DRF (anything else needs an ADR) |
| `ViewSet`/`ModelViewSet` and routers | Explicit `APIView`/generic views with `path()` |
| Session or `TokenAuthentication` for the API | JWT Bearer; sessions only for the admin |
| `rest_framework_simplejwt.token_blacklist` | The Redis allowlist |
| Offset or page-number pagination | Cursor pagination (`api-values.md` §4) |
| Object storage | Local volume, proxy delivery (`infrastructure.md` §7) |
| `CELERY_TASK_ALWAYS_EAGER = True` | Call services; `captureOnCommitCallbacks` |

## 4. Formatting and code conventions

- Every module starts with its docstring, then `from __future__ import annotations`.
- ruff format, line length 88, double quotes. Absolute imports only.
- PEP 604 unions, builtin generics, `collections.abc`, and `typing.Protocol`.
- Value objects: `@dataclass(frozen=True, slots=True)`. Events:
  `@dataclasses.dataclass(frozen=True, kw_only=True)`.
- `TextChoices` values are lowercase snake_case. Code-only vocabularies use `StrEnum`.
- Logging: `logger = logging.getLogger(__name__)`, constant event names, and `extra=`.

## 5. Names

**Apps**:
- `config` (composition), `common` (primitives, not an app), `events`;
- `accounts` (custom user `accounts.User`, created before the first migration);
- `access` (tenancy, policy, audit), `files`, `notifications`;
- `backoffice` (staff API, if any), `deploy` (tooling).

**Settings modules**:
- `config.settings.local`, `test` (hermetic), and `test_postgres`;
- `ci`, `build` (collectstatic), and `migration` (migration role);
- `production` (staging and production).

**Naming formats**

| Thing | Format | Example |
|---|---|---|
| Constraint | `<app>_<model>_<rule>_(uniq\|chk)` | `orders_order_total_non_negative_chk` |
| Index (≤ 30 chars) | `<short app>_<short cols>_idx` | `ord_org_created_idx` |
| Input / output serializer | `<Resource><Action>RequestSerializer` / `<Resource>Serializer` | `OrderCreateRequestSerializer` |
| View | `<Resource>ListView`, `<Resource>DetailView`, `<Resource><Action>View` | `OrderCancelView` |
| URL name / OpenAPI operation | `<resources>-<action>` / `<resources>_<action>` | `orders-cancel` |
| Policy and audit action | `<resource>.<verb>` | `order.cancel` |
| Domain event / class | `<resource>.<past_participle>` / `<Resource><PastParticiple>` | `order.cancelled` / `OrderCancelled` |
| Error code / exception | snake_case / PascalCase condition | `order_not_cancellable` / `OrderNotCancellable` |
| Celery task | `<app>.<verb>_<object>` | `orders.expire_unpaid_order` |
| Setting and env var | `<APP>_<THING>_<UNIT>` | `ORDERS_PAYMENT_WINDOW_SECONDS` |
| Redis key | `<app>:<purpose>:v<N>:<id>` | `accounts:jwt-access:v1:<jti>` |
| Metric | `<app>_<noun>_<unit or total>` | `orders_cancelled_total` |
| Branch | `feature/`, `fix/`, `chore/`, `docs/` + slug | `feature/order-refunds` |
| Docker volume | `<project>_<service>_data` | `<project>_postgres17_data` |

## 6. Tooling

- `pyproject.toml`: `assets/project/pyproject.toml` (ruff rules including `PGH`,
  strict mypy with the Django and DRF plugins, branch coverage with
  `fail_under = 85`, bandit).
- Dependency files:
  - `requirements-bootstrap.txt`: pip, hash-pinned;
  - `requirements.txt`: runtime pins;
  - `requirements-dev.txt`: tool pins;
  - `pylock.toml`: generated by `pip lock --only-binary=:all: -r requirements.txt -o pylock.toml`
    and committed.
- A manual CI workflow (`workflow_dispatch`) proposes lock updates as an artifact
  for review.

## 7. CI

GitHub Actions:
- runs on push and pull request to `main`;
- `permissions: contents: read` (plus `packages: write` only to publish);
- `timeout-minutes: 30`;
- actions pinned by full commit SHA, with the version in a comment.

Jobs, in order:
1. git-history secret scan;
2. build the `ci` image stage;
3. `deploy/run_quality_gates.py`;
4. the PostgreSQL tier;
5. `check --deploy` with production settings;
6. `deploy/check_version_drift.py` and `deploy/validate_project_policy.py`;
7. on `main`, publish the `runtime` image tagged with the git SHA.

CI secrets are generated per run and never printed.

## 8. Git

- `main` is protected: changes arrive through pull requests with green CI.
- Conventional Commits: `<type>(<scope>): <imperative subject ≤ 72 chars>`.
  - Types: `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `build`, `ci`, `chore`.
  - Scope: an app, or `config`, `common`, `deploy`, `deps`.
- One logical change per commit. A migration goes with its model change. Lock
  updates are their own pull request.
- Never force-push shared branches. The agent commits only when asked.

## 9. Canonical commands

| Purpose | Command |
|---|---|
| Start the local stack | `docker compose -f docker-compose.dev.yml up -d --no-build` |
| Start workers / beat | `... --profile workers up -d --no-build` / `... --profile scheduler up -d --no-build` |
| Quality gate | `python deploy/run_quality_gates.py` |
| Hermetic tests | `python manage.py test --settings=config.settings.test --parallel` |
| PostgreSQL tests | `python manage.py test --settings=config.settings.test_postgres` |
| Missing migrations | `python manage.py makemigrations --check --dry-run` |
| Migration safety | `python deploy/check_migration_safety.py` |
| Generate / check docs | `python deploy/generate_docs.py` / `... --check` |
| Version drift | `python deploy/check_version_drift.py` |
| Policy check | `python deploy/validate_project_policy.py` |
| Deploy check | `python manage.py check --deploy --settings=config.settings.production` |
| Local backup | `docker compose -f docker-compose.dev.yml exec -T db pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > backups/$(date +%Y%m%d-%H%M)-<reason>.dump` |
| Apply migrations locally | `docker compose -f docker-compose.dev.yml --profile operations run --rm migrate` |
| Seed reference data | `python manage.py seed_reference_data` |
| Lock candidate / audit | `pip lock --only-binary=:all: -r requirements.txt -o pylock.toml` / `pip-audit -r requirements.txt` |
