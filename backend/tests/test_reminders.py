"""Reminders: due next actions, the 45-day decision clock and quiet applications, each once."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from apps.accounts.models import Role
from apps.applications import services
from apps.applications.models import Application, Stage
from apps.notifications import reminders, tasks
from apps.notifications.models import Delivery, Notification, NotificationChannel
from apps.operations.models import TaskRun
from apps.profiles.clock import user_today
from apps.profiles.models import Profile
from apps.profiles.settings import NotifySettings
from apps.tenancy.context import tenant_context
from tests.fakes import FakeBot

pytestmark = pytest.mark.django_db


@pytest.fixture
def member(make_user):
    return make_user()


@pytest.fixture
def bot(monkeypatch):
    fake = FakeBot()
    monkeypatch.setattr("apps.notifications.tasks.get_bot", lambda: fake)
    return fake


def _application(member, **fields) -> Application:
    with tenant_context(member.pk):
        data = services.NewApplication(company_name="Example Corp", role_title="Analyst")
        for name, value in fields.items():
            setattr(data, name, value)
        return services.create_application(data)


def _today(member) -> date:
    with tenant_context(member.pk):
        return user_today()


def _keys(member) -> list[str]:
    with tenant_context(member.pk):
        return sorted(Notification.objects.values_list("dedupe_key", flat=True))


def test_a_due_next_action_fires_once(member, bot):
    today = _today(member)
    application = _application(member, next_action="Send the portfolio", next_action_due=today)
    tasks.scan_reminders.delay()
    tasks.scan_reminders.delay()
    assert _keys(member) == [f"next_action:{application.pk}:{today}"]
    with tenant_context(member.pk):
        notification = Notification.objects.get()
    assert notification.title == "Due: Send the portfolio"
    assert notification.link == f"/applications/{application.pk}"


def test_a_new_due_date_is_a_new_reminder(member, bot):
    today = _today(member)
    application = _application(member, next_action_due=today - timedelta(days=1))
    tasks.scan_reminders.delay()
    with tenant_context(member.pk):
        Application.objects.filter(pk=application.pk).update(next_action_due=today)
    tasks.scan_reminders.delay()
    assert len(_keys(member)) == 2


def test_nothing_fires_before_its_date_or_on_a_closed_application(member, bot):
    today = _today(member)
    _application(member, next_action_due=today + timedelta(days=1))
    _application(member, next_action_due=today, outcome="rejected")
    tasks.scan_reminders.delay()
    assert _keys(member) == []


def test_the_decision_clock(member, bot):
    today = _today(member)
    interviewed = today - timedelta(days=45)
    due = _application(member, stage=Stage.INTERVIEWS, last_interview_at=interviewed)
    # Not due yet, and an offer has its decision already.
    _application(member, stage=Stage.INTERVIEWS, last_interview_at=today - timedelta(days=44))
    _application(member, stage=Stage.OFFER, last_interview_at=interviewed)
    tasks.scan_reminders.delay()
    assert _keys(member) == [f"decision_due:{due.pk}:{interviewed}"]
    with tenant_context(member.pk):
        body = Notification.objects.get().body
    assert "45 days since your last interview" in body


def test_quiet_applications(member, bot):
    today = _today(member)
    quiet = _application(member, stage=Stage.APPLIED)
    recent = _application(member, stage=Stage.APPLIED)
    saved = _application(member, stage=Stage.SAVED)
    with tenant_context(member.pk):
        Application.objects.filter(pk__in=[quiet.pk, saved.pk]).update(
            last_activity_at=today - timedelta(days=14)
        )
        Application.objects.filter(pk=recent.pk).update(last_activity_at=today - timedelta(days=13))
    tasks.scan_reminders.delay()
    assert _keys(member) == [f"quiet:{quiet.pk}:{today - timedelta(days=14)}"]


def test_each_kind_can_be_switched_off(member):
    today = _today(member)
    _application(
        member,
        stage=Stage.INTERVIEWS,
        next_action_due=today,
        last_interview_at=today - timedelta(days=60),
    )
    off = NotifySettings(remind_next_action=False, remind_decision_due=False, remind_quiet=False)
    with tenant_context(member.pk):
        Application.objects.update(last_activity_at=today - timedelta(days=30))
        assert reminders.due(today, off) == []
        assert {r.kind for r in reminders.due(today, NotifySettings())} == {
            "next_action_due",
            "decision_due",
            "quiet_application",
        }


def test_the_follow_up_delay_is_the_users(member, bot):
    today = _today(member)
    application = _application(member, stage=Stage.APPLIED)
    with tenant_context(member.pk):
        Application.objects.update(last_activity_at=today - timedelta(days=5))
        Profile.objects.create(notify={"follow_up_after_days": 5})
    tasks.scan_reminders.delay()
    assert _keys(member) == [f"quiet:{application.pk}:{today - timedelta(days=5)}"]


def test_reminders_are_pushed_once_to_a_linked_chat(member, bot):
    with tenant_context(member.pk):
        Profile.objects.create(notify={"quiet_hours": None})
        NotificationChannel.objects.create(
            kind="telegram", config={"chat_id": 99}, linked_at="2026-01-01T00:00:00Z"
        )
    _application(member, next_action="Call back", next_action_due=_today(member))
    tasks.scan_reminders.delay()
    tasks.scan_reminders.delay()
    assert [chat for chat, _text in bot.sent] == [99]
    with tenant_context(member.pk):
        assert Delivery.objects.get().status == "sent"
    run = TaskRun.objects.filter(name="notifications.scan_reminders").latest("started_at")
    assert run.outcome == "ok"


def test_the_guest_gets_no_reminders(make_user, bot):
    guest = make_user(role=Role.DEMO)
    _application(guest, next_action_due=date(2020, 1, 1))
    tasks.scan_reminders.delay()
    assert _keys(guest) == []
