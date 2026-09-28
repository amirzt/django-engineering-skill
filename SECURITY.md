# Security

This repository is a Claude Code / agent skill: Markdown instructions plus a
small bootstrap kit of Django code (`assets/project/`) that gets copied into
real projects. Security issues here fall into two categories.

## The bootstrap kit (`assets/project/`)

If a bug in this code would cause a bootstrapped project to be vulnerable —
for example, a broken authorization check, a missing constraint that allows a
race condition, or unsafe handling of secrets — please report it privately
rather than opening a public issue.

## The skill's guidance

If a reference file (`references/`) recommends a pattern that is insecure —
for example, an authorization approach that doesn't actually scope a
queryset, or advice that would cause secrets to be logged — this is also a
security-relevant bug in the skill's guidance, even though no code executes
directly. Please report it the same way.

## Reporting

Open a private security advisory on GitHub
(`Security` tab → `Report a vulnerability`), or, if that's not available,
open an issue titled generically (no exploit details) and note that it's
security-sensitive so a maintainer can follow up privately.

Please include:
- Whether the issue is in `assets/project/` (executable code) or a
  `references/` file (guidance).
- The smallest example that reproduces it.
- The impact you'd expect on a real project that adopted the affected
  guidance or code.

There is no bug bounty; this is a best-effort volunteer project. Reports are
still very welcome.
