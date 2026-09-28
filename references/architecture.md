# Architecture

The modular-monolith shape, the layer order, how it is enforced, where new code
belongs, and how settings are structured.

## Contents

1. Modular monolith
2. Layer order
3. Enforcement
4. Deciding ownership of new code
5. Settings and configuration
6. Recipe: add an app
7. Recipe: add a setting

---

## 1. Modular monolith

- One deployable Django project split into **bounded apps**, each owning its models,
  rules, and service API.
- No microservices and no generic repository layer without an ADR.
- One **central path per kind of side-effecting work**: one payment pipeline, one
  gateway per external system, one asset service, one event emitter. New features
  extend it; they never bypass it.

## 2. Layer order

A directed dependency graph, lowest first:

```text
common/                     infrastructure primitives; imports no app
  ^
events                      domain events, outbox, handler registry
  ^
foundational apps           identity, tenancy and authorization, audit
  ^
shared subsystems           files, notifications
  ^
feature apps                siblings; call each other only through services
  ^
back-office, config, deploy composition, admin, tooling
```

- Lower layers **never** import higher layers. When a lower layer must cause an
  effect in a higher one, it emits a domain event that the higher layer handles
  (`events-and-jobs.md`).
- Sibling feature apps call each other only through service functions, and only in
  the directions recorded in `config/architecture.py`.
- Every accepted exception is written down with its reason, in
  `config/architecture.py` (as an allowed import) and in an ADR. A hidden exception
  is a defect.
- A component isolated for security (a parser without network access, for
  example) imports nothing first-party, and a test enforces that.

## 3. Enforcement

`config/architecture.py` (from `assets/project/config/`) is the single
machine-readable statement of the architecture:

- `PROJECT_APPS`: the project's apps, lowest layer first;
- `ALLOWED_IMPORTS`: package → first-party packages it may import;
- `INTEGER_PK_MODELS`, `EVIDENCE_MODELS`, `MONEY_INTEGER_SUFFIXES`: model rules;
- `APPROVED_SIGNAL_RECEIVERS`, `CELERY_QUEUES`: event and task rules.

`common/tests/test_module_boundaries.py` fails when:
- a package imports a layer it may not;
- a project app is missing from `ALLOWED_IMPORTS`;
- a view module mentions `transaction`;
- a `utils.py`, `helpers.py`, or `misc.py` exists.

Keep `AGENTS.md`'s "Apps and layer order" section in sync with this file.

## 4. Deciding ownership of new code

1. The app that owns the **data** the code writes owns the code.
2. A primitive with no domain meaning (retry, hashing, SSRF, rate limit) goes in
   `common/`, in a module named for its job.
3. A cross-app workflow lives in the **highest** app involved and calls the lower
   apps' services. A reaction from a lower app to a higher one is a domain event.
4. Still unclear: ask (`workflow.md` §4), and record the decision in an ADR.

## 5. Settings and configuration

- Settings are split by concern under `config/settings/components/`: for example
  `django_core.py`, `database.py`, `redis_and_celery.py`, `auth_and_api.py`,
  `security.py`, `storage.py`, `observability.py`, and `<feature>_limits.py`.
  `base.py` imports them in order. Each environment module (`local`, `test`,
  `production`, ...) does `from .base import *` and then overrides.
- A component that needs another component's value **imports it explicitly**. Two
  components never define the same name.
- **Every tunable value is a setting**, read through `config/settings/env.py`
  helpers that fail on malformed input:

```python
def env_int(name: str, default: int | None = None, *, minimum: int | None = None) -> int:
    raw = os.environ.get(name)
    if raw in (None, ""):
        if default is None:
            raise ImproperlyConfigured(f"{name} is required.")
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise ImproperlyConfigured(f"{name} must be an integer.") from error
    if minimum is not None and value < minimum:
        raise ImproperlyConfigured(f"{name} must be >= {minimum}.")
    return value
```

- Defaults come from the project policy and its profiles. Code never hardcodes them.
- `.env.example` lists every variable with a comment. It changes in the same change
  as the setting and every reader. `common/tests/test_code_documentation.py`
  enforces this for every `env_*("NAME")` call.
- Production settings **fail fast** at import on unsafe values: a weak
  `SECRET_KEY`, `DEBUG=True`, empty `ALLOWED_HOSTS`, plaintext database transport
  outside the private network, or a missing required secret
  (`security.md` §9).

## 6. Recipe: add an app

1. Choose its name and layer (§2).
2. Add it to `PROJECT_APPS` and `ALLOWED_IMPORTS` in `config/architecture.py`, and
   to `AGENTS.md`.
3. Create the skeleton (`file-organization.md` §2): `apps.py` (with `ready()`
   importing `handlers.py`), `models/__init__.py`, `services/`, `exceptions.py`,
   `events.py`, `handlers.py`, `urls/`, and `tests/support.py`.
4. Add it to `INSTALLED_APPS` and to the coverage `source` list.
5. Include its URLs under the API prefix.
6. Create `docs/features/<app>.md` from the template (`comments-and-docs.md` §4).
7. Verify: the quality gate passes with the empty app.

## 7. Recipe: add a setting

1. Name it `<APP>_<THING>_<UNIT>` (the profile may fix a different convention).
2. If it is a fixed project value, record it in the project policy first (owner
   approval, `workflow.md` §3).
3. Read it in the right component module through the `env.py` helpers (§5).
4. Add it to `.env.example` with a comment and its default.
5. Add production validation if a wrong value is dangerous.
6. Tests: the documentation test passes, and the validation rejects a bad value.
