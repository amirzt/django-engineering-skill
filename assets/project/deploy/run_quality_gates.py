"""The single quality gate, run identically by developers and CI.

Runs every step in order and stops at the first failure. A missing pinned tool
is a failure, not a skip: running with a different toolchain would make local
and CI results disagree. `--list` prints the steps; naming steps runs only those
(for local iteration - CI always runs all of them).
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
TEST_SETTINGS = os.environ.get("QUALITY_GATE_TEST_SETTINGS", "config.settings.test")

#: (name, python module that must be importable, command)
STEPS: list[tuple[str, str | None, list[str]]] = [
    ("ruff-check", "ruff", [PY, "-m", "ruff", "check", "."]),
    ("ruff-format", "ruff", [PY, "-m", "ruff", "format", "--check", "."]),
    ("mypy", "mypy", [PY, "-m", "mypy", "."]),
    ("django-check", None, [PY, "manage.py", "check", f"--settings={TEST_SETTINGS}"]),
    (
        "migrations",
        None,
        [
            PY,
            "manage.py",
            "makemigrations",
            "--check",
            "--dry-run",
            f"--settings={TEST_SETTINGS}",
        ],
    ),
    ("migration-safety", None, [PY, "deploy/check_migration_safety.py"]),
    ("generated-docs", None, [PY, "deploy/generate_docs.py", "--check"]),
    (
        "tests",
        "coverage",
        [
            PY,
            "-m",
            "coverage",
            "run",
            "manage.py",
            "test",
            f"--settings={TEST_SETTINGS}",
        ],
    ),
    ("coverage", "coverage", [PY, "-m", "coverage", "report"]),
    ("bandit", "bandit", [PY, "-m", "bandit", "-q", "-c", "pyproject.toml", "-r", "."]),
    ("pip-audit", "pip_audit", [PY, "-m", "pip_audit", "-r", "requirements.txt"]),
]


def main(argv: list[str]) -> int:
    if "--list" in argv:
        print("\n".join(name for name, _, _ in STEPS))
        return 0
    selected = [s for s in STEPS if not argv or s[0] in argv]
    env = {**os.environ, "DJANGO_SETTINGS_MODULE": TEST_SETTINGS}
    for name, module, command in selected:
        if module and importlib.util.find_spec(module) is None:
            print(
                f"[{name}] required tool '{module}' is not installed (requirements-dev.txt)"
            )
            return 1
        print(f"[{name}] {' '.join(command[1:])}", flush=True)
        if subprocess.run(command, cwd=ROOT, env=env, check=False).returncode != 0:  # noqa: S603 - fixed argv, no shell
            print(f"[{name}] FAILED")
            return 1
    print("Quality gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
