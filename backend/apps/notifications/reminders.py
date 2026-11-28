"""Which reminders are due for one user, and creating them.

Runs inside the user's tenant context, with "today" in the user's timezone. Each reminder has a
dedupe key built from what it is about and the date that made it due, so it fires once; a new
due date or new news on the application makes a new key, and a new reminder.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from apps.applications.models import AWAITING_EMPLOYER, DECISION_NOTICE_DAYS, Application
from apps.notifications.service import notify
from apps.profiles.settings import NotifySettings


@dataclass(frozen=True)
class Reminder:
    kind: str
    key: str
    title: str
    body: str
    application: Application


def _label(application: Application) -> str:
    return f"{application.role_title} at {application.company_name}"


def due(today: date, preferences: NotifySettings) -> list[Reminder]:
    reminders: list[Reminder] = []
    open_applications = Application.objects.filter(outcome="")

    if preferences.remind_next_action:
        for application in open_applications.filter(next_action_due__lte=today):
            action = application.next_action or "The next step you planned"
            reminders.append(
                Reminder(
                    kind="next_action_due",
                    key=f"next_action:{application.pk}:{application.next_action_due}",
                    title=f"Due: {action}",
                    body=f"{_label(application)}. Due {application.next_action_due:%B %-d}.",
                    application=application,
                )
            )

    waiting = open_applications.filter(stage__in=AWAITING_EMPLOYER)

    if preferences.remind_decision_due:
        for application in waiting.filter(decision_due_at__lte=today):
            reminders.append(
                Reminder(
                    kind="decision_due",
                    key=f"decision_due:{application.pk}:{application.last_interview_at}",
                    title=f"No decision yet from {application.company_name}?",
                    body=(
                        f"It is {DECISION_NOTICE_DAYS} days since your last interview for "
                        f"{_label(application)} ({application.last_interview_at:%B %-d}). In "
                        "Ontario, an employer with 25 or more employees must tell you by now "
                        "whether a decision has been made. A follow-up is fair."
                    ),
                    application=application,
                )
            )

    if preferences.remind_quiet:
        quiet_since = today - timedelta(days=preferences.follow_up_after_days)
        for application in waiting.filter(last_activity_at__lte=quiet_since):
            days = (today - application.last_activity_at).days
            reminders.append(
                Reminder(
                    kind="quiet_application",
                    key=f"quiet:{application.pk}:{application.last_activity_at}",
                    title=f"No news from {application.company_name} for {days} days",
                    body=f"{_label(application)}. Follow up, or mark it as ghosted.",
                    application=application,
                )
            )
    return reminders


def create_due(today: date, preferences: NotifySettings) -> int:
    """Create the notifications for every due reminder; returns how many were new."""
    created = 0
    for reminder in due(today, preferences):
        notification = notify(
            kind=reminder.kind,
            dedupe_key=reminder.key,
            title=reminder.title,
            body=reminder.body,
            link=f"/applications/{reminder.application.pk}",
            application=reminder.application,
        )
        created += notification is not None
    return created
