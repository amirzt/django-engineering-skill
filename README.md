# Django Backend Engineering

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/amirzt/django-engineering-skill/actions/workflows/ci.yml/badge.svg)](https://github.com/amirzt/django-engineering-skill/actions/workflows/ci.yml)

A [Claude Code / Agent Skill](https://docs.claude.com/en/docs/claude-code/skills) that
makes AI agents write **production-grade Django backends**, consistently, across
every project they touch.

Point an agent at this skill and it stops improvising architecture on every task.
Instead it follows one set of rules for where code goes, how invariants are
enforced, how errors are shaped, how background jobs are made idempotent, and how
a change gets reviewed before it ships — the same rules every time, for every
project that adopts it.

## Why use this

AI agents are good at writing Django code and bad at staying consistent about
it: one task puts business logic in a view, the next in a signal, the next in
a serializer. Invariants get enforced with `if` statements instead of
database constraints. Retries happen for operations that aren't safe to
repeat. Every project — and often every session within the same project —
ends up with a different shape.

This skill is an opinionated answer to that, for three reasons:

- **The rules survive between sessions.** A fresh agent session has no memory
  of the last one's decisions. This skill puts those decisions in a
  `references/` file and a project policy, so every session reads the same
  rules instead of re-deriving (and re-drifting from) them.
- **Correctness is enforced, not just requested.** The bootstrap kit ships
  database constraints, guarded updates, a migration-safety checker, and
  automated tests that fail CI when the architecture rules are broken —
  instead of relying on an agent (or a reviewer) to remember to check.
- **It defers to what's already there.** The skill reads a repository's own
  `AGENTS.md`, `CLAUDE.md`, and project policy first, and only fills in
  where the project hasn't already decided something (see
  [Precedence](#precedence)). It's meant to reduce drift, not to impose
  itself on a codebase that already has conventions.

## What it adds to your project

Adopting this skill (via the bootstrap, see [Quick start](#quick-start))
brings in the following, all real and tested, not just guidance:

| Adds | Why |
|---|---|
| **Model bases** — `PublicModel`, `TimestampedModel`, `AppendOnlyModel` | Public-facing IDs that don't leak sequential row counts, consistent `created_at`/`updated_at`, and a base for records that must never be mutated after creation (audit trails, ledgers). |
| **A domain error taxonomy** — `DomainError`, `ErrorCategory`, `DependencyUnavailable`, `PolicyDenied` | One vocabulary for "why did this fail" across the whole codebase, instead of every app inventing its own exceptions. |
| **A DRF exception handler + error envelope** | Every endpoint returns errors in the same shape with the same fields — callers write one error-parsing path, not one per endpoint. |
| **A constraint-violation translator** (`raise_for_constraint`) | A database constraint failure becomes a clean domain error instead of a raw, endpoint-specific `IntegrityError` leaking to the client. |
| **External-error classification** — retryable / permanent / ambiguous | Retries only happen when they're actually safe. An ambiguous outcome (e.g. a payment call that timed out after the charge may have gone through) is never retried blindly. |
| **Structured, correlated logging** — request ID and job ID propagation, JSON formatter | A single request can be traced end-to-end across an HTTP view and the Celery worker it triggered, in log aggregation, not just in a debugger. |
| **Durable jobs** — claim, lease, fencing token, retry, dead-letter | Background work stays correct under Celery's at-least-once delivery: no duplicate side effects from a task that ran twice, and stuck jobs surface instead of vanishing. |
| **Domain events + transactional outbox** | One app reacting to a change in another goes through an explicit, typed event — not a signal quietly carrying business logic, and not a direct cross-app import. |
| **A migration-safety checker** | Destructive migrations (dropping a column, renaming in place) are blocked unless explicitly approved — expand-and-contract is the default, not something you hope everyone remembers. |
| **Architecture-enforcement tests** — module boundaries, model conventions, event registry completeness | Layering rules ("services don't import views", "every model uses a base", "every emitted event has a registered handler") are checked by a test suite, so a violation fails CI instead of passing review by accident. |
| **A docs generator** — data dictionary, error catalog, event catalog, OpenAPI | Reference docs are generated from the code and checked for staleness (`--check`), so they can't silently drift from what's actually deployed. |
| **A single quality gate** (`deploy/run_quality_gates.py`) | Lint, types, migrations, safety checks, tests, coverage, and a dependency audit run as one command, identically for a developer and for CI. |
| **A project-policy mechanism** | Architecture decisions (stack, apps, queues, limits) are recorded once in `docs/engineering/project-policy.md` and read by every future session — decisions get made once, not re-litigated per task. |

## What's inside

| Path | Purpose |
|---|---|
| `SKILL.md` | Entry point. Routes the agent to the right reference for the task. |
| `references/` | One topic per file — models, migrations, APIs, security, events and jobs, Redis, files, observability, testing, operations, and more. Each has its own table of contents. |
| `bootstrap/` | The questionnaire and templates used to set up a new project's policy and instruction files. |
| `profiles/` | Concrete, swappable defaults (stack choices, locale, tooling) a project can opt into. |
| `assets/project/` | Real Django code — model bases, error handling, the domain-events app, durable jobs, migration safety checks, a quality gate — copied into a new repository by the bootstrap and tested together in CI. |
| `agents/` | Per-agent adapters/metadata (e.g. `openai.yaml`) for tools other than Claude Code. |
| `scripts/` | Standalone checks: policy completeness, dependency-version drift. |

## Install

See [INSTALL.md](INSTALL.md) for exact steps per agent (Claude Code, and others).
Quick version for Claude Code:

```bash
git clone https://github.com/amirzt/django-engineering-skill ~/.claude/skills/django-backend-engineering
```

Then, in any repository, just ask the agent to use the
`django-backend-engineering` skill — or let it trigger automatically when the
task involves Django models, APIs, background jobs, or a review.

## Quick start

- **New project**: the skill's `SKILL.md` routes to `bootstrap/README.md`, which
  walks the agent through a short questionnaire and copies in the kit under
  `assets/project/`.
- **Existing project**: the skill reads the repository's own conventions first
  (`AGENTS.md`, `CLAUDE.md`, `docs/engineering/project-policy.md`) and only
  falls back to its own defaults where the project hasn't decided something.
- **Code review**: point the agent at a diff; it checks it against
  `references/workflow.md` §6 and the references for whatever areas the diff
  touches.

## Precedence

The skill never overrides what a project or a user has already decided. In
order: platform/system instructions, the user's explicit request, the
repository's own instruction files (`AGENTS.md`, `CLAUDE.md`, etc.), the
project policy, and only then this skill's own profiles and references.

## Contributing

Contributions are welcome — new references, a new profile, fixes to the
bootstrap kit. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE).
