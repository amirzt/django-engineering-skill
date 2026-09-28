# Installing the skill

This is a folder of Markdown and Python that an agent reads — there is no
package to build. "Installing" it means making the folder available where
your agent looks for skills.

## Claude Code

Clone (or copy) this repository into your skills directory:

```bash
git clone https://github.com/amirhosseinzt/django-backend-engineering-skill \
  ~/.claude/skills/django-backend-engineering
```

Project-local instead of global (only this repo gets the skill):

```bash
git clone https://github.com/amirhosseinzt/django-backend-engineering-skill \
  .claude/skills/django-backend-engineering
```

Claude Code discovers `SKILL.md` from either location automatically. You can
also invoke it explicitly, e.g. "use the django-backend-engineering skill to
review this."

## Other agents (Cursor, generic OpenAI-based agents, etc.)

`SKILL.md` is plain Markdown with YAML frontmatter (`name`, `description`) and
no Claude-specific syntax, so most agents that support a "read this file for
instructions" or "custom rules" mechanism can point at it directly:

1. Copy or symlink the whole folder into wherever your agent loads
   instructions/rules from.
2. Point the agent's entry rule at `SKILL.md` — it is the router; everything
   else (`references/`, `profiles/`, `bootstrap/`) is loaded on demand from
   there, not all at once.
3. `agents/` holds any agent-specific adapter metadata. `agents/openai.yaml`
   is the current example; add a sibling file for another agent if it needs
   one.

## Verifying it worked

Ask the agent a Django question that should trigger a reference lookup, e.g.
"add a status field with a state machine to this model" — a correctly wired
agent will mention checking `references/models.md` or
`references/data-integrity.md` before proposing an implementation.

## Updating

```bash
cd ~/.claude/skills/django-backend-engineering
git pull
```

Check [CHANGELOG.md](CHANGELOG.md) for anything that affects an existing
project's policy before adopting a new version.
