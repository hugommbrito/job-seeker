"""Notifications: the in-app centre, the channels that push to a phone, and each delivery.

A notification is created once per dedupe key and user; the unique constraint, not application
logic, is what makes a reminder fire exactly once. Pushing it to a channel is a separate
delivery row, claimed before the message goes out: a crash between claim and send loses one
push, where the other order would risk sending it again on every retry.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from apps.applications.models import Application
from apps.tenancy.models import CatalogModel, TenantModel


class ChannelKind(models.TextChoices):
    TELEGRAM = "telegram", "Telegram"


class NotificationChannel(TenantModel):
    kind = models.CharField(max_length=16, choices=ChannelKind.choices)
    # Per kind; for Telegram, {"chat_id": <int>} once linked. Validated where it is read.
    config = models.JSONField(default=dict, blank=True)
    # While linking: a hash of the one-time code the user sends to the bot, and its expiry.
    link_code_hash = models.CharField(max_length=64, blank=True, default="")
    link_expires_at = models.DateTimeField(null=True, blank=True)
    linked_at = models.DateTimeField(null=True, blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["user", "kind"], name="notification_channel_one_per_kind"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind} channel {self.pk}"

    @property
    def ready(self) -> bool:
        return self.enabled and self.linked_at is not None


class Notification(TenantModel):
    kind = models.CharField(max_length=32)
    dedupe_key = models.CharField(max_length=200)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True, default="")
    # An app path to open, such as /applications/12.
    link = models.CharField(max_length=200, blank=True, default="")
    application = models.ForeignKey(
        Application,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["user", "dedupe_key"], name="notification_once_per_key"
            ),
        ]
        indexes: ClassVar = [models.Index(fields=["user", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.kind} notification {self.pk}"


class DeliveryStatus(models.TextChoices):
    PENDING = "pending", "Waiting"
    SENDING = "sending", "Being sent"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"


class Delivery(TenantModel):
    notification = models.ForeignKey(
        Notification, on_delete=models.CASCADE, related_name="deliveries"
    )
    channel = models.ForeignKey(
        NotificationChannel, on_delete=models.CASCADE, related_name="deliveries"
    )
    status = models.CharField(
        max_length=16, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    # A machine-readable reason, never the message or the chat.
    last_error = models.CharField(max_length=100, blank=True, default="")
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["notification", "channel"], name="delivery_once_per_channel"
            ),
        ]

    def __str__(self) -> str:
        return f"delivery {self.pk} ({self.status})"


class TelegramPollState(CatalogModel):
    """Where the bot's update stream was last read. One row; holds no user data."""

    next_offset = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"telegram offset {self.next_offset}"
