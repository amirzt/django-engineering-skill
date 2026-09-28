# Comments and documentation

How code is commented, how docstrings are written, which documents exist, their
templates, and what is generated and checked.

## Contents

1. Language
2. Docstrings: the house style
3. Comments
4. Documents and templates
5. Generated documents
6. Enforcement

---

## 1. Language

All comments, docstrings, commit messages, and documents are in **English**.
User-facing strings go through `gettext`, never into comments.

## 2. Docstrings: the house style

Docstrings are **prose that explains purpose and reasoning**. They are not
parameter boilerplate.

- **First line**: one sentence saying what the module, class, or function does.
- **Body**, when needed:
  - the invariants it protects and the failure it prevents;
  - the design choice and why, and the alternatives rejected when non-obvious;
  - references to ADRs by number (`ADR-012`).

  **Bold** may mark the key statements of a long module docstring.
- **No `Args:`/`Returns:` sections.** Types carry types. A parameter whose meaning is
  not obvious gets a sentence.
- **Say what the signature does not show**: domain errors raised, events emitted,
  tasks dispatched, audit written, locks taken.

Where docstrings are required (the first two rows are enforced):

| Place | Requirement |
|---|---|
| Every module in `common/` and `deploy/`, under `services/`, `models/`, `management/commands/`, and every `models.py`, `tasks.py`, `events.py`, `handlers.py` (not `__init__.py`) | Module docstring |
| Every model class | The model contract (`models.md` §3) |
| Every `DomainEvent` subclass | One line: what fact it records |
| Every public service function that raises domain errors, emits events, dispatches tasks, writes audit, or takes locks | Function docstring |
| Every Protocol and registry | The contract implementations must honour |

Example:

```python
"""Durable, dead-letter-capable cleanup of external resources.

A cleanup that was only dispatched from `on_commit` could be lost with a broker
message or a worker that died mid-attempt, and nothing durable would record that
the cleanup was still owed. Each owed cleanup is therefore a `CleanupJob` row,
claimed with `skip_locked`, leased, and retried with backoff until it succeeds or
is dead-lettered for an operator (`requeue_dead_jobs`).
"""
```

## 3. Comments

**Write a comment for:**
- why, not what;
- an invariant and the constraint that enforces it;
- a trap: SQL `NULL` logic, bulk operations skipping signals, a library quirk;
- units: `# seconds`, `# whole Rials`;
- a security or concurrency decision;
- the query that justifies an index.

**Never write:**
- a restatement of the code;
- commented-out code;
- history ("this used to…"): git and ADRs hold history;
- references to plans, steps, sprints, tickets, or reviewers (ADR numbers are allowed);
- decorative banners, or vague markers like `# hack`.

**Forms:**
- Comments are full sentences, on the line above the code they explain. A trailing
  comment is only for a short unit or reason.
- `#:` above a module-level constant or class attribute documents it.
- `# TODO(<owner>): <what> - <why or condition to remove>`. No other TODO form.
- `# noqa: <CODE> - <reason>` and `# type: ignore[<code>]  # <reason>`. No blanket
  forms: ruff `PGH` enforces the codes, and a test enforces the reasons.

## 4. Documents and templates

| Document | Path | Written by |
|---|---|---|
| Repository instructions | `AGENTS.md` (+ `CLAUDE.md` importing it) | hand (from `bootstrap/`) |
| Project policy | `docs/engineering/project-policy.md` | hand (from `bootstrap/`) |
| README | `README.md` | hand |
| ADRs | `docs/decisions/NNN-<slug>.md` | hand |
| Feature documents | `docs/features/<feature>.md` | hand |
| Celery map | `docs/features/celery.md` | hand (checked) |
| Redis map | `docs/features/redis.md` | hand |
| Runbooks | `docs/runbooks/<procedure>.md` | hand |
| Domain event catalog | `docs/features/domain-events.md` | **generated** |
| Data dictionary | `docs/data-model.md` | **generated** |
| Error catalog | `docs/api/errors.md` | **generated** |
| OpenAPI | `docs/api/openapi.json` | **generated** |

Every hand-written document starts with:

```markdown
# <Title>

Purpose: <what question this document answers>
Owner: <app or role>
Last verified: <YYYY-MM-DD> against commit <short sha>
Related: <links to ADRs, features, runbooks>
```

**Writing rules:**
- Describe **current** behavior in the present tense; history belongs in ADRs and git.
- Lead with what the reader needs to act. Use tables for maps and catalogs.
- Name exact paths, commands, settings, and error codes. Put a unit on every number.
- Examples must run against the current code.
- No secrets, real personal data, or production hostnames.
- Link to a topic's home instead of copying it.
- **A stale document is a bug**, updated in the same change as the code.

**ADR**:

```markdown
# ADR NNN: <Decision as a statement>

Status: Proposed | Accepted | Superseded by ADR MMM
Date: YYYY-MM-DD

## Context
## Decision
## Alternatives considered
- <Alternative>: rejected because <reason>.
## Consequences
```

**Feature document**: sections `What it does`, `Public surface` (endpoints, events,
commands), `Data and states`, `Limits and settings`, `Failure behavior`,
`Operations` (metrics, alerts, runbooks), `Known gaps` (each with a reason and an owner).

**Runbook**: sections `When to use` (alert or symptom), `Impact`, `Diagnose` (exact
commands, and what normal looks like), `Act` (numbered steps, each with how to
verify it worked), `Roll back / escalate`, `Afterwards`.

**Celery map entry**: a table per task with its definition path, trigger, queue,
arguments, delivery semantics, durable result, and failure behavior. The task name
appears in backticks: the documentation test looks for it.

**Redis map row**: `| Prefix | Instance | Owner | TTL | Invalidation | On failure |`.

**Plans** stay in the chat unless the owner asks for a plan file (`workflow.md` §2).

## 5. Generated documents

`deploy/generate_docs.py` writes the data dictionary, the error catalog, the event
catalog, and (when drf-spectacular is installed) OpenAPI. `--check` fails when any
committed copy is stale. Regenerate after changing models, errors, events, or
endpoints, and never edit a generated file by hand.

## 6. Enforcement

`common/tests/test_code_documentation.py` checks:
- required module docstrings;
- `noqa`, `type: ignore`, and `TODO` formats;
- that `.env.example` covers every `env_*("NAME")` read in `config/settings/`;
- that every Celery task appears in the Celery map;
- that every relative link in `docs/` and the root Markdown files resolves.

`test_model_conventions.py` checks model contracts. The quality gate runs
`generate_docs.py --check`.
