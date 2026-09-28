# Bootstrapping a new project

Follow these steps in order for a new repository. Only the modules the answers
call for are added, so a small internal tool does not receive machinery it does
not need.

## Steps

1. **Ask the questionnaire** (`questionnaire.md`) in one message. Show the default
   answers, and wait for the owner's answers or "use the defaults". Login and
   authentication have no default: the owner must answer. If the repository's
   `AGENTS.md` already records answers (a bootstrap-answers table), treat them as
   given, and ask only about the missing ones and those marked `<fill>`.
2. **Select modules** from the answers (`questionnaire.md`, "What the answers add").
3. **Copy the kit** into the repository root:
   - everything under `assets/project/` (see `assets/README.md`);
   - `scripts/validate_project_policy.py` and `scripts/check_version_drift.py` into `deploy/`.
4. **Declare the architecture** in `config/architecture.py`:
   - `PROJECT_APPS` and `ALLOWED_IMPORTS` for the selected apps;
   - `CELERY_QUEUES` from the profile;
   - `MONEY_INTEGER_SUFFIXES`;
   - the documentation paths.
5. **Settings** (`references/architecture.md` §5):
   - `config/settings/components/` and the environment modules named by the profile;
   - `env.py`, `.env.example`, and production validation;
   - `REST_FRAMEWORK["EXCEPTION_HANDLER"] = "common.api_errors.exception_handler"`;
   - `TEST_RUNNER = "config.test_runner.ProjectTestRunner"`;
   - the `DURABLE_JOB_*` settings.
6. **Celery**: `config/celery.py` with the correlation hooks
   (`references/events-and-jobs.md` §9), `config/__init__.py` loading the app, and a
   beat entry for `events.dispatch_due_deliveries` every minute.
7. **Project policy**: copy `project-policy.template.md` to
   `docs/engineering/project-policy.md`, and fill every section:
   - copy the selected profile's pinned-versions table and resolve every
     "pin at bootstrap" entry (newest stable release that `pip-audit` reports clean,
     and image digests from the registry);
   - set `status: initialized`;
   - run `python deploy/validate_project_policy.py` until it passes.
8. **Repository instructions**:
   - `AGENTS.md`: if it does not exist, create it from `AGENTS.md.template`. If it
     exists, **keep it**: never overwrite the owner's file. Fill only the sections it
     marks as filled by the bootstrap, and replace its bootstrap answers with a
     pointer to the policy's `## Decisions`, where they now live.
   - `CLAUDE.md`: if it does not exist, create it from `CLAUDE.md.template`. If it
     exists without an `@AGENTS.md` line, ask the owner before changing it.
9. **Dependencies and containers** per the profile: requirements files, `pylock.toml`,
   `pyproject.toml` (from assets), the Dockerfile, compose files, and CI.
10. **Foundational apps**, only as selected:
    - `accounts` (the custom user **before the first migration**);
    - `access` (principal, policy, scoping, audit);
    - `files`, `notifications`.

    Each follows its reference.
11. **Docs skeleton**:
    - `docs/features/celery.md` listing `events.dispatch_due_deliveries` and
      `events.deliver_event`;
    - `docs/features/redis.md`;
    - `docs/decisions/001-adopt-engineering-policy.md`;
    - then `python deploy/generate_docs.py`.
12. **Verify**:
    - `makemigrations`, and read the migrations;
    - the quality gate and both test tiers;
    - `python deploy/check_version_drift.py`;
    - the stack starts, and `/health/ready` is green.

    Report per `references/workflow.md` §8.

## What the kit already proves

The files in `assets/project/` were tested together with Django 6.0.8, DRF 3.17.2,
Celery 5.6.3, on SQLite and PostgreSQL 16, using the profile's ruff and strict mypy
configuration:
- the kit's 50 tests pass on PostgreSQL, and on SQLite with the 2 PostgreSQL-only
  tests skipped;
- the enforcement tests catch deliberate violations;
- the migration checker flags an unapproved `RemoveField`;
- the docs generator detects stale documents.

Re-run the gate after adapting them. A project on another Django version must
check the APIs that changed between versions.
