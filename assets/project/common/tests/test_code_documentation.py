"""Comment and documentation rules: required docstrings, marker formats, doc drift."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from django.test import SimpleTestCase

from common.tests.support import FIRST_PARTY, ROOT, parse, python_files
from config import architecture

NOQA = re.compile(r"#\s*noqa\b(?!: [A-Z]+[0-9]+(?:, ?[A-Z]+[0-9]+)* - \S)")
TYPE_IGNORE = re.compile(r"#\s*type:\s*ignore(?!\[[a-z-]+(?:, ?[a-z-]+)*\]  # \S)")
TODO = re.compile(r"#\s*TODO\b(?!\([\w.-]+\): \S)")
ENV_HELPERS = {"env_str", "env_int", "env_bool", "env_list", "env_decimal", "env_float"}
DOC_LINK = re.compile(r"\]\(([^)\s#]+)(?:#[^)]*)?\)")


def requires_module_docstring(path: Path) -> bool:
    parts = path.relative_to(ROOT).parts
    if path.name == "__init__.py":
        return False
    return (
        parts[0] in {"common", "deploy"}
        or "services" in parts
        or "models" in parts
        or "commands" in parts
        or path.name in {"models.py", "tasks.py", "events.py", "handlers.py"}
    )


class CodeDocumentationTests(SimpleTestCase):
    def test_required_modules_have_docstrings(self):
        missing = [
            str(path.relative_to(ROOT))
            for package in FIRST_PARTY
            for path in python_files(package)
            if requires_module_docstring(path) and not ast.get_docstring(parse(path))
        ]
        self.assertEqual(missing, [])

    def test_suppressions_and_todos_carry_codes_and_reasons(self):
        violations = []
        for package in FIRST_PARTY:
            for path in python_files(package, include_tests=True):
                for number, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), 1
                ):
                    if (
                        NOQA.search(line)
                        or TYPE_IGNORE.search(line)
                        or TODO.search(line)
                    ):
                        violations.append(
                            f"{path.relative_to(ROOT)}:{number}: {line.strip()}"
                        )
        self.assertEqual(violations, [])

    def test_every_setting_read_from_the_environment_is_in_env_example(self):
        settings_dir = ROOT / architecture.SETTINGS_PACKAGE
        example = ROOT / architecture.ENV_EXAMPLE
        if not settings_dir.exists():
            self.skipTest("no settings package")
        documented = {
            line.split("=", 1)[0].strip()
            for line in (
                example.read_text(encoding="utf-8").splitlines()
                if example.exists()
                else []
            )
            if "=" in line and not line.lstrip().startswith("#")
        }
        read: set[str] = set()
        for path in settings_dir.rglob("*.py"):
            for node in ast.walk(parse(path)):
                if (
                    isinstance(node, ast.Call)
                    and getattr(node.func, "id", None) in ENV_HELPERS
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                ):
                    read.add(str(node.args[0].value))
        self.assertEqual(sorted(read - documented), [])

    def test_every_celery_task_is_in_the_task_map(self):
        from celery import current_app

        current_app.loader.import_default_modules()
        names = sorted(n for n in current_app.tasks if not n.startswith("celery."))
        task_map = ROOT / architecture.CELERY_TASK_MAP
        text = task_map.read_text(encoding="utf-8") if task_map.exists() else ""
        self.assertEqual([n for n in names if f"`{n}`" not in text], [])

    def test_relative_links_in_docs_resolve(self):
        broken = []
        for doc in [*(ROOT / "docs").rglob("*.md"), *ROOT.glob("*.md")]:
            for target in DOC_LINK.findall(doc.read_text(encoding="utf-8")):
                if "://" in target or target.startswith("mailto:"):
                    continue
                if not (doc.parent / target).exists():
                    broken.append(f"{doc.relative_to(ROOT)} -> {target}")
        self.assertEqual(broken, [])
