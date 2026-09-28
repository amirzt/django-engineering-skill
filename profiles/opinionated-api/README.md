# Profile: opinionated-api

The owner's default stack for API backends. It applies **only** when the project
policy lists `opinionated-api` in its `profiles`. The policy may override any value
here, and each override is recorded in its `## Profiles and overrides` section.

| File | Decides |
|---|---|
| `stack.md` | Pinned versions, allowed extras, forbidden technologies, formatting, names, tooling, CI, git, canonical commands |
| `infrastructure.md` | PostgreSQL, PgBouncer, Redis, Celery, web server, image, compose topology, storage, observability values, local stack |
| `api-values.md` | URL style, views, list and pagination format, headers, JWT and OTP values, throttles, security settings, all numeric limits |
| `admin.md` | Django admin conventions |

Read only the file the task needs.

**In one paragraph:**
- Django 6.0 + DRF, with explicit `APIView`s and no trailing slashes.
- JWT with a Redis allowlist in a non-evicting Redis, and a second evictable Redis
  for the broker and cache.
- Celery with a fixed queue list, PostgreSQL 17 behind PgBouncer in transaction mode.
- Cursor pagination everywhere, and local media served through the app with signed URLs.
- Django's test runner with SQLite and PostgreSQL tiers.
- ruff, strict mypy, 85% branch coverage, bandit, and pip-audit.
