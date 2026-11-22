"""Users, sessions and sign-in throttling.

All three are framework tables: they identify who is asking and hold no application data, so
row-level security does not apply to them. That is why the user table is kept to the minimum
(email, password hash, role) and everything else about a person lives in tenant tables.
"""

from __future__ import annotations

from typing import ClassVar

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.sessions.base_session import AbstractBaseSession
from django.db import models


class Role(models.TextChoices):
    OWNER = "owner", "Owner"
    MEMBER = "member", "Member"
    # The public guest account: read-only, and only on routes marked for it.
    DEMO = "demo", "Demo"


def normalise_email(email: str) -> str:
    # The whole address is lower-cased, not only the domain, so one person cannot end up with
    # two accounts that differ by capitalisation.
    return email.strip().lower()


class UserManager(BaseUserManager["User"]):
    def create_user(self, email: str, password: str, role: str = Role.MEMBER) -> User:
        user = self.model(email=normalise_email(email), role=role)
        user.set_password(password)
        user.full_clean()
        user.save(using=self._db)
        return user

    def get_by_natural_key(self, username: str | None) -> User:
        return self.get(email=normalise_email(username or ""))


class User(AbstractBaseUser):
    # Not kept: the table holds what authentication needs and nothing about behaviour.
    last_login = None

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=16, choices=Role.choices)

    objects: ClassVar[UserManager] = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=models.Q(role__in=Role.values), name="accounts_user_role_valid"
            ),
        ]

    def __str__(self) -> str:
        # Not the email: this ends up in logs and tracebacks.
        return f"user {self.pk} ({self.role})"

    @property
    def is_demo(self) -> bool:
        return self.role == Role.DEMO


class Session(AbstractBaseSession):
    """A server-side session, stored under a hash of its key.

    The browser holds the key; the table holds only its SHA-256. Someone who can read the
    database (a backup, a SQL injection) therefore cannot turn a row into a working cookie.
    """

    session_key = models.CharField(max_length=64, primary_key=True, db_column="key_hash")

    class Meta(AbstractBaseSession.Meta):
        db_table = "accounts_session"

    @classmethod
    def get_session_store_class(cls) -> type:
        from apps.accounts.session_backend import SessionStore

        return SessionStore


class LoginThrottle(models.Model):
    """Failed sign-ins counted per key within a time window.

    Kept in the database because several server processes must share the count. The key is an
    HMAC of what it counts (an email, an address, or the pair), so the table stores neither.
    """

    key = models.CharField(max_length=64, primary_key=True)
    failures = models.PositiveIntegerField()
    window_start = models.DateTimeField()

    def __str__(self) -> str:
        return f"{self.failures} failure(s) since {self.window_start:%Y-%m-%d %H:%M}"
