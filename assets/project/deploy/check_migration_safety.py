"""Reject migrations that are unsafe for a database holding real data.

Expand operations (new tables, nullable or defaulted columns, indexes,
constraints) are safe while an older version still runs. Any other operation -
removing, renaming, or altering columns, and raw SQL or Python - needs a human
decision, recorded in the migration module as `CONTRACT_APPROVED = "<ADR or
reason>"`. Run by path: `python deploy/check_migration_safety.py`.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deploy._django import setup  # noqa: E402 - the path is set just above

EXPAND_OPERATIONS = frozenset(
    {
        "CreateModel",
        "AddIndex",
        "AddIndexConcurrently",
        "AddConstraint",
        "AlterModelOptions",
        "AlterModelManagers",
        "AlterModelTableComment",
    }
)


def _is_safe_add_field(operation: Any) -> bool:
    from django.db.models import NOT_PROVIDED

    field = operation.field
    return (
        field.null
        or field.has_default()
        or getattr(field, "db_default", NOT_PROVIDED) is not NOT_PROVIDED
    )


def _operations(migration: Any) -> Iterator[Any]:
    for operation in migration.operations:
        if type(operation).__name__ == "SeparateDatabaseAndState":
            yield from operation.database_operations
        else:
            yield operation


def main() -> int:
    setup()
    from django.db.migrations.loader import MigrationLoader

    from config import architecture

    loader = MigrationLoader(None, ignore_no_migrations=True)
    violations: list[str] = []
    for (app_label, name), migration in sorted(loader.disk_migrations.items()):
        if app_label not in architecture.PROJECT_APPS:
            continue
        module = sys.modules[type(migration).__module__]
        if getattr(module, "CONTRACT_APPROVED", ""):
            continue
        for operation in _operations(migration):
            kind = type(operation).__name__
            if kind in EXPAND_OPERATIONS or (
                kind == "AddField" and _is_safe_add_field(operation)
            ):
                continue
            violations.append(f"{app_label}.{name}: {kind} needs CONTRACT_APPROVED")
    for line in violations:
        print(line)
    print(
        f"{len(violations)} unsafe operation(s)."
        if violations
        else "Migrations are expand-only or approved."
    )
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
