#!/usr/bin/env python3
"""Compare the policy's pinned versions with what the repository actually uses.

Reads the `## Pinned versions` table of the project policy
(`| Kind | Name | Version |`, kinds: python, image, action) and checks:

- python: `name==version` in requirements*.txt, and the version in pylock.toml;
- image:  `name:version` in Dockerfile* FROM lines and compose `image:` lines;
- action: `uses: name@version` in .github/workflows/*.yml.

It also reports top-level requirements, images, and actions that the policy
does not list. It never changes anything: a mismatch is reported for a human
to resolve. Exit code 0 when everything agrees, 1 otherwise. Standard library only.

Usage: python <skill>/scripts/check_version_drift.py [--root .] [--policy docs/engineering/project-policy.md]
"""

from __future__ import annotations

import argparse
import re
import tomllib
from pathlib import Path


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def pinned(policy: Path) -> dict[str, dict[str, str]]:
    text = policy.read_text(encoding="utf-8")
    section = re.search(
        r"^## Pinned versions\s*$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL
    )
    table: dict[str, dict[str, str]] = {"python": {}, "image": {}, "action": {}}
    for line in section.group(1).splitlines() if section else []:
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0].lower() in table:
            name = normalize(cells[1]) if cells[0].lower() == "python" else cells[1]
            table[cells[0].lower()][name] = cells[2]
    return table


def requirement_pins(root: Path) -> dict[str, tuple[str, str]]:
    found: dict[str, tuple[str, str]] = {}
    for path in sorted(root.glob("requirements*.txt")):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(
                r"^\s*([A-Za-z0-9_.\-\[\]]+?)(?:\[[^\]]*\])?==([^\s;\\]+)", line
            )
            if match:
                found[normalize(match.group(1))] = (match.group(2), path.name)
    return found


def lock_versions(root: Path) -> dict[str, str]:
    lock = root / "pylock.toml"
    if not lock.exists():
        return {}
    data = tomllib.loads(lock.read_text(encoding="utf-8"))
    return {
        normalize(p["name"]): str(p.get("version", ""))
        for p in data.get("packages", [])
    }


def images(root: Path) -> dict[str, list[tuple[str, str]]]:
    found: dict[str, list[tuple[str, str]]] = {}
    files = [
        *root.glob("Dockerfile*"),
        *root.glob("docker-compose*.y*ml"),
        *root.glob("compose*.y*ml"),
    ]
    for path in files:
        text = path.read_text(encoding="utf-8")
        # Build stages (`FROM x AS stage`) may be reused by later FROM lines.
        stages = {
            s.lower()
            for s in re.findall(r"^\s*FROM\s+\S+\s+AS\s+(\S+)", text, re.I | re.M)
        }
        for line in text.splitlines():
            match = re.match(
                r"^\s*(?:FROM\s+|image:\s*)[\"']?([^\s\"']+)", line, re.IGNORECASE
            )
            if not match or "${" in match.group(1) or match.group(1).lower() in stages:
                continue
            ref = match.group(1)
            name, _, version = (
                ref.partition(":") if "@" not in ref.split(":")[0] else (ref, "", "")
            )
            found.setdefault(name, []).append((version, path.name))
    return found


def actions(root: Path) -> dict[str, list[tuple[str, str]]]:
    found: dict[str, list[tuple[str, str]]] = {}
    for path in sorted((root / ".github" / "workflows").glob("*.y*ml")):
        for match in re.finditer(
            r"uses:\s*([^\s@]+)@([^\s#]+)", path.read_text(encoding="utf-8")
        ):
            found.setdefault(match.group(1), []).append((match.group(2), path.name))
    return found


def check(root: Path, policy: Path) -> list[str]:
    table = pinned(policy)
    problems: list[str] = []
    reqs, lock = requirement_pins(root), lock_versions(root)
    for name, version in table["python"].items():
        if name not in reqs and name not in lock:
            problems.append(
                f"python {name}: pinned {version} but not found in requirements*.txt or pylock.toml"
            )
        if name in reqs and reqs[name][0] != version:
            problems.append(
                f"python {name}: policy {version}, {reqs[name][1]} {reqs[name][0]}"
            )
        if name in lock and lock[name] != version:
            problems.append(
                f"python {name}: policy {version}, pylock.toml {lock[name]}"
            )
    problems += [
        f"python {n}: {f} pins {v} but the policy does not list it"
        for n, (v, f) in reqs.items()
        if n not in table["python"]
    ]
    for kind, used in (("image", images(root)), ("action", actions(root))):
        for name, uses in used.items():
            expected = table[kind].get(name)
            if expected is None:
                problems.append(
                    f"{kind} {name}: used in {uses[0][1]} but the policy does not list it"
                )
                continue
            problems += [
                f"{kind} {name}: policy {expected}, {f} {v}"
                for v, f in uses
                if v != expected
            ]
        problems += [
            f"{kind} {n}: pinned but not used anywhere"
            for n in table[kind]
            if n not in used
        ]
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path())
    parser.add_argument(
        "--policy", type=Path, default=Path("docs/engineering/project-policy.md")
    )
    args = parser.parse_args()
    policy = args.policy if args.policy.is_absolute() else args.root / args.policy
    if not policy.exists():
        print(f"{policy} does not exist")
        return 1
    problems = check(args.root, policy)
    for problem in problems:
        print(f"drift: {problem}")
    print(
        "Versions agree with the policy."
        if not problems
        else f"{len(problems)} drift problem(s)."
    )
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
