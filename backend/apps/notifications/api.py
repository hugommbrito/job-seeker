"""The in-app notification centre, and the channels that push notifications to a phone."""

from __future__ import annotations

from datetime import datetime

from django.conf import settings
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone
from ninja import Field, Router, Schema, Status
from ninja.errors import HttpError

from apps.accounts.demo import demo_denied, demo_readable
from apps.notifications import service
from apps.notifications.models import ChannelKind, Notification, NotificationChannel
from apps.notifications.tasks import deliver_user
from apps.tenancy.context import current_user_id

router = Router(tags=["notifications"])
channels_router = Router(tags=["notifications"])


class NotificationOut(Schema):
    id: int
    kind: str
    title: str
    body: str
    link: str
    created_at: datetime
    read: bool

    @staticmethod
    def resolve_read(obj: Notification) -> bool:
        return obj.read_at is not None


class NotificationsOut(Schema):
    unread: int
    items: list[NotificationOut]


class ReadIn(Schema):
    # None marks every notification as read.
    ids: list[int] | None = Field(default=None, max_length=500)


@router.get("", response=NotificationsOut)
@demo_readable
def list_notifications(request: HttpRequest) -> dict[str, object]:
    rows = Notification.objects.order_by("-created_at", "-id")
    return {"unread": rows.filter(read_at__isnull=True).count(), "items": list(rows[:50])}


@router.post("/read", response={204: None})
@demo_denied
def mark_read(request: HttpRequest, payload: ReadIn) -> Status[None]:
    rows = Notification.objects.filter(read_at__isnull=True)
    if payload.ids is not None:
        rows = rows.filter(pk__in=payload.ids)
    rows.update(read_at=timezone.now())
    return Status(204, None)


class TelegramOut(Schema):
    # Whether this server has a bot at all.
    available: bool
    linked: bool
    enabled: bool
    # A link was started and has not expired.
    linking: bool


class ChannelsOut(Schema):
    telegram: TelegramOut


class LinkOut(Schema):
    url: str
    expires_at: datetime


def _telegram() -> NotificationChannel | None:
    return NotificationChannel.objects.filter(kind=ChannelKind.TELEGRAM).first()


@channels_router.get("", response=ChannelsOut)
@demo_readable
def list_channels(request: HttpRequest) -> ChannelsOut:
    channel = _telegram()
    linking = bool(
        channel and channel.link_expires_at is not None and channel.link_expires_at > timezone.now()
    )
    return ChannelsOut(
        telegram=TelegramOut(
            available=bool(settings.TELEGRAM_BOT_USERNAME),
            linked=bool(channel and channel.linked_at),
            enabled=bool(channel and channel.enabled),
            linking=linking,
        )
    )


@channels_router.post("/telegram/link", response=LinkOut)
@demo_denied
def link_telegram(request: HttpRequest) -> LinkOut:
    if not settings.TELEGRAM_BOT_USERNAME:
        raise HttpError(409, "Telegram is not set up on this server.")
    start = service.start_telegram_link(settings.TELEGRAM_BOT_USERNAME)
    return LinkOut(url=start.url, expires_at=start.expires_at)


@channels_router.delete("/telegram", response={204: None})
@demo_denied
def unlink_telegram(request: HttpRequest) -> Status[None]:
    NotificationChannel.objects.filter(kind=ChannelKind.TELEGRAM).delete()
    return Status(204, None)


@channels_router.post("/telegram/test", response={201: NotificationOut})
@demo_denied
def test_telegram(request: HttpRequest) -> Status[Notification]:
    channel = _telegram()
    if channel is None or not channel.ready:
        raise HttpError(409, "Link Telegram first.")
    notification = service.notify(
        kind="test",
        dedupe_key=f"test:{timezone.now().isoformat()}",
        title="A test from job-seeker",
        body="If this arrived, reminders will too (outside your quiet hours).",
        link="/settings",
    )
    if notification is None:
        raise HttpError(409, "Try again in a moment.")
    user_id = current_user_id()
    transaction.on_commit(lambda: deliver_user.delay(user_id), robust=True)
    return Status(201, notification)
