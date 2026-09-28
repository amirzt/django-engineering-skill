#!/usr/bin/env python3
"""Validate a project's engineering policy file produced by the bootstrap.

Fails while the policy is still a template: `status` is not `initialized`, a
required section is missing, a selected profile does not exist in this skill,
or placeholders such as `<project name>`, "pin at bootstrap", or TODO remain.

The profile check needs the skill itself. The script finds it next to itself
(when run from the skill), in `DJANGO_SKILL_ROOT`, or in the usual install
locations. A project copy in `deploy/` running in CI, where no skill is
installed, skips that one check and says so.

Usage: python deploy/validate_project_policy.py [docs/engineering/project-policy.md]
Exit code 0 when the policy is complete, 1 otherwise. Standard library only.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

SKILL_NAME = "django-backend-engineering"
DEFAULT_POLICY = Path("docs/engineering/project-policy.md")
REQUIRED_SECTIONS = (
    "Decisions",
    "Profiles and overrides",
    "Apps and layer order",
    "Authentication",
    "External integrations",
    "Pinned versions",
)
PLACEHOLDER = re.compile(r"<[A-Za-z][^<>\n]*>")
UNRESOLVED = re.compile(r"pin at bootstrap|\bTODO\b|\bTBD\b", re.IGNORECASE)


def skill_root() -> Path | None:
    candidates = [Path(__file__).resolve().parents[1]]
    if os.environ.get("DJANGO_SKILL_ROOT"):
        candidates.insert(0, Path(os.environ["DJANGO_SKILL_ROOT"]))
    for base in (Path(), Path.home()):
        candidates += [
            base / folder / "skills" / SKILL_NAME
            for folder in (".claude", ".agents", ".codex")
        ]
    return next((c for c in candidates if (c / "SKILL.md").is_file()), None)


def front_matter(text: str) -> dict[str, str]:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return {}
    pairs = (line.split(":", 1) for line in match.group(1).splitlines() if ":" in line)
    return {key.strip(): value.strip() for key, value in pairs}


def strip_code(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    return re.sub(r"`[^`\n]*`", "", text)


def validate(path: Path) -> list[str]:
    if not path.exists():
        return [
            f"{path} does not exist; run the bootstrap (see bootstrap/README.md in the skill)."
        ]
    text = path.read_text(encoding="utf-8")
    meta = front_matter(text)
    errors: list[str] = []
    if not meta:
        errors.append("missing front matter (--- status: ... ---)")
    if meta.get("status") != "initialized":
        errors.append(
            f"status is {meta.get('status', 'missing')!r}; it must be 'initialized'"
        )
    root = skill_root()
    profiles = [p.strip() for p in meta.get("profiles", "").split(",") if p.strip()]
    if root is None:
        print(f"note: the {SKILL_NAME} skill was not found; profile names not checked")
        profiles = []
    for profile in profiles:
        if (
            root is not None
            and profile != "none"
            and not (
                (root / "profiles" / f"{profile}.md").exists()
                or (root / "profiles" / profile).is_dir()
            )
        ):
            errors.append(f"profile {profile!r} does not exist in {root / 'profiles'}")
    headings = set(re.findall(r"^## (.+?)\s*$", text, re.MULTILINE))
    errors += [
        f"missing section '## {s}'" for s in REQUIRED_SECTIONS if s not in headings
    ]
    prose = strip_code(text)
    for number, line in enumerate(prose.splitlines(), 1):
        for found in PLACEHOLDER.findall(line):
            errors.append(f"line {number}: unresolved placeholder {found}")
        if UNRESOLVED.search(line):
            errors.append(f"line {number}: unresolved marker: {line.strip()}")
    versions = re.search(
        r"^## Pinned versions\s*$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL
    )
    table = [
        r
        for r in (versions.group(1).splitlines() if versions else [])
        if r.lstrip().startswith("|")
    ]
    # The first two lines are the header and the separator.
    if len(table) < 3:
        errors.append(
            "'## Pinned versions' needs a | Kind | Name | Version | table with at least one row"
        )
    return errors


def main(argv: list[str]) -> int:
    path = Path(argv[0]) if argv else DEFAULT_POLICY
    errors = validate(path)
    for error in errors:
        print(f"policy: {error}")
    print(f"{path}: {'OK' if not errors else f'{len(errors)} problem(s)'}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
