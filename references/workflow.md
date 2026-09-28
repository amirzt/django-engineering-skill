# Workflow

How a task is carried out from request to handoff. Read once per session, before
the first change.

## Contents

1. Task lifecycle
2. Plans
3. Autonomy
4. Stop and ask
5. Verification
6. Self-review (also for code review)
7. Definition of done
8. Handoff
9. Bug fixes
10. Refactors

---

## 1. Task lifecycle

1. **Understand**
   - Restate the goal in one or two sentences.
   - If anything that decides behavior is unclear, ask (§4) before designing.
2. **Inspect**
   - Read the code the change touches, **its tests**, and the relevant docs
     (`docs/features/`, `docs/decisions/`, generated catalogs).
   - Check the real state: `git status`, the local stack, the schema.
   - Never design against an imagined codebase.
3. **Plan**
   - Decide where every piece goes (`file-organization.md`, `architecture.md` §4).
   - State the invariants and failure modes that apply (`data-integrity.md`).
   - Beyond a one-file change, write the plan in the chat (§2).
4. **Implement**
   - Follow the recipe of the touched area; every reference ends with its recipes.
   - Make the smallest coherent change. No drive-by refactors or reformatting, no
     duplicate abstractions.
   - Extend existing registries, services, and pipelines. Never build a parallel path.
   - Preserve work in the tree that is not yours.
5. **Verify** (§5).
6. **Document** in the same change: the documents the change affects, plus the
   regenerated generated documents (`comments-and-docs.md` §5).
7. **Review yourself** (§6).
8. **Hand off** (§8).

## 2. Plans

**Plans live in the chat by default.** Write a plan file only when the owner
explicitly asks for one. Never create plan files on your own.

A plan is needed when the task touches more than one file, or any model,
migration, event, endpoint, task, setting, or security behavior:

```markdown
## Plan: <short title>

**Goal** - what will be true when this is done.
**Current state** - what exists today, verified against the code (paths).
**Scope** / **Out of scope**
**Invariants** - each with the constraint, lock, or guard that enforces it.
**Failure modes** - concurrency, duplicates, crashes between steps, dependency
failures, authorization, invalid input - and how each is handled.
**Design** - where each piece goes: models/migrations, services, events emitted and
handled, endpoints (method, path, errors), tasks/jobs/queues, settings, admin.
**Steps** - ordered, small, each with how it will be verified.
**Tests** - files and the behaviors each proves.
**Docs** - documents to update or regenerate.
**Open questions** - decisions the owner must make.
```

**When the owner asks for a plan file**, write it to `docs/plans/NNN-<slug>.md`
with the same sections, plus:
- a **Progress log**: dated entries with what was done, the commands, and the evidence;
- a **Delivery record**: what shipped, and every deferred item with its reason and owner.

## 3. Autonomy

| The agent may do alone | The agent must ask first | Never, without an explicit owner instruction for that exact action |
|---|---|---|
| Read code, docs, logs, local data | **Commit, push, or open a pull request** | `docker compose down -v`, deleting volumes or media |
| Edit code, tests, and docs within the task | Add, upgrade, or remove a dependency | `flush`, `reset_db`, `migrate <app> zero`, dropping tables |
| Run tests, the quality gate, linters, generators | **Apply migrations** to a database whose data matters (after a backup) | Redis `FLUSHALL`/`FLUSHDB`, purging queues |
| Create migrations and read them | Change a value in the project policy or a profile | Any action against a deployed environment |
| Restart or recreate local containers (volumes kept) | Change the public API contract or security settings | Pointing local tooling at a deployed environment |
| Create local test data through the API, admin, or shell | Call real external services that cost money or reach real people | Force-push or rewrite published history |
| Take a local database backup | Delete files outside the task | Print, copy, or commit secrets |
| | Make an ADR-level decision | Skip, disable, or weaken a test to get green |
| | Anything in §4 | Edit generated documents by hand |

## 4. Stop and ask

Ask the owner when:
- the behavior is ambiguous, or two reasonable designs have materially different
  consequences;
- the change affects the public API contract, data ownership, money, security,
  tenant isolation, or deployment;
- a migration would drop, rewrite, or lose populated data;
- the change would introduce a new project-wide rule, limit, timeout, fallback,
  queue, dependency, or technology;
- the repository contradicts the project policy or this skill;
- a destructive or outward-facing action is needed (§3).

How to ask: one message with **what you found**, **the decision needed**, **the
options** with their consequences, and **your recommendation**. Continue with the
parts that do not depend on the answer, and say which parts are waiting.

## 5. Verification

Unit tests or mocks alone are never enough. In order:

1. **Focused tests** for the change: invalid input, authorization, idempotency and
   retries, emitted events, failure paths (`testing.md` §1).
2. **The quality gate** (`python deploy/run_quality_gates.py`, or the repository's
   own), plus the PostgreSQL tier when locks, constraints, queries, or migrations
   are involved. Run `check --deploy` with production settings when settings,
   security, or runtime changed.
3. **The real flow** on the local stack: call the real HTTP endpoint with a small,
   bounded request. Exercise both success and at least one relevant failure.
4. **Inspect the durable result**, not only the HTTP body: rows and states, the
   outbox and delivery rows, audit events, files, cache entries, and the structured
   logs for the request ID.
5. **The worker path** for anything asynchronous: run the real worker, and confirm
   the claim, lease, retry, and completion or dead-letter lifecycle.
6. **Idempotent replay** for endpoints with `Idempotency-Key`: send the same request
   again, and the same key with a different body.

If a dependency is unavailable, prove it is the dependency and not the code
(health checks, configuration, logs). Record the evidence, run every deterministic
test, and say exactly what could not be verified.

**Never claim a check or flow passed unless it ran and its effects were inspected.**

## 6. Self-review (also for code review)

Before handing off, or when reviewing someone else's change, check the diff:

- [ ] Each file does one job and is named for it (`file-organization.md`).
- [ ] The layer order is respected; cross-layer reactions are domain events (`architecture.md`, `events-and-jobs.md`).
- [ ] Models follow `models.md`: contract docstring, Meta, named constraints and indexes, related names, field types.
- [ ] No I/O inside transactions or locks; no check-then-write races (`data-integrity.md`).
- [ ] Validation is in the right layer; errors are registered domain errors (`api.md` §5–§9).
- [ ] Events are emitted inside the transaction; handlers are thin and idempotent.
- [ ] Authorization goes through the policy; querysets are scoped before lookup (`security.md` §1–§3).
- [ ] No hardcoded values; every new setting is in `.env.example`.
- [ ] No sensitive or secret data in logs, events, or Redis (`security.md` §7).
- [ ] Comments and docstrings follow `comments-and-docs.md`; no history or plan references.
- [ ] Tests assert durable effects; test names describe behavior.
- [ ] Documents are updated and generated documents regenerated.
- [ ] Nothing unrelated is in the diff.

When reviewing, report findings most severe first, each with the file and line,
the rule, and the concrete failure it causes.

## 7. Definition of done

- The change uses the central path for its kind of work.
- Invalid and unauthorized requests fail **before** any side effect.
- Authorization and tenant isolation are proven by tests.
- Retries, duplicate delivery, crashes, cancellation, and ambiguous outcomes are safe.
- Constraints, migrations, query counts, events, and worker behavior were reviewed.
- The quality gate and both test tiers pass, and the real flow was exercised with
  durable effects inspected (§5).
- Documentation reflects what shipped, and every deferred item has a reason and an owner.
- The handoff (§8) states exactly what ran and what did not.

## 8. Handoff

```markdown
## Summary
<What changed and why, in 2-4 sentences.>

## Changes
- `<path>` - <what changed>

## Verification
- Tests: `<command>` -> <result>
- Quality gate: `<command>` -> <result>
- Real flow: <requests> -> <status codes>; durable state inspected: <rows/events/files>
- Worker path: <what ran> -> <result>

## Not verified
- <item> - <why> - <what would verify it>

## Decisions and open questions
- <decision made, or question for the owner>

## Deferred
- <item> - <reason> - <owner>
```

## 9. Bug fixes

1. **Reproduce first**: write a failing test at the lowest layer that shows the bug.
2. **Find the root cause**, not the symptom. Say it in one sentence.
3. **Fix it** in the layer that owns the rule (`api.md` §5).
4. **Look for siblings**: the same mistake elsewhere. Fix them, or list them in the handoff.
5. Name the regression test after the **behavior**, never after a ticket.
6. Verify (§5), and state the root cause in the handoff.

## 10. Refactors

1. Behavior does not change. A behavior change is a separate change.
2. Tests are green before starting and after every step.
3. A moved module keeps a facade until every import is updated. Update every
   dotted-path string (task names, handler keys, settings, test labels) in the same
   step. Renaming a task or a handler key is a contract change
   (`migrations-and-deployment.md` §4).
4. Regenerate the generated documents.
5. Never mix a refactor with a feature or a bug fix.
