"""Abstract model bases every project model starts from.

`PublicModel` is the default: UUID identity and timestamps. `TimestampedModel`
is for internal lookup tables that keep an integer key. `AppendOnlyModel` is for
evidence rows that are never edited or deleted; a mistake is corrected with a
compensating row, never by changing history.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import models


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class PublicModel(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class AppendOnlyQuerySet(models.QuerySet[Any]):
    """Refuses bulk writes, so evidence cannot be rewritten through a queryset."""

    def update(self, **kwargs: Any) -> int:
        raise TypeError(f"{self.model.__name__} rows are append-only.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise TypeError(f"{self.model.__name__} rows are append-only.")


class AppendOnlyModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise TypeError(f"{type(self).__name__} rows are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise TypeError(f"{type(self).__name__} rows are append-only.")
