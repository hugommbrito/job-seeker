"""Database sessions that store a hash of the session key instead of the key.

Set as SESSION_ENGINE. Django's database backend looks sessions up by the cookie value; this one
hashes the value first, in every place the key meets the table. Nothing else changes: the cookie
still carries the raw key, and `cycle_key`, `flush` and expiry behave as usual.

A plain SHA-256 is enough because the key is 32 random characters: there is nothing to guess,
so there is nothing a salt or a slow hash would protect.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from django.contrib.sessions.backends.db import SessionStore as DatabaseSessionStore
from django.core.exceptions import SuspiciousOperation
from django.utils import timezone


def hash_session_key(session_key: str) -> str:
    return hashlib.sha256(session_key.encode()).hexdigest()


class SessionStore(DatabaseSessionStore):
    @classmethod
    def get_model_class(cls) -> Any:
        from apps.accounts.models import Session

        return Session

    def _lookup(self) -> dict[str, Any]:
        assert self.session_key is not None
        return {
            "session_key": hash_session_key(self.session_key),
            "expire_date__gt": timezone.now(),
        }

    def _forget_key(self, error: Exception) -> None:
        if isinstance(error, SuspiciousOperation):
            logger = logging.getLogger(f"django.security.{error.__class__.__name__}")
            logger.warning(str(error))
        self._session_key = None

    def _get_session_from_db(self) -> Any:
        try:
            return self.model.objects.get(**self._lookup())
        except (self.model.DoesNotExist, SuspiciousOperation) as error:
            self._forget_key(error)
            return None

    async def _aget_session_from_db(self) -> Any:
        try:
            return await self.model.objects.aget(**self._lookup())
        except (self.model.DoesNotExist, SuspiciousOperation) as error:
            self._forget_key(error)
            return None

    def exists(self, session_key: str) -> bool:
        return bool(self.model.objects.filter(session_key=hash_session_key(session_key)).exists())

    async def aexists(self, session_key: str) -> bool:
        return bool(
            await self.model.objects.filter(session_key=hash_session_key(session_key)).aexists()
        )

    def create_model_instance(self, data: dict[str, Any]) -> Any:
        return self.model(
            # Private in Django and absent from its type stubs; the method this overrides
            # calls it the same way.
            session_key=hash_session_key(self._get_or_create_session_key()),  # type: ignore[attr-defined]
            session_data=self.encode(data),
            expire_date=self.get_expiry_date(),
        )

    async def acreate_model_instance(self, data: dict[str, Any]) -> Any:
        return self.model(
            session_key=hash_session_key(await self._aget_or_create_session_key()),  # type: ignore[attr-defined]
            session_data=self.encode(data),
            expire_date=await self.aget_expiry_date(),
        )

    def delete(self, session_key: str | None = None) -> None:
        session_key = session_key or self.session_key
        if session_key is None:
            return
        self.model.objects.filter(session_key=hash_session_key(session_key)).delete()

    async def adelete(self, session_key: str | None = None) -> None:
        session_key = session_key or self.session_key
        if session_key is None:
            return
        await self.model.objects.filter(session_key=hash_session_key(session_key)).adelete()
