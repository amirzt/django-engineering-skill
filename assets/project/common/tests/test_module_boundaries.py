"""Architecture rules: layer order, thin views, and no catch-all modules."""

from __future__ import annotations

import ast

from django.test import SimpleTestCase

from common.tests.support import FIRST_PARTY, ROOT, parse, python_files
from config import architecture


def _first_party_imports(tree: ast.Module) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found & FIRST_PARTY


class LayerOrderTests(SimpleTestCase):
    def test_every_project_app_declares_its_allowed_imports(self):
        missing = [
            app
            for app in architecture.PROJECT_APPS
            if app not in architecture.ALLOWED_IMPORTS
        ]
        self.assertEqual(missing, [])

    def test_packages_import_only_allowed_layers(self):
        violations = [
            f"{path.relative_to(ROOT)} imports {name}"
            for package, allowed in architecture.ALLOWED_IMPORTS.items()
            for path in python_files(package)
            for name in sorted(_first_party_imports(parse(path)) - {package} - allowed)
        ]
        self.assertEqual(violations, [])

    def test_views_never_open_transactions(self):
        offenders = [
            str(path.relative_to(ROOT))
            for app in architecture.PROJECT_APPS
            for path in python_files(app)
            if (
                "views" in path.parts
                or path.name.endswith("_views.py")
                or path.name == "views.py"
            )
            and "transaction" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(offenders, [])

    def test_no_catch_all_modules(self):
        banned = {"utils.py", "helpers.py", "misc.py"}
        found = [
            str(path.relative_to(ROOT))
            for package in FIRST_PARTY
            for path in python_files(package, include_tests=True)
            if path.name in banned
        ]
        self.assertEqual(found, [])
