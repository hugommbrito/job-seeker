"""Notifications: once per key, delivered to a linked Telegram chat outside quiet hours."""

from __future__ import annotations

import json
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx2
import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.notifications import service, tasks
from apps.notifications.models import Delivery, DeliveryStatus, Notification, NotificationChannel
from apps.notifications.quiet import in_quiet_hours
from apps.notifications.telegram import TelegramBot, Update
from apps.operations.models import TaskRun
from apps.profiles.models import Profile
from apps.profiles.settings import QuietHours
from apps.tenancy.context import tenant_context
from tests.fakes import FakeBot

pytestmark = pytest.mark.django_db

NOON_IN_TORONTO = datetime(2026, 11, 24, 17, 0, tzinfo=UTC)
MIDNIGHT_IN_TORONTO = datetime(2026, 11, 25, 5, 0, tzinfo=UTC)


@pytest.fixture
def member(make_user):
    return make_user()


@pytest.fixture
def client(member, client_for):
    return client_for(member)


@pytest.fixture
def bot(monkeypatch, settings):
    settings.TELEGRAM_BOT_USERNAME = "example_jobs_bot"
    fake = FakeBot()
    monkeypatch.setattr("apps.notifications.tasks.get_bot", lambda: fake)
    return fake


def _link(client, bot, chat_id=555, update_id=1):
    url = client.post("/api/channels/telegram/link").json()["url"]
    payload = url.split("?start=", 1)[1]
    bot.inbox.append(Update(update_id=update_id, chat_id=chat_id, text=f"/start {payload}"))
    tasks.poll_telegram.delay()
    return payload


def test_linking_a_chat(client, member, bot):
    response = client.post("/api/channels/telegram/link")
    assert response.status_code == 200
    assert response.json()["url"].startswith(f"https://t.me/example_jobs_bot?start={member.pk}_")
    assert client.get("/api/channels").json()["telegram"]["linking"] is True

    _link(client, bot)
    telegram = client.get("/api/channels").json()["telegram"]
    assert telegram == {"available": True, "linked": True, "enabled": True, "linking": False}
    assert bot.sent == [(555, service.LINKED)]
    with tenant_context(member.pk):
        channel = NotificationChannel.objects.get()
    assert channel.config == {"chat_id": 555}
    assert channel.link_code_hash == ""


def test_a_link_is_used_once_and_read_once(client, member, bot):
    _link(client, bot)
    tasks.poll_telegram.delay()
    assert len(bot.sent) == 1, "the same update was processed twice"


@pytest.mark.parametrize(
    "text",
    [
        "/start 1_short",
        "hello",
        "/start",
        "/start 999999_" + "a" * 22,
    ],
)
def test_anything_else_sent_to_the_bot_links_nothing(client, member, bot, text):
    client.post("/api/channels/telegram/link")
    bot.inbox.append(Update(update_id=1, chat_id=777, text=text))
    tasks.poll_telegram.delay()
    with tenant_context(member.pk):
        assert NotificationChannel.objects.get().linked_at is None


def test_an_expired_or_borrowed_code_links_nothing(client, member, make_user, client_for, bot):
    payload = client.post("/api/channels/telegram/link").json()["url"].split("?start=")[1]
    with tenant_context(member.pk):
        NotificationChannel.objects.update(link_expires_at=timezone.now() - timedelta(seconds=1))
    bot.inbox.append(Update(update_id=1, chat_id=555, text=f"/start {payload}"))
    tasks.poll_telegram.delay()
    assert bot.sent == [(555, service.NOT_LINKED)]

    # A valid code with somebody else's id in front of it.
    other = make_user()
    code = client.post("/api/channels/telegram/link").json()["url"].split("_", 1)[1]
    bot.inbox.append(Update(update_id=2, chat_id=556, text=f"/start {other.pk}_{code}"))
    tasks.poll_telegram.delay()
    with tenant_context(member.pk):
        assert NotificationChannel.objects.get().linked_at is None


def test_linking_needs_a_bot_on_the_server(client, settings):
    settings.TELEGRAM_BOT_USERNAME = ""
    assert client.post("/api/channels/telegram/link").status_code == 409
    assert client.get("/api/channels").json()["telegram"]["available"] is False


def test_a_notification_is_created_once_per_key(member):
    with tenant_context(member.pk):
        first = service.notify(kind="x", dedupe_key="next_action:1:2026-12-01", title="Due")
        again = service.notify(kind="x", dedupe_key="next_action:1:2026-12-01", title="Due")
        assert first is not None
        assert again is None
        assert Notification.objects.count() == 1


def _notify(member, key="k1"):
    with tenant_context(member.pk):
        return service.notify(
            kind="x", dedupe_key=key, title="Follow up", body="Example Corp", link="/applications/1"
        )


def test_delivery_to_a_linked_chat(client, member, bot, settings):
    settings.APP_BASE_URL = "https://jobs.example.org"
    _link(client, bot)
    bot.sent.clear()
    _notify(member)
    counts = service.deliver_pending(member.pk, bot, NOON_IN_TORONTO)
    assert counts == {"sent": 1, "failed": 0, "waiting": 0}
    assert bot.sent == [
        (555, "Follow up\n\nExample Corp\n\nhttps://jobs.example.org/applications/1")
    ]
    # Sent once: another run finds nothing to send.
    assert service.deliver_pending(member.pk, bot, NOON_IN_TORONTO)["sent"] == 0
    assert len(bot.sent) == 1


def test_quiet_hours_hold_the_push_until_they_end(client, member, bot):
    _link(client, bot)
    bot.sent.clear()
    _notify(member)
    assert service.deliver_pending(member.pk, bot, MIDNIGHT_IN_TORONTO) == {
        "sent": 0,
        "failed": 0,
        "waiting": 1,
    }
    assert bot.sent == []
    # The in-app notification exists meanwhile.
    assert client.get("/api/notifications").json()["unread"] == 1
    assert service.deliver_pending(member.pk, bot, NOON_IN_TORONTO)["sent"] == 1


def test_quiet_hours_follow_the_users_timezone(client, member, bot):
    with tenant_context(member.pk):
        Profile.objects.create(timezone="Asia/Tokyo")
    _link(client, bot)
    bot.sent.clear()
    _notify(member)
    # 17:00 UTC is 02:00 in Tokyo: quiet, although it is noon in Toronto.
    assert service.deliver_pending(member.pk, bot, NOON_IN_TORONTO)["waiting"] == 1


def test_a_failing_send_is_retried_then_given_up(client, member, bot):
    _link(client, bot)
    _notify(member)
    bot.fail_with = "http_500"
    for _ in range(service.MAX_ATTEMPTS):
        service.deliver_pending(member.pk, bot, NOON_IN_TORONTO)
    with tenant_context(member.pk):
        delivery = Delivery.objects.get()
    assert delivery.status == DeliveryStatus.FAILED
    assert delivery.attempts == service.MAX_ATTEMPTS
    assert delivery.last_error == "http_500"


def test_a_blocked_bot_switches_the_channel_off(client, member, bot):
    _link(client, bot)
    _notify(member)
    bot.fail_with = "blocked"
    service.deliver_pending(member.pk, bot, NOON_IN_TORONTO)
    assert client.get("/api/channels").json()["telegram"]["enabled"] is False
    # Later notifications are not queued for a switched-off channel.
    with tenant_context(member.pk):
        service.notify(kind="x", dedupe_key="k2", title="t")
        assert Delivery.objects.count() == 1


def test_without_a_bot_deliveries_wait(client, member, bot):
    _link(client, bot)
    _notify(member)
    assert service.deliver_pending(member.pk, None, NOON_IN_TORONTO)["waiting"] == 1


def test_the_notification_centre(client, member):
    _notify(member, "a")
    _notify(member, "b")
    listed = client.get("/api/notifications").json()
    assert listed["unread"] == 2
    first = listed["items"][1]["id"]
    assert (
        client.post(
            "/api/notifications/read", data={"ids": [first]}, content_type="application/json"
        ).status_code
        == 204
    )
    assert client.get("/api/notifications").json()["unread"] == 1
    client.post("/api/notifications/read", data={}, content_type="application/json")
    assert client.get("/api/notifications").json()["unread"] == 0


def test_a_test_message_goes_out_at_once(client, member, bot, django_capture_on_commit_callbacks):
    assert client.post("/api/channels/telegram/test").status_code == 409
    with tenant_context(member.pk):
        # No quiet hours, so the result does not depend on the time the test runs.
        Profile.objects.create(notify={"quiet_hours": None})
    _link(client, bot)
    bot.sent.clear()
    with django_capture_on_commit_callbacks(execute=True):
        assert client.post("/api/channels/telegram/test").status_code == 201
    assert [chat for chat, _text in bot.sent] == [555]


def test_unlinking(client, member, bot):
    _link(client, bot)
    assert client.delete("/api/channels/telegram").status_code == 204
    assert client.get("/api/channels").json()["telegram"]["linked"] is False


def test_the_guest_is_never_a_recipient(make_user):
    member, guest = make_user(), make_user(role=Role.DEMO)
    assert member.pk in service.recipients()
    assert guest.pk not in service.recipients()


def test_scheduled_runs_are_recorded(bot, monkeypatch):
    tasks.deliver.delay()
    monkeypatch.setattr("apps.notifications.tasks.get_bot", lambda: None)
    tasks.poll_telegram.delay()
    runs = dict(TaskRun.objects.values_list("name", "outcome"))
    assert runs == {"notifications.deliver": "ok", "notifications.poll_telegram": "ok"}


@pytest.mark.parametrize(
    ("start", "end", "local", "quiet"),
    [
        (time(22), time(8), time(23, 30), True),
        (time(22), time(8), time(7, 59), True),
        (time(22), time(8), time(8, 0), False),
        (time(22), time(8), time(12), False),
        (time(13), time(14), time(13, 30), True),
        (time(13), time(14), time(14), False),
        (time(9), time(9), time(9), False),
    ],
)
def test_quiet_hours_wrap_midnight(start, end, local, quiet):
    zone = ZoneInfo("America/Toronto")
    now = datetime.combine(datetime(2026, 11, 24).date(), local, tzinfo=zone)
    assert in_quiet_hours(QuietHours(start=start, end=end), zone, now) is quiet
    assert in_quiet_hours(None, zone, now) is False


def test_the_real_client_never_puts_the_token_in_a_result():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path.endswith("/sendMessage"):
            body = json.loads(request.content)
            if body["chat_id"] == 403:
                return httpx2.Response(
                    403, json={"ok": False, "description": "Forbidden: bot was blocked"}
                )
            return httpx2.Response(200, json={"ok": True, "result": {"message_id": 1}})
        return httpx2.Response(
            200,
            json={
                "ok": True,
                "result": [{"update_id": 9, "message": {"chat": {"id": 42}, "text": "/start x"}}],
            },
        )

    bot = TelegramBot("123:SECRET", http=httpx2.Client(transport=httpx2.MockTransport(handler)))
    assert bot.send(1, "hello").ok
    blocked = bot.send(403, "hello")
    assert (blocked.ok, blocked.error) == (False, "blocked")
    assert bot.updates(0) == [Update(update_id=9, chat_id=42, text="/start x")]
    assert json.loads(seen[0].content) == {
        "chat_id": 1,
        "text": "hello",
        "disable_web_page_preview": True,
    }

    def down(request):
        raise httpx2.ConnectError(
            "connection refused for https://api.telegram.org/bot123:SECRET/sendMessage"
        )

    failed = TelegramBot(
        "123:SECRET", http=httpx2.Client(transport=httpx2.MockTransport(down))
    ).send(1, "x")
    assert failed.error == "ConnectError"
    assert "SECRET" not in failed.error
