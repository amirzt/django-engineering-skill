"""Classification of failures from external systems and side-effecting work.

Callers branch on the class, never on message text. A retryable failure is
known not to have taken effect; a permanent one will not succeed on retry; an
ambiguous one may have taken effect and is never retried automatically - it is
reconciled instead.
"""

from __future__ import annotations


class ExternalCallError(Exception):
    error_code = "external_call_failed"

    def __init__(self, error_code: str | None = None, message: str = "") -> None:
        if error_code:
            self.error_code = error_code
        super().__init__(message or self.error_code)


class RetryableError(ExternalCallError):
    error_code = "retryable_failure"


class PermanentError(ExternalCallError):
    error_code = "permanent_failure"


class AmbiguousOutcomeError(ExternalCallError):
    error_code = "ambiguous_outcome"
