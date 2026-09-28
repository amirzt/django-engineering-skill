"""The project DRF exception handler and the single error envelope.

Every error response has the same shape so clients can branch on `type` and
`code` without parsing messages:

    {"error": {"type", "code", "message", "param", "details", "request_id"}}

Services raise `DomainError` subclasses and `PolicyDenied`; this module is the
only place that turns them, and framework exceptions, into HTTP responses.
Unexpected exceptions become a 500 that never reveals internals; the request id
lets an operator find the logged traceback.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterator
from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, InterfaceError, OperationalError
from django.http import Http404
from rest_framework import exceptions
from rest_framework.response import Response

from common.errors import CATEGORY_STATUS, DomainError, ErrorCategory, PolicyDenied
from common.observability import request_id_var

logger = logging.getLogger(__name__)

#: Codes produced by this handler itself, as (code, type, status, message).
#: The error catalog is generated from these plus `common.errors.ERROR_CODES`.
BUILTIN_ERROR_CODES: tuple[tuple[str, str, int, str], ...] = (
    (
        "validation_failed",
        ErrorCategory.INVALID_REQUEST,
        400,
        "One or more fields are invalid.",
    ),
    (
        "malformed_request",
        ErrorCategory.INVALID_REQUEST,
        400,
        "The request body could not be parsed.",
    ),
    (
        "method_not_allowed",
        ErrorCategory.INVALID_REQUEST,
        405,
        "The method is not allowed.",
    ),
    (
        "unsupported_media_type",
        ErrorCategory.INVALID_REQUEST,
        415,
        "The content type is not supported.",
    ),
    (
        "authentication_required",
        ErrorCategory.AUTHENTICATION,
        401,
        "Authentication is required.",
    ),
    (
        "invalid_token",
        ErrorCategory.AUTHENTICATION,
        401,
        "The credentials are invalid or expired.",
    ),
    (
        "permission_denied",
        ErrorCategory.PERMISSION,
        403,
        "You do not have permission to do this.",
    ),
    ("not_found", ErrorCategory.NOT_FOUND, 404, "The resource was not found."),
    ("rate_limited", ErrorCategory.RATE_LIMIT, 429, "Too many requests."),
    (
        "dependency_unavailable",
        ErrorCategory.UNAVAILABLE,
        503,
        "A required service is temporarily unavailable.",
    ),
    ("server_error", ErrorCategory.SERVER, 500, "An unexpected error occurred."),
)
_BUILTIN_MESSAGES = {
    code: message for code, _type, _status, message in BUILTIN_ERROR_CODES
}


def _response(
    status: int,
    error_type: str,
    code: str,
    message: str,
    *,
    param: str | None = None,
    details: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    body = {
        "error": {
            "type": str(error_type),
            "code": code,
            "message": message,
            "param": param,
            "details": details or [],
            "request_id": request_id_var.get(),
        }
    }
    return Response(body, status=status, headers=headers)


def _flatten(detail: Any, prefix: str = "") -> Iterator[dict[str, Any]]:
    """Turn DRF's nested validation detail into a flat list of field errors."""
    if isinstance(detail, dict):
        for key, value in detail.items():
            yield from _flatten(value, f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(detail, list):
        for index, value in enumerate(detail):
            if isinstance(value, (dict, list)):
                yield from _flatten(value, f"{prefix}[{index}]")
            else:
                yield from _flatten(value, prefix)
    else:
        yield {
            "param": prefix or None,
            "code": str(getattr(detail, "code", "invalid")),
            "message": str(detail),
        }


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response:
    if isinstance(exc, DomainError):
        status = CATEGORY_STATUS[exc.category]
        log = logger.error if status >= 500 else logger.info
        log("domain_error", extra={"error_code": exc.code, "context": exc.context})
        return _response(status, exc.category, exc.code, exc.message, param=exc.param)

    if isinstance(exc, PolicyDenied):
        logger.info("policy_denied", extra={"action": exc.action, "reason": exc.reason})
        if exc.is_not_found:
            return _response(
                404,
                ErrorCategory.NOT_FOUND,
                "not_found",
                _BUILTIN_MESSAGES["not_found"],
            )
        return _response(
            403,
            ErrorCategory.PERMISSION,
            "permission_denied",
            _BUILTIN_MESSAGES["permission_denied"],
        )

    if isinstance(exc, (Http404, ObjectDoesNotExist, exceptions.NotFound)):
        return _response(
            404, ErrorCategory.NOT_FOUND, "not_found", _BUILTIN_MESSAGES["not_found"]
        )

    if isinstance(exc, exceptions.ValidationError):
        return _response(
            400,
            ErrorCategory.INVALID_REQUEST,
            "validation_failed",
            _BUILTIN_MESSAGES["validation_failed"],
            details=list(_flatten(exc.detail)),
        )

    if isinstance(exc, exceptions.ParseError):
        return _response(
            400,
            ErrorCategory.INVALID_REQUEST,
            "malformed_request",
            _BUILTIN_MESSAGES["malformed_request"],
        )

    if isinstance(exc, exceptions.NotAuthenticated):
        return _response(
            401,
            ErrorCategory.AUTHENTICATION,
            "authentication_required",
            _BUILTIN_MESSAGES["authentication_required"],
        )

    if isinstance(exc, exceptions.AuthenticationFailed):
        return _response(
            401,
            ErrorCategory.AUTHENTICATION,
            "invalid_token",
            _BUILTIN_MESSAGES["invalid_token"],
        )

    if isinstance(exc, exceptions.PermissionDenied):
        return _response(
            403,
            ErrorCategory.PERMISSION,
            "permission_denied",
            _BUILTIN_MESSAGES["permission_denied"],
        )

    if isinstance(exc, exceptions.Throttled):
        wait = getattr(exc, "wait", None)
        headers = {"Retry-After": str(math.ceil(wait))} if wait else None
        return _response(
            429,
            ErrorCategory.RATE_LIMIT,
            "rate_limited",
            _BUILTIN_MESSAGES["rate_limited"],
            headers=headers,
        )

    if isinstance(exc, exceptions.MethodNotAllowed):
        return _response(
            405,
            ErrorCategory.INVALID_REQUEST,
            "method_not_allowed",
            _BUILTIN_MESSAGES["method_not_allowed"],
        )

    if isinstance(exc, exceptions.UnsupportedMediaType):
        return _response(
            415,
            ErrorCategory.INVALID_REQUEST,
            "unsupported_media_type",
            _BUILTIN_MESSAGES["unsupported_media_type"],
        )

    if isinstance(exc, (OperationalError, InterfaceError)):
        logger.error("database_unavailable", exc_info=exc)
        return _response(
            503,
            ErrorCategory.UNAVAILABLE,
            "dependency_unavailable",
            _BUILTIN_MESSAGES["dependency_unavailable"],
            headers={"Retry-After": "5"},
        )

    if isinstance(exc, IntegrityError):
        # A known constraint must have been mapped to a DomainError by the
        # service (see raise_for_constraint); reaching here is a bug.
        logger.error("unmapped_integrity_error", exc_info=exc)
    else:
        logger.error("unhandled_exception", exc_info=exc)
    return _response(
        500, ErrorCategory.SERVER, "server_error", _BUILTIN_MESSAGES["server_error"]
    )
