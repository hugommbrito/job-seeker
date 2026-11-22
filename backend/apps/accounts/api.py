"""Sign-in, sign-out and "who am I".

There is no sign-up route: accounts are created with `manage.py create_user`.
"""

from __future__ import annotations

from django.contrib.auth import authenticate
from django.contrib.auth import login as start_session
from django.contrib.auth import logout as end_session
from django.http import HttpRequest, HttpResponse
from django.middleware.csrf import get_token
from ninja import Router, Schema, Status
from ninja.errors import HttpError
from ninja.utils import check_csrf

from apps.accounts import throttle
from apps.accounts.demo import demo_denied, demo_readable
from apps.accounts.models import Role, User

router = Router(tags=["auth"])


class LoginIn(Schema):
    email: str
    password: str


class UserOut(Schema):
    email: str
    role: Role


class ErrorOut(Schema):
    detail: str


@router.get("/csrf", auth=None, response={204: None})
@demo_readable
def csrf(request: HttpRequest) -> Status[None]:
    """Set the CSRF cookie. The web client calls this once before its first write."""
    get_token(request)
    return Status(204, None)


@router.post(
    "/login",
    auth=None,
    response={200: UserOut, 401: ErrorOut, 403: ErrorOut, 429: ErrorOut},
)
@demo_denied
def login(
    request: HttpRequest, payload: LoginIn, response: HttpResponse
) -> Status[User] | Status[ErrorOut]:
    # Routes with session authentication get the CSRF check from the authenticator. This one
    # has none, and an unprotected login lets a hostile page sign the visitor into an account
    # the attacker controls.
    if check_csrf(request) is not None:
        raise HttpError(403, "CSRF check failed.")

    address = throttle.client_address(request)
    wait = throttle.seconds_until_allowed(payload.email, address)
    if wait:
        response["Retry-After"] = str(wait)
        return Status(429, ErrorOut(detail="Too many failed sign-in attempts. Try again later."))

    user = authenticate(request, username=payload.email, password=payload.password)
    if user is None:
        throttle.record_failure(payload.email, address)
        # One message for an unknown email and a wrong password: the difference would tell a
        # stranger which addresses have accounts.
        return Status(401, ErrorOut(detail="Email or password is incorrect."))

    throttle.record_success(payload.email, address)
    assert isinstance(user, User)
    start_session(request, user)
    return Status(200, user)


@router.post("/logout", response={204: None})
@demo_readable  # the guest must be able to leave
def logout(request: HttpRequest) -> Status[None]:
    end_session(request)
    return Status(204, None)


@router.get("/me", response=UserOut)
@demo_readable
def me(request: HttpRequest) -> User:
    assert isinstance(request.user, User)
    return request.user
