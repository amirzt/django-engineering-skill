"""Shared helpers for the enforcement tests. Contains no runnable tests."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

from config import architecture

ROOT = Path(__file__).resolve().parents[2]
FIRST_PARTY = frozenset((*architecture.PROJECT_APPS, *architecture.NON_APP_PACKAGES))


def python_files(package: str, *, include_tests: bool = False) -> Iterator[Path]:
    base = ROOT / package
    if not base.exists():
        return
    for path in sorted(base.rglob("*.py")):
        parts = set(path.relative_to(ROOT).parts)
        if "migrations" in parts or (not include_tests and "tests" in parts):
            continue
        yield path


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def module_name(path: Path) -> str:
    return ".".join(path.relative_to(ROOT).with_suffix("").parts)
