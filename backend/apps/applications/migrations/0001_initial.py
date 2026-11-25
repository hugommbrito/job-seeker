import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from apps.tenancy import sql


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("tenancy", "0001_grants"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Application",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("company_name", models.CharField(max_length=200)),
                ("role_title", models.CharField(max_length=300)),
                (
                    "stage",
                    models.CharField(
                        choices=[
                            ("discovered", "Discovered"),
                            ("saved", "Saved"),
                            ("preparing", "Preparing"),
                            ("applied", "Applied"),
                            ("recruiter", "Recruiter"),
                            ("interviews", "Interviews"),
                            ("offer", "Offer"),
                            ("accepted", "Accepted"),
                        ],
                        default="saved",
                        max_length=16,
                    ),
                ),
                (
                    "outcome",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("rejected", "Rejected"),
                            ("ghosted", "Ghosted"),
                            ("withdrawn", "Withdrawn"),
                        ],
                        default="",
                        max_length=16,
                    ),
                ),
                ("posting_url", models.URLField(blank=True, default="", max_length=2000)),
                ("location", models.CharField(blank=True, default="", max_length=200)),
                ("source", models.CharField(blank=True, default="", max_length=100)),
                ("notes", models.TextField(blank=True, default="")),
                ("applied_at", models.DateField(blank=True, null=True)),
                ("last_interview_at", models.DateField(blank=True, null=True)),
                ("decision_due_at", models.DateField(blank=True, null=True)),
                ("next_action", models.CharField(blank=True, default="", max_length=300)),
                ("next_action_due", models.DateField(blank=True, null=True)),
                ("last_activity_at", models.DateField()),
                ("posting_snapshot", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
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
            name="ApplicationEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("created", "Created"),
                            ("stage_changed", "Stage changed"),
                            ("closed", "Closed"),
                            ("reopened", "Reopened"),
                            ("note", "Note"),
                            ("interview", "Interview"),
                        ],
                        max_length=16,
                    ),
                ),
                ("occurred_on", models.DateField()),
                ("text", models.TextField(blank=True, default="")),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "application",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
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
        migrations.AddIndex(
            model_name="application",
            index=models.Index(fields=["user", "stage"], name="application_user_id_e4f34f_idx"),
        ),
        migrations.AddConstraint(
            model_name="application",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "stage__in",
                        [
                            "discovered",
                            "saved",
                            "preparing",
                            "applied",
                            "recruiter",
                            "interviews",
                            "offer",
                            "accepted",
                        ],
                    )
                ),
                name="applications_stage_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="application",
            constraint=models.CheckConstraint(
                condition=models.Q(("outcome__in", ["rejected", "ghosted", "withdrawn", ""])),
                name="applications_outcome_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="applicationevent",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "kind__in",
                        ["created", "stage_changed", "closed", "reopened", "note", "interview"],
                    )
                ),
                name="applications_event_kind_valid",
            ),
        ),
        # Every tenant table gets row-level security in the migration that creates it, and every
        # reference between tenant tables also matches the owner.
        sql.enable_tenant_rls("applications_application"),
        sql.enable_tenant_rls("applications_applicationevent"),
        sql.tenant_key("applications_application"),
        sql.same_tenant_foreign_key(
            "applications_applicationevent", "application_id", "applications_application"
        ),
    ]
