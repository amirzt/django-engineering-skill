# Contributing

This skill only stays useful if it stays consistent with itself. Read
`SKILL.md` and at least one reference file before proposing a change, so new
material matches the existing tone and structure.

## Ways to contribute

- **Fix a reference** — a rule that's wrong, outdated, or ambiguous in
  `references/`.
- **Add a reference section** — new material goes inside an existing file's
  table of contents unless it's a genuinely new topic area; prefer extending
  over sprawling.
- **Add or update a profile** — `profiles/` holds concrete defaults (stack,
  locale, tooling). A new profile should be self-contained and optional: the
  skill must keep working for projects that don't select it.
- **Fix or extend the bootstrap kit** — `assets/project/` is real, running
  code. Changes here must keep its own test suite green (see below).
- **Improve the bootstrap flow** — `bootstrap/questionnaire.md`,
  `bootstrap/README.md`, and the `.template` files.

## Ground rules

- **`SKILL.md` stays a router.** It should not grow new rules directly —
  route to a reference instead.
- **Don't break precedence.** The skill must never claim to override a
  project's own `AGENTS.md`, `CLAUDE.md`, or project policy. See `SKILL.md`
  §1.
- **`assets/project/` must keep passing its own tests.** It's copied
  verbatim into real projects; a broken kit breaks every project that
  bootstraps after the change.
- **No invented specifics.** Concrete values (versions, limits, names) belong
  in `profiles/`, not hardcoded into a reference meant to be general.
- **Keep files navigable.** Every reference file should keep its table of
  contents current when sections are added, removed, or renamed.

## Testing a change to the bootstrap kit

```bash
cd assets/project
python deploy/run_quality_gates.py
```

This runs the same gate a bootstrapped project runs: linting, strict typing,
and both test tiers (SQLite by default; PostgreSQL-only tests are skipped
without a PostgreSQL connection). It needs Django, DRF, and Celery installed
and a settings module, which this skill repository itself doesn't carry
(`assets/project/` is copied *into* an already-scaffolded project). CI here
instead lints and byte-compiles `assets/project/` and `scripts/` on every
pull request — see `.github/workflows/ci.yml` — as a fast check that the kit
is well-formed; run the full quality gate locally against a bootstrapped
project before merging a substantive kit change.

## Submitting a change

1. Open an issue or discussion first for anything that changes an existing
   rule's behavior (not just wording) — these are the equivalent of a
   breaking change for anyone who already adopted the skill.
2. Keep the change scoped to one reference/profile/topic per pull request.
3. Update `CHANGELOG.md` under "Unreleased."
4. If you're changing `assets/project/`, make sure
   `python deploy/run_quality_gates.py` passes locally before opening the PR.

## Reporting a problem that isn't a code change

If the issue is that the skill produced an unsafe or incorrect result on
real Django code, please include: the task you asked for, which reference(s)
the agent cited (if any), and what it produced instead of what you expected.
