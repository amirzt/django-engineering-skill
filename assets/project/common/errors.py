"""The errors a service raises on purpose, and the authorization denial.

A `DomainError` subclass names a condition, not an HTTP response: it carries a
stable machine-readable `code` and a category, and the API boundary maps the
category to a status (`common.api_errors`). A class that declares its own `code`
is registered at import time, so two classes can never claim the same code, and
the error catalog is generated from this registry.

`PolicyDenied` lives here rather than in the authorization app so the exception
handler at the bottom layer can render it without importing upward.
"""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar

from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _


class ErrorCategory(StrEnum):
    INVALID_REQUEST = "invalid_request_error"
    AUTHENTICATION = "authentication_error"
    PERMISSION = "permission_error"
    NOT_FOUND = "not_found_error"
    CONFLICT = "conflict_error"
    RATE_LIMIT = "rate_limit_error"
    UNAVAILABLE = "service_unavailable_error"
    SERVER = "server_error"


#: The HTTP status each category is rendered with.
CATEGORY_STATUS: dict[ErrorCategory, int] = {
    ErrorCategory.INVALID_REQUEST: 400,
    ErrorCategory.AUTHENTICATION: 401,
    ErrorCategory.PERMISSION: 403,
    ErrorCategory.NOT_FOUND: 404,
    ErrorCategory.CONFLICT: 409,
    ErrorCategory.RATE_LIMIT: 429,
    ErrorCategory.UNAVAILABLE: 503,
    ErrorCategory.SERVER: 500,
}

#: Every registered error code and the class that owns it.
ERROR_CODES: dict[str, type[DomainError]] = {}


class DomainError(Exception):
    category: ClassVar[ErrorCategory] = ErrorCategory.INVALID_REQUEST
    code: ClassVar[str] = "invalid_request"
    default_message: ClassVar[str | Promise] = _("The request is invalid.")

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        # A subclass that does not declare its own code is a grouping base and
        # shares its parent's code; only declared codes are registered.
        if "code" not in cls.__dict__:
            return
        existing = ERROR_CODES.get(cls.code)
        if existing is not None and existing.__qualname__ != cls.__qualname__:
            raise TypeError(
                f"Error code {cls.code!r} is already used by {existing.__qualname__}."
            )
        ERROR_CODES[cls.code] = cls

    def __init__(
        self, message: str | None = None, *, param: str | None = None, **context: object
    ) -> None:
        self.message = str(message or self.default_message)
        self.param = param
        #: Logged for diagnosis, never returned to the client.
        self.context = context
        super().__init__(self.message)


ERROR_CODES[DomainError.code] = DomainError


class DependencyUnavailable(DomainError):
    """A dependency the request needs (Redis, a provider) cannot decide right now."""

    category = ErrorCategory.UNAVAILABLE
    code = "dependency_unavailable"
    default_message = _("A required service is temporarily unavailable.")


class PolicyDenied(Exception):
    """An authorization decision refused an action.

    A scope denial (`is_not_found=True`) must be indistinguishable from a missing
    object, or list endpoints become an enumeration oracle; it renders as 404.
    A role or credential denial renders as 403.
    """

    def __init__(self, action: str, reason: str, *, is_not_found: bool) -> None:
        super().__init__(f"{action}: {reason}")
        self.action = action
        self.reason = reason
        self.is_not_found = is_not_found
