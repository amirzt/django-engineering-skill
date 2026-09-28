"""Migration operations shared across apps.

`PostgresOnlySQL` lets one migration history serve both the hermetic SQLite test
tier and PostgreSQL: statements that only PostgreSQL understands are skipped on
other backends instead of forking the history.
"""

from __future__ import annotations

from typing import Any

from django.db import migrations


class PostgresOnlySQL(migrations.RunSQL):
    def database_forwards(
        self, app_label: str, schema_editor: Any, from_state: Any, to_state: Any
    ) -> None:
        if schema_editor.connection.vendor == "postgresql":
            super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(
        self, app_label: str, schema_editor: Any, from_state: Any, to_state: Any
    ) -> None:
        if schema_editor.connection.vendor == "postgresql":
            super().database_backwards(app_label, schema_editor, from_state, to_state)
