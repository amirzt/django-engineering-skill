"""The error envelope and the mapping from exceptions to statuses."""

from __future__ import annotations

from types import SimpleNamespace

from django.db import IntegrityError, OperationalError
from django.http import Http404
from django.test import SimpleTestCase
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions

from common.api_errors import exception_handler
from common.constraint_errors import raise_for_constraint
from common.errors import ERROR_CODES, DomainError, ErrorCategory, PolicyDenied
from common.observability import request_id_var


class ProbeConflict(DomainError):
    category = ErrorCategory.CONFLICT
    code = "probe_conflict"
    default_message = _("The probe is in a conflicting state.")


class ErrorEnvelopeTests(SimpleTestCase):
    def render(self, exc: Exception):
        token = request_id_var.set("req_test")
        try:
            return exception_handler(exc, {})
        finally:
            request_id_var.reset(token)

    def assert_error(self, exc: Exception, status: int, error_type: str, code: str):
        response = self.render(exc)
        self.assertEqual(response.status_code, status)
        error = response.data["error"]
        self.assertEqual(
            (error["type"], error["code"], error["request_id"]),
            (error_type, code, "req_test"),
        )
        self.assertEqual(
            set(error), {"type", "code", "message", "param", "details", "request_id"}
        )
        return response

    def test_domain_errors_render_with_their_category_and_code(self):
        response = self.assert_error(
            ProbeConflict(param="status"), 409, "conflict_error", "probe_conflict"
        )
        self.assertEqual(response.data["error"]["param"], "status")

    def test_domain_error_context_is_never_returned(self):
        response = self.render(ProbeConflict(secret_hint="x"))
        self.assertNotIn("secret_hint", str(response.data))

    def test_scope_denial_is_indistinguishable_from_not_found(self):
        self.assert_error(
            PolicyDenied("order.read", "scope", is_not_found=True),
            404,
            "not_found_error",
            "not_found",
        )
        self.assert_error(Http404(), 404, "not_found_error", "not_found")

    def test_role_denial_is_forbidden(self):
        self.assert_error(
            PolicyDenied("order.cancel", "role", is_not_found=False),
            403,
            "permission_error",
            "permission_denied",
        )

    def test_validation_errors_are_flattened_into_details(self):
        exc = exceptions.ValidationError(
            {"items": [{"quantity": ["Must be positive."]}], "note": ["Too long."]}
        )
        response = self.assert_error(
            exc, 400, "invalid_request_error", "validation_failed"
        )
        params = {d["param"] for d in response.data["error"]["details"]}
        self.assertEqual(params, {"items[0].quantity", "note"})

    def test_framework_errors_keep_their_statuses(self):
        self.assert_error(
            exceptions.ParseError(), 400, "invalid_request_error", "malformed_request"
        )
        self.assert_error(
            exceptions.NotAuthenticated(),
            401,
            "authentication_error",
            "authentication_required",
        )
        self.assert_error(
            exceptions.AuthenticationFailed(),
            401,
            "authentication_error",
            "invalid_token",
        )
        self.assert_error(
            exceptions.PermissionDenied(), 403, "permission_error", "permission_denied"
        )
        self.assert_error(
            exceptions.MethodNotAllowed("POST"),
            405,
            "invalid_request_error",
            "method_not_allowed",
        )
        self.assert_error(
            exceptions.UnsupportedMediaType("text/csv"),
            415,
            "invalid_request_error",
            "unsupported_media_type",
        )
        response = self.assert_error(
            exceptions.Throttled(wait=3.2), 429, "rate_limit_error", "rate_limited"
        )
        self.assertEqual(response.headers["Retry-After"], "4")

    def test_dependency_failures_are_503_and_bugs_are_opaque_500s(self):
        self.assert_error(
            OperationalError(),
            503,
            "service_unavailable_error",
            "dependency_unavailable",
        )
        with self.assertLogs("common.api_errors", "ERROR"):
            response = self.assert_error(
                IntegrityError("duplicate key"), 500, "server_error", "server_error"
            )
        self.assertNotIn("duplicate", str(response.data))
        with self.assertLogs("common.api_errors", "ERROR"):
            self.assert_error(KeyError("secret"), 500, "server_error", "server_error")

    def test_error_codes_are_unique(self):
        self.assertIs(ERROR_CODES["probe_conflict"], ProbeConflict)
        with self.assertRaises(TypeError):
            type("Duplicate", (DomainError,), {"code": "probe_conflict"})


class ConstraintMappingTests(SimpleTestCase):
    def test_known_constraints_map_to_domain_errors_and_others_reraise(self):
        driver_error = Exception("duplicate key")
        driver_error.diag = SimpleNamespace(
            constraint_name="probe_uniq"
        )  # what psycopg 3 provides
        known = IntegrityError("dup")
        known.__cause__ = driver_error
        with self.assertRaises(ProbeConflict):
            raise_for_constraint(known, {"probe_uniq": ProbeConflict})
        unknown = IntegrityError("other")
        with self.assertRaises(IntegrityError):
            raise_for_constraint(unknown, {"probe_uniq": ProbeConflict})
