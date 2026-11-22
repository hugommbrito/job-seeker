"""The signed-in user's profile."""

from __future__ import annotations

from django.http import HttpRequest
from ninja import Router, Schema

from apps.accounts.demo import demo_readable
from apps.accounts.models import User
from apps.profiles.models import DEFAULT_TIMEZONE, Profile

router = Router(tags=["profile"])


class ProfileOut(Schema):
    timezone: str


@router.get("", response=ProfileOut)
@demo_readable
def get_profile(request: HttpRequest) -> ProfileOut:
    # The filter is the normal way to ask for one's own row. Row-level security is what makes
    # forgetting it harmless.
    user = request.user
    assert isinstance(user, User)
    profile = Profile.objects.filter(user=user).first()
    # No row yet means the wizard has not run; the defaults are the answer, and reading does
    # not create anything.
    return ProfileOut(timezone=profile.timezone if profile else DEFAULT_TIMEZONE)
