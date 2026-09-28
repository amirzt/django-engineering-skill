"""Translate known database constraint violations into domain errors.

The database constraint is the source of truth for uniqueness and value rules;
a service that writes a guarded row maps the violation of a *known* constraint
to the domain error clients understand, and re-raises anything else.
`diag.constraint_name` is provided by psycopg 3; SQLite has no equivalent, so
tests of this mapping belong to the PostgreSQL test tier.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import NoReturn

from django.db import IntegrityError

from common.errors import DomainError


def raise_for_constraint(
    error: IntegrityError, mapping: Mapping[str, type[DomainError]]
) -> NoReturn:
    constraint = getattr(
        getattr(error.__cause__, "diag", None), "constraint_name", None
    )
    domain_error = mapping.get(constraint or "")
    if domain_error is None:
        raise error
    raise domain_error() from error
