"""Domain event rules: unique names, emitted events, known handlers, approved signals."""

from __future__ import annotations

import ast
import re
import uuid

from django.test import SimpleTestCase

from common.tests.support import module_name, parse, python_files
from config import architecture
from events.domain import DomainEvent, event_classes
from events.exceptions import EventOutsideTransaction
from events.services.emitter import emit
from events.services.registry import HandlerMode, registry

EVENT_NAME = re.compile(r"^[a-z][a-z_]*\.[a-z][a-z_]*$")


def emitted_class_names() -> set[str]:
    """Names of the classes passed to emit(...) anywhere in production code."""
    names: set[str] = set()
    for app in architecture.PROJECT_APPS:
        for path in python_files(app):
            for node in ast.walk(parse(path)):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                func = node.func
                called = getattr(func, "id", None) or getattr(func, "attr", None)
                if called != "emit":
                    continue
                arg = node.args[0]
                target = arg.func if isinstance(arg, ast.Call) else arg
                if isinstance(target, ast.Attribute) and isinstance(
                    target.value, ast.Name | ast.Attribute
                ):
                    target = target.value  # EventClass.from_principal(...)
                name = getattr(target, "id", None) or getattr(target, "attr", None)
                if name:
                    names.add(name)
    return names


def signal_receivers() -> set[str]:
    """Every function connected to a signal in project apps, as module.function."""
    found: set[str] = set()
    for app in architecture.PROJECT_APPS:
        for path in python_files(app):
            module = module_name(path)
            for node in ast.walk(parse(path)):
                if isinstance(node, ast.FunctionDef):
                    for decorator in node.decorator_list:
                        func = getattr(decorator, "func", decorator)
                        if (
                            getattr(func, "id", None) == "receiver"
                            or getattr(func, "attr", None) == "receiver"
                        ):
                            found.add(f"{module}.{node.name}")
                if (
                    isinstance(node, ast.Call)
                    and getattr(node.func, "attr", None) == "connect"
                    and node.args
                    and isinstance(node.args[0], ast.Name)
                ):
                    found.add(f"{module}.{node.args[0].id}")
    return found


class EventRegistryTests(SimpleTestCase):
    def test_event_names_are_unique_and_well_formed(self):
        classes = event_classes()  # raises DuplicateEventName on duplicates
        self.assertEqual([n for n in classes if not EVENT_NAME.match(n)], [])

    def test_every_event_class_is_emitted_somewhere(self):
        emitted = emitted_class_names()
        self.assertEqual(
            sorted(
                c.__name__
                for c in event_classes().values()
                if c.__name__ not in emitted
            ),
            [],
        )

    def test_every_emitted_name_is_a_known_event_class(self):
        known = {c.__name__ for c in event_classes().values()}
        self.assertEqual(sorted(emitted_class_names() - known), [])

    def test_handlers_reference_known_events_and_queues(self):
        names = set(event_classes())
        handlers = [h for h in registry.all() if ".tests." not in f"{h.key}."]
        violations = [h.key for h in handlers if h.event_name not in names]
        violations += [
            f"{h.key} -> {h.queue}"
            for h in handlers
            if h.mode == HandlerMode.ASYNC and h.queue not in architecture.CELERY_QUEUES
        ]
        self.assertEqual(violations, [])

    def test_only_approved_signal_receivers_exist(self):
        self.assertEqual(
            sorted(signal_receivers() - set(architecture.APPROVED_SIGNAL_RECEIVERS)), []
        )

    def test_emit_outside_a_transaction_is_refused(self):
        class ProbeHappened(DomainEvent):
            name = "probe.happened"

        with self.assertRaises(EventOutsideTransaction):
            emit(ProbeHappened(subject_id=uuid.uuid4()))
