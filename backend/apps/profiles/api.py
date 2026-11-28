"""The signed-in user's profile and tracks: what the first-run wizard and the settings page edit."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from functools import cache
from typing import Annotated
from zoneinfo import available_timezones

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Field, Router, Schema, Status
from pydantic import AfterValidator, StringConstraints

from apps.accounts.demo import demo_denied, demo_readable
from apps.profiles.models import DEFAULT_TIMEZONE, Profile, Track
from apps.profiles.settings import HardFilters, NotifySettings, Title, TrackFilters, read
from apps.tenancy.context import current_user_id

router = Router(tags=["profile"])
tracks_router = Router(tags=["profile"])


@cache
def _zones() -> frozenset[str]:
    return frozenset(available_timezones())


def _zone(value: str) -> str:
    if value not in _zones():
        raise ValueError("is not a known timezone")
    return value


Zone = Annotated[str, AfterValidator(_zone)]


class Home(Schema):
    label: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] = ""
    latitude: Annotated[Decimal, Field(ge=-90, le=90, max_digits=9, decimal_places=6)]
    longitude: Annotated[Decimal, Field(ge=-180, le=180, max_digits=9, decimal_places=6)]


class ProfileOut(Schema):
    timezone: str
    hard: HardFilters
    notify: NotifySettings
    home: Home | None
    onboarded: bool


class ProfilePatch(Schema):
    timezone: Zone | None = None
    hard: HardFilters | None = None
    notify: NotifySettings | None = None
    # null clears it.
    home: Home | None = None
    onboarded: bool | None = None


def _out(profile: Profile | None) -> ProfileOut:
    if profile is None:
        # No row yet: the wizard has not run. Reading never creates one.
        return ProfileOut(
            timezone=DEFAULT_TIMEZONE,
            hard=HardFilters(),
            notify=NotifySettings(),
            home=None,
            onboarded=False,
        )
    where = f"profile {profile.pk}"
    home = None
    if profile.home_latitude is not None and profile.home_longitude is not None:
        home = Home(
            label=profile.home_label,
            latitude=profile.home_latitude,
            longitude=profile.home_longitude,
        )
    return ProfileOut(
        timezone=profile.timezone,
        hard=read(HardFilters, profile.hard, where),
        notify=read(NotifySettings, profile.notify, where),
        home=home,
        onboarded=profile.onboarded_at is not None,
    )


def _own_profile() -> Profile | None:
    # The filter is the normal way to ask for one's own row. Row-level security is what makes
    # forgetting it harmless.
    return Profile.objects.filter(user_id=current_user_id()).first()


@router.get("", response=ProfileOut)
@demo_readable
def get_profile(request: HttpRequest) -> ProfileOut:
    return _out(_own_profile())


@router.patch("", response=ProfileOut)
@demo_denied
def update_profile(request: HttpRequest, payload: ProfilePatch) -> ProfileOut:
    profile = _own_profile() or Profile(user_id=current_user_id())
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("timezone"):
        profile.timezone = changes["timezone"]
    if payload.hard is not None:
        profile.hard = payload.hard.model_dump(mode="json")
    if payload.notify is not None:
        profile.notify = payload.notify.model_dump(mode="json")
    if "home" in changes:
        home = payload.home
        profile.home_label = home.label if home else ""
        profile.home_latitude = home.latitude if home else None
        profile.home_longitude = home.longitude if home else None
    if payload.onboarded is not None:
        profile.onboarded_at = (
            (profile.onboarded_at or timezone.now()) if payload.onboarded else None
        )
    profile.save()
    return _out(profile)


class TrackIn(Schema):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    target_titles: Annotated[list[Title], Field(max_length=20)] = Field(default_factory=list)
    summary: Annotated[str, StringConstraints(max_length=5000)] = ""
    filter_overrides: TrackFilters = Field(default_factory=TrackFilters)
    active: bool = True


class TrackPatch(Schema):
    name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
        | None
    ) = None
    target_titles: Annotated[list[Title], Field(max_length=20)] | None = None
    summary: Annotated[str, StringConstraints(max_length=5000)] | None = None
    filter_overrides: TrackFilters | None = None
    active: bool | None = None


class TrackOut(Schema):
    id: int
    name: str
    target_titles: list[str]
    summary: str
    filter_overrides: TrackFilters
    active: bool
    created_at: datetime

    @staticmethod
    def resolve_filter_overrides(obj: Track) -> TrackFilters:
        return read(TrackFilters, obj.filter_overrides, f"track {obj.pk}")


@tracks_router.get("", response=list[TrackOut])
@demo_readable
def list_tracks(request: HttpRequest) -> list[Track]:
    return list(Track.objects.order_by("created_at", "id"))


@tracks_router.post("", response={201: TrackOut})
@demo_denied
def create_track(request: HttpRequest, payload: TrackIn) -> Status[Track]:
    track = Track.objects.create(
        name=payload.name,
        target_titles=payload.target_titles,
        summary=payload.summary,
        filter_overrides=payload.filter_overrides.model_dump(mode="json", exclude_none=True),
        active=payload.active,
    )
    return Status(201, track)


@tracks_router.patch("/{int:track_id}", response=TrackOut)
@demo_denied
def update_track(request: HttpRequest, track_id: int, payload: TrackPatch) -> Track:
    track = get_object_or_404(Track, pk=track_id)
    changes = payload.model_dump(exclude_unset=True)
    for name in ("name", "target_titles", "summary", "active"):
        if changes.get(name) is not None:
            setattr(track, name, changes[name])
    if payload.filter_overrides is not None:
        track.filter_overrides = payload.filter_overrides.model_dump(mode="json", exclude_none=True)
    track.save()
    return track


@tracks_router.delete("/{int:track_id}", response={204: None})
@demo_denied
def delete_track(request: HttpRequest, track_id: int) -> Status[None]:
    get_object_or_404(Track, pk=track_id).delete()
    return Status(204, None)
