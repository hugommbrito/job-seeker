import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from apps.tenancy import sql


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("tenancy", "0001_grants"),
        ("applications", "0003_application_user_posting"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TelegramPollState",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("next_offset", models.BigIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="Notification",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("kind", models.CharField(max_length=32)),
                ("dedupe_key", models.CharField(max_length=200)),
                ("title", models.CharField(max_length=200)),
                ("body", models.TextField(blank=True, default="")),
                ("link", models.CharField(blank=True, default="", max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                (
                    "application",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notifications",
                        to="applications.application",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="NotificationChannel",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("kind", models.CharField(choices=[("telegram", "Telegram")], max_length=16)),
                ("config", models.JSONField(blank=True, default=dict)),
                ("link_code_hash", models.CharField(blank=True, default="", max_length=64)),
                ("link_expires_at", models.DateTimeField(blank=True, null=True)),
                ("linked_at", models.DateTimeField(blank=True, null=True)),
                ("enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Delivery",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Waiting"),
                            ("sending", "Being sent"),
                            ("sent", "Sent"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("last_error", models.CharField(blank=True, default="", max_length=100)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "notification",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deliveries",
                        to="notifications.notification",
                    ),
                ),
                (
                    "channel",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deliveries",
                        to="notifications.notificationchannel",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(
                fields=["user", "-created_at"], name="notificatio_user_id_05b4bc_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.UniqueConstraint(
                fields=("user", "dedupe_key"), name="notification_once_per_key"
            ),
        ),
        migrations.AddConstraint(
            model_name="notificationchannel",
            constraint=models.UniqueConstraint(
                fields=("user", "kind"), name="notification_channel_one_per_kind"
            ),
        ),
        migrations.AddConstraint(
            model_name="delivery",
            constraint=models.UniqueConstraint(
                fields=("notification", "channel"), name="delivery_once_per_channel"
            ),
        ),
        # Row-level security, and references that also match the owner (ADR 0006).
        sql.enable_tenant_rls("notifications_notificationchannel"),
        sql.enable_tenant_rls("notifications_notification"),
        sql.enable_tenant_rls("notifications_delivery"),
        sql.tenant_key("notifications_notificationchannel"),
        sql.tenant_key("notifications_notification"),
        sql.same_tenant_foreign_key(
            "notifications_notification", "application_id", "applications_application"
        ),
        sql.same_tenant_foreign_key(
            "notifications_delivery", "notification_id", "notifications_notification"
        ),
        sql.same_tenant_foreign_key(
            "notifications_delivery", "channel_id", "notifications_notificationchannel"
        ),
    ]
