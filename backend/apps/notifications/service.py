"""Creating notifications, linking a Telegram chat, and pushing pending deliveries.

Every function documents whether it runs inside the user's tenant context. Network calls (the
bot) always happen outside one, because a tenant context is an open transaction.
"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.applications.models import Application
from apps.notifications.models import (
    ChannelKind,
    Delivery,
    DeliveryStatus,
    Notification,
    NotificationChannel,
    TelegramPollState,
)
from apps.notifications.quiet import in_quiet_hours
from apps.notifications.telegram import Bot, SendResult, Update
from apps.profiles.clock import user_zone
from apps.profiles.models import Profile
from apps.profiles.settings import NotifySettings, read
from apps.tenancy.context import current_user_id, tenant_context

logger = logging.getLogger(__name__)

LINK_TTL = timedelta(minutes=15)
# A delivery that failed this many times stops being retried; the notification stays in the app.
MAX_ATTEMPTS = 3
# Per user and run, so one user's backlog cannot hold up everyone else's.
DELIVERIES_PER_RUN = 20

# The only message the bot acts on: "/start <user id>_<one-time code>". Anything else sent to it
# is ignored; its text is never stored or logged.
_START = re.compile(r"^/start (\d{1,18})_([A-Za-z0-9_-]{16,43})$")


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def notify(
    *,
    kind: str,
    dedupe_key: str,
    title: str,
    body: str = "",
    link: str = "",
    application: Application | None = None,
) -> Notification | None:
    """In a tenant context. Create the notification once per key; None if it already exists.

    The unique constraint on (user, dedupe_key) is what guarantees "exactly once", including
    when two runs of a task race.
    """
    try:
        with transaction.atomic():
            notification = Notification.objects.create(
                kind=kind,
                dedupe_key=dedupe_key,
                title=title[:200],
                body=body,
                link=link,
                application=application,
            )
    except IntegrityError:
        return None
    for channel in NotificationChannel.objects.filter(enabled=True, linked_at__isnull=False):
        Delivery.objects.create(notification=notification, channel=channel)
    return notification


@dataclass(frozen=True)
class LinkStart:
    url: str
    expires_at: datetime


def start_telegram_link(bot_username: str) -> LinkStart:
    """In a tenant context. A one-time deep link that ties the chat that opens it to this user."""
    code = secrets.token_urlsafe(16)
    expires_at = timezone.now() + LINK_TTL
    channel, _ = NotificationChannel.objects.get_or_create(kind=ChannelKind.TELEGRAM)
    channel.link_code_hash = _hash(code)
    channel.link_expires_at = expires_at
    channel.save(update_fields=["link_code_hash", "link_expires_at"])
    payload = f"{current_user_id()}_{code}"
    return LinkStart(url=f"https://t.me/{bot_username}?start={payload}", expires_at=expires_at)


def accept_link(update: Update) -> int | None:
    """Outside any tenant context. Link the chat if the update carries a valid code.

    Returns the chat id when a link was made. The user id in the payload only says where to
    look; the one-time code, stored as a hash in that user's own row, is what proves it.
    """
    match = _START.match(update.text.strip())
    if match is None or update.chat_id is None:
        return None
    user_id, code = int(match[1]), match[2]
    if not User.objects.filter(pk=user_id).exclude(role=Role.DEMO).exists():
        return None
    with tenant_context(user_id):
        channel = NotificationChannel.objects.filter(
            kind=ChannelKind.TELEGRAM,
            link_code_hash=_hash(code),
            link_expires_at__gt=timezone.now(),
        ).first()
        if channel is None:
            return None
        channel.config = {"chat_id": update.chat_id}
        channel.linked_at = timezone.now()
        channel.enabled = True
        channel.link_code_hash = ""
        channel.link_expires_at = None
        channel.save()
    return update.chat_id


LINKED = "Linked. Reminders from job-seeker will arrive in this chat."
NOT_LINKED = "That link has expired or is not valid. Open job-seeker's settings for a new one."


def poll_telegram(bot: Bot) -> dict[str, int]:
    """Outside any tenant context. Read what was sent to the bot and act on link requests."""
    state, _ = TelegramPollState.objects.get_or_create(pk=1)
    updates = bot.updates(state.next_offset)
    linked = 0
    for update in updates:
        chat_id = accept_link(update)
        if chat_id is not None:
            bot.send(chat_id, LINKED)
            linked += 1
        elif update.chat_id is not None and update.text.startswith("/start"):
            bot.send(update.chat_id, NOT_LINKED)
    if updates:
        state.next_offset = max(update.update_id for update in updates) + 1
        state.save(update_fields=["next_offset", "updated_at"])
    return {"updates": len(updates), "linked": linked}


def message_text(notification: Notification) -> str:
    parts = [notification.title, notification.body]
    if notification.link and settings.APP_BASE_URL:
        parts.append(settings.APP_BASE_URL.rstrip("/") + notification.link)
    return "\n\n".join(part for part in parts if part)


def _chat_id(channel: NotificationChannel) -> int | None:
    value = channel.config.get("chat_id") if isinstance(channel.config, dict) else None
    return value if isinstance(value, int) else None


def deliver_pending(user_id: int, bot: Bot | None, now: datetime | None = None) -> dict[str, int]:
    """Outside any tenant context. Push this user's waiting deliveries, unless it is quiet time."""
    now = now or timezone.now()
    counts = {"sent": 0, "failed": 0, "waiting": 0}
    with tenant_context(user_id):
        profile = Profile.objects.filter(user_id=user_id).first()
        preferences = read(
            NotifySettings, profile.notify if profile else {}, f"profile of {user_id}"
        )
        waiting = Delivery.objects.filter(status=DeliveryStatus.PENDING, channel__enabled=True)
        if bot is None or in_quiet_hours(preferences.quiet_hours, user_zone(), now):
            counts["waiting"] = waiting.count()
            return counts
        # Claimed before sending: a crash after this point loses a push instead of repeating it.
        claimed = list(
            waiting.select_for_update(skip_locked=True)
            .select_related("notification", "channel")
            .order_by("created_at")[:DELIVERIES_PER_RUN]
        )
        jobs = []
        for delivery in claimed:
            delivery.status = DeliveryStatus.SENDING
            delivery.attempts += 1
            delivery.save(update_fields=["status", "attempts"])
            jobs.append(
                (
                    delivery.pk,
                    delivery.channel_id,
                    _chat_id(delivery.channel),
                    message_text(delivery.notification),
                )
            )

    results = [
        (
            pk,
            channel_id,
            bot.send(chat_id, text) if chat_id is not None else SendResult(False, "not_linked"),
        )
        for pk, channel_id, chat_id, text in jobs
    ]

    with tenant_context(user_id):
        for pk, channel_id, result in results:
            delivery = Delivery.objects.get(pk=pk)
            delivery.last_error = result.error
            if result.ok:
                delivery.status = DeliveryStatus.SENT
                delivery.sent_at = now
                counts["sent"] += 1
            elif result.error == "blocked":
                # The user left the chat or blocked the bot: stop trying until they link again.
                delivery.status = DeliveryStatus.FAILED
                NotificationChannel.objects.filter(pk=channel_id).update(enabled=False)
                counts["failed"] += 1
            elif delivery.attempts >= MAX_ATTEMPTS:
                delivery.status = DeliveryStatus.FAILED
                counts["failed"] += 1
            else:
                delivery.status = DeliveryStatus.PENDING
                counts["waiting"] += 1
            delivery.save(update_fields=["status", "last_error", "sent_at"])
    if counts["failed"]:
        logger.warning("user %s: %s delivery(ies) failed", user_id, counts["failed"])
    return counts


def recipients() -> list[int]:
    """Users who get notifications: everyone but the guest, whose data is synthetic."""
    return list(User.objects.exclude(role=Role.DEMO).values_list("pk", flat=True))
