"""Base classes that say which of the three table classes a model belongs to.

Every table is one of:

* tenant     per-user data, protected by row-level security (inherit ``TenantModel``);
* catalog    shared data with no user column, such as postings (inherit ``CatalogModel``);
* framework  Django's own and the authentication tables, listed in ``classification``.

A model that inherits neither base and is not listed as framework fails the catalog meta-test.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import models

from apps.tenancy.context import current_user_id


class TenantModel(models.Model):
    """A row that belongs to exactly one user.

    The table's first migration must also call ``apps.tenancy.sql.enable_tenant_rls``; the
    meta-test fails until it does.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="+",
    )

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Convenience only. Ownership is enforced by the policy's WITH CHECK clause, which
        # rejects a row whose user differs from the active context whatever this code does.
        if self.user_id is None:
            self.user_id = current_user_id()
        super().save(*args, **kwargs)


class CatalogModel(models.Model):
    """A row shared by all users. It must not carry a user column."""

    class Meta:
        abstract = True
