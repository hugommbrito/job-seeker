"""Scheduled notification work: reading the bot's messages and pushing what is waiting."""

from __future__ import annotations

from celery import shared_task

from apps.notifications import reminders, service
from apps.notifications.telegram import get_bot
from apps.operations.runs import recorded
from apps.profiles.clock import user_today
from apps.profiles.models import Profile
from apps.profiles.settings import NotifySettings, read
from apps.tenancy.context import tenant_context


@shared_task(name="notifications.poll_telegram")
def poll_telegram() -> None:
    with recorded("notifications.poll_telegram") as counts:
        bot = get_bot()
        if bot is None:
            counts["not_configured"] = 1
            return
        counts.update(service.poll_telegram(bot))


@shared_task(name="notifications.deliver")
def deliver() -> None:
    with recorded("notifications.deliver") as counts:
        bot = get_bot()
        for user_id in service.recipients():
            for name, value in service.deliver_pending(user_id, bot).items():
                counts[name] = counts.get(name, 0) + value


@shared_task(name="notifications.deliver_user")
def deliver_user(user_id: int) -> None:
    """Push one user's waiting deliveries now, instead of at the next scheduled run."""
    service.deliver_pending(user_id, get_bot())


@shared_task(name="notifications.scan_reminders")
def scan_reminders() -> None:
    """Create every due reminder, then push them, one user at a time."""
    with recorded("notifications.scan_reminders") as counts:
        counts.update({"users": 0, "reminders": 0, "sent": 0})
        bot = get_bot()
        for user_id in service.recipients():
            with tenant_context(user_id):
                profile = Profile.objects.filter(user_id=user_id).first()
                preferences = read(
                    NotifySettings, profile.notify if profile else {}, f"profile of {user_id}"
                )
                counts["reminders"] += reminders.create_due(user_today(), preferences)
            # Outside the tenant context: delivery calls the bot.
            counts["sent"] += service.deliver_pending(user_id, bot)["sent"]
            counts["users"] += 1
