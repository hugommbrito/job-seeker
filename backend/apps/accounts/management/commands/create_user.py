"""Create an account. There is no public sign-up, so this is the only way in."""

from __future__ import annotations

import getpass
import sys
from typing import Any

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.accounts.models import Role, User, normalise_email


class Command(BaseCommand):
    help = "Create a user. The password is prompted for, or read from stdin; never an argument."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("email")
        parser.add_argument("--role", choices=Role.values, default=Role.MEMBER)
        parser.add_argument(
            "--password-stdin",
            action="store_true",
            help="Read the password from the first line of stdin instead of prompting.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        email = normalise_email(options["email"])
        if User.objects.filter(email=email).exists():
            raise CommandError("A user with this email already exists.")

        if options["password_stdin"]:
            password = sys.stdin.readline().rstrip("\n")
        else:
            password = getpass.getpass("Password: ")
            if password != getpass.getpass("Password (again): "):
                raise CommandError("The two passwords do not match.")

        candidate = User(email=email, role=options["role"])
        try:
            validate_password(password, candidate)
            user = User.objects.create_user(email=email, password=password, role=options["role"])
        except ValidationError as error:
            raise CommandError("; ".join(error.messages)) from error

        # The email is not echoed: command output ends up in terminal scrollback and CI logs.
        self.stdout.write(self.style.SUCCESS(f"Created user {user.pk} with role {user.role}."))
