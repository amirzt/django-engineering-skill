"""Model design rules that must hold for every project model."""

from __future__ import annotations

import ast
import re

from django.apps import apps
from django.db import models
from django.test import SimpleTestCase

from common.model_bases import AppendOnlyQuerySet
from common.tests.support import ROOT, parse, python_files
from config import architecture

CONTRACT_HEADINGS = (
    "Owner:",
    "Tenant scope:",
    "Lifecycle:",
    "Invariants:",
    "Data classification:",
    "Append-only:",
    "Events:",
)
MONEY_NAME = re.compile(r"(amount|price|cost|fee|total|balance)")
NAMED_KINDS = {"Index", "UniqueConstraint", "CheckConstraint"}


def project_models() -> list[type[models.Model]]:
    return [
        m for m in apps.get_models() if m._meta.app_label in architecture.PROJECT_APPS
    ]


def own_fields(model: type[models.Model]) -> list[models.Field]:
    return [*model._meta.local_fields, *model._meta.local_many_to_many]


class ModelConventionTests(SimpleTestCase):
    def assert_no_violations(self, violations):
        self.assertEqual(sorted(violations), [])

    def test_every_model_documents_its_contract(self):
        self.assert_no_violations(
            f"{m._meta.label}: missing {[h for h in CONTRACT_HEADINGS if h not in (m.__doc__ or '')]}"
            for m in project_models()
            if any(h not in (m.__doc__ or "") for h in CONTRACT_HEADINGS)
        )

    def test_meta_declares_verbose_names(self):
        self.assert_no_violations(
            m._meta.label
            for m in project_models()
            if not {"verbose_name", "verbose_name_plural"}
            <= set(m._meta.original_attrs)
        )

    def test_every_model_defines_str(self):
        self.assert_no_violations(
            m._meta.label for m in project_models() if m.__str__ is models.Model.__str__
        )

    def test_models_use_uuid_primary_keys_unless_listed(self):
        self.assert_no_violations(
            m._meta.label
            for m in project_models()
            if m._meta.label not in architecture.INTEGER_PK_MODELS
            and not isinstance(m._meta.pk, models.UUIDField)
        )

    def test_every_model_has_created_at(self):
        self.assert_no_violations(
            m._meta.label
            for m in project_models()
            if "created_at" not in {f.name for f in m._meta.fields}
        )

    def test_no_float_fields_and_no_nullable_text(self):
        self.assert_no_violations(
            f"{m._meta.label}.{f.name}"
            for m in project_models()
            for f in own_fields(m)
            if isinstance(f, models.FloatField)
            or (isinstance(f, (models.CharField, models.TextField)) and f.null)
        )

    def test_relations_declare_related_name(self):
        self.assert_no_violations(
            f"{m._meta.label}.{f.name}"
            for m in project_models()
            for f in own_fields(m)
            if f.is_relation
            and f.remote_field.related_name is None
            and not m._meta.default_related_name
        )

    def test_status_fields_use_choices(self):
        self.assert_no_violations(
            f"{m._meta.label}.{f.name}"
            for m in project_models()
            for f in own_fields(m)
            if f.name == "status" and not f.choices
        )

    def test_money_fields_carry_their_unit(self):
        violations = []
        for m in project_models():
            names = {f.name for f in m._meta.fields}
            for f in own_fields(m):
                if not MONEY_NAME.search(f.name):
                    continue
                if isinstance(f, models.IntegerField) and not f.name.endswith(
                    architecture.MONEY_INTEGER_SUFFIXES
                ):
                    violations.append(f"{m._meta.label}.{f.name}")
                if isinstance(f, models.DecimalField) and "currency" not in names:
                    violations.append(f"{m._meta.label}.{f.name}")
        self.assert_no_violations(violations)

    def test_evidence_models_are_append_only(self):
        self.assert_no_violations(
            label
            for label in architecture.EVIDENCE_MODELS
            if not issubclass(
                apps.get_model(label)._default_manager._queryset_class,
                AppendOnlyQuerySet,
            )
        )

    def test_constraints_and_indexes_are_named(self):
        violations = []
        for app in architecture.PROJECT_APPS:
            for path in python_files(app):
                if "models" not in path.parts and path.name != "models.py":
                    continue
                for node in ast.walk(parse(path)):
                    kind = getattr(
                        getattr(node, "func", None), "attr", None
                    ) or getattr(getattr(node, "func", None), "id", None)
                    if (
                        isinstance(node, ast.Call)
                        and kind in NAMED_KINDS
                        and not any(k.arg == "name" for k in node.keywords)
                    ):
                        violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
        self.assert_no_violations(violations)
