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

## Why this exists

AI agents are good at writing Django code and bad at staying consistent about
it: one task puts business logic in a view, the next in a signal, the next in a
serializer. Invariants get enforced with `if` statements instead of database
constraints. Every project ends up with a different shape.

This skill is an opinionated answer to that: a router document (`SKILL.md`), a
set of reference documents the agent reads only when the task needs them, a
project-policy mechanism so a repository's decisions are recorded once and
followed forever after, and a bootstrap kit of real, tested code
(`assets/project/`) that a new project can start from instead of an empty
folder.

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
