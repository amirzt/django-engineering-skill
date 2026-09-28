---
name: django-backend-engineering
description: Design, implement, review, or operate production Django backends - domain-owned apps and service layers, model design and migrations, concurrency-safe persistence, domain events and Celery jobs, DRF APIs and error contracts, authorization and tenancy, Redis, file handling, observability, testing, and deployment. Use when creating or changing Django models, services, endpoints, background work, integrations, security, or operational procedures, when reviewing Django code, or when bootstrapping a new Django project.
---

# Django Backend Engineering

A router skill. Read this file, then read **only** the references the task needs
(section 5). Every reference has a table of contents: open the relevant sections,
not the whole file.

## 1. Precedence

1. Platform, system, and developer instructions.
2. The user's explicit instructions in the conversation.
3. The repository's own instruction files: `AGENTS.md` (including nested ones),
   `CLAUDE.md`, `.github/copilot-instructions.md`, or others the repository defines.
4. The project policy: `docs/engineering/project-policy.md`.
5. This skill: the selected profiles, then the references.

A lower source never overrides a higher one. When they conflict, follow the higher
source and mention the conflict in your reply.

## 2. Find the project's context first

1. Read the repository's instruction files.
2. Read `docs/engineering/project-policy.md` if it exists. It records this
   project's decisions and the **profiles** it selected (`profiles/`), which supply
   concrete values (versions, names, limits, formats).
   - If the policy says `status: template`, the bootstrap is unfinished: run
     `python <skill>/scripts/validate_project_policy.py` and complete it first.
3. If there is no policy:
   - **New project**: follow `bootstrap/README.md`.
   - **Existing project**: follow the repository's existing conventions plus the
     universal references. Do not impose a profile. Offer to create a policy if
     the owner wants one.
4. A profile applies **only** when the policy lists it.

## 3. Workflow for every task

Details and templates are in `references/workflow.md`.

1. Understand the request, and restate the goal.
2. Inspect the code the change touches, its tests, and its docs.
3. Pick the references from section 5.
4. State the invariants and failure modes that apply.
5. For non-trivial work, write the plan **in the chat** (plan files only when asked).
6. Implement in the owning app and module (`references/file-organization.md`),
   with the smallest coherent change.
7. Run focused tests, then the repository's quality gate.
8. Exercise the real flow, and inspect the durable result (rows, events, files).
9. Review your own diff against `references/workflow.md` §6.
10. Hand off with what was run, what passed, and what was not verified.

## 4. Always true

- One responsibility per file, named for it. Never `utils.py`/`helpers.py`.
  Business logic lives in services, never in views, serializers, models, or signals.
- Lower layers never import higher ones. A reaction across layers is a domain event.
- Invariants are database constraints. No check-then-write races. No network or
  storage I/O inside a transaction or lock.
- Querysets are scoped to the caller before lookup. Authorization goes through the
  policy service, and an out-of-scope resource is 404.
- Side-effecting work is idempotent and safe under at-least-once delivery. An
  ambiguous external outcome is never retried automatically.
- Domain events are emitted inside the transaction. Model signals never carry
  business effects.
- No hardcoded IDs, limits, timeouts, URLs, or secrets. Never log secret or
  sensitive data.
- Tests assert durable effects. Never claim a check passed unless it ran.
- Never commit, push, add a dependency, apply migrations to data that matters, or
  run a destructive command without the owner's instruction (`references/workflow.md` §3).

## 5. Routing table

| The task involves | Read |
|---|---|
| Any change (once per session) | `references/workflow.md` |
| Where code goes, a new module or app | `references/file-organization.md`, `references/architecture.md` |
| A setting or configuration | `references/architecture.md` §5 |
| A model, field, or migration | `references/models.md`, `references/migrations-and-deployment.md` |
| A status change, money, locks, idempotency | `references/data-integrity.md` |
| Reacting to a change in another app | `references/events-and-jobs.md` |
| A Celery task, periodic job, retries, dead-letter | `references/events-and-jobs.md`, `references/data-integrity.md` §7 |
| An API endpoint, validation, errors, pagination | `references/api.md`, `references/security.md` §1–§4 |
| Permissions, tenancy, sessions, secrets | `references/security.md` |
| An external integration or inbound webhook | `references/security.md` §12–§13, `references/events-and-jobs.md` §10 |
| File uploads, downloads, storage | `references/files.md` |
| Redis, caching, rate limiting, locks | `references/redis-and-caching.md` |
| Logging, metrics, alerts, health, performance | `references/observability-and-performance.md` |
| Writing or organizing tests | `references/testing.md` |
| Comments, docstrings, documents | `references/comments-and-docs.md` |
| Release, rollback, backup, rotation, incidents, dependencies | `references/operations.md`, `references/migrations-and-deployment.md` |
| A concrete value (version, name, limit, format) | the project policy, then its profiles in `profiles/` |
| Reviewing code | `references/workflow.md` §6, plus the references of the touched areas |
| A new project | `bootstrap/README.md` |

## 6. Bundled resources

- `assets/project/`: files the bootstrap copies into a new repository. They include
  the `common/` primitives, the `events` app, the enforcement tests, and the
  `deploy/` quality gate, migration checker, and docs generator. They were tested
  together on Django 6.0.8 (SQLite and PostgreSQL). `assets/README.md` lists them.
- `scripts/validate_project_policy.py [policy]`: fails while the policy is
  incomplete.
- `scripts/check_version_drift.py --root <repo>`: compares the policy's pinned
  versions with requirements, the lock file, Dockerfiles, compose files, and CI.
- `profiles/opinionated-api/`: the owner's default stack (DRF, JWT with Redis
  revocation, Celery, cursor pagination, explicit views, local media, fixed tooling).
- `profiles/iran.md`: `Asia/Tehran`, `fa` + `en`, Persian text and digit
  normalization, Iranian identifiers, IRR, Jalali display.
