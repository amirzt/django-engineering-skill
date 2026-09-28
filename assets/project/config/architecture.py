"""The project's architecture declarations, read by the enforcement tests and tools.

This module is the single machine-readable statement of the layer order, the
project's apps, and every accepted exception. Keep it in sync with the
"Apps and layer order" section of AGENTS.md; the tests fail when code drifts
from it.
"""

from __future__ import annotations

#: Django apps owned by this project, in layer order (lowest first).
PROJECT_APPS: tuple[str, ...] = (
    "events",
    # "accounts",
    # "access",
    # "files",
    # "notifications",
    # "<feature apps>",
)

#: First-party packages that are not Django apps.
NON_APP_PACKAGES: tuple[str, ...] = ("common", "config", "deploy")

#: package -> first-party packages it may import (besides itself).
ALLOWED_IMPORTS: dict[str, frozenset[str]] = {
    "common": frozenset(),
    "events": frozenset({"common"}),
    # "accounts": frozenset({"common", "events"}),
    # "access": frozenset({"common", "events", "accounts"}),
    # "files": frozenset({"common", "events", "accounts", "access"}),
    # "notifications": frozenset({"common", "events", "accounts", "access"}),
}

#: Models that intentionally use an integer primary key: "app.Model" -> reason.
INTEGER_PK_MODELS: dict[str, str] = {}

#: Append-only evidence models ("app.Model").
EVIDENCE_MODELS: frozenset[str] = frozenset()

#: Integer money fields must end with one of these unit suffixes.
MONEY_INTEGER_SUFFIXES: tuple[str, ...] = ("_irr",)

#: The only approved Django signal receivers: "<module>.<function>" -> reason.
APPROVED_SIGNAL_RECEIVERS: dict[str, str] = {}

#: Celery queues that exist (must match the deployment's workers).
CELERY_QUEUES: frozenset[str] = frozenset({"default", "events"})

#: Where hand-written documentation checks look.
CELERY_TASK_MAP = "docs/features/celery.md"
ENV_EXAMPLE = ".env.example"
SETTINGS_PACKAGE = "config/settings"
