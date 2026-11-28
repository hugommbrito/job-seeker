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
            name="UserPosting",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[("paste", "Pasted text"), ("url", "From a URL")], max_length=8
                    ),
                ),
                ("url", models.URLField(blank=True, default="", max_length=2000)),
                ("title", models.CharField(blank=True, default="", max_length=300)),
                ("company_name", models.CharField(blank=True, default="", max_length=200)),
                ("location_text", models.CharField(blank=True, default="", max_length=200)),
                (
                    "workplace_type",
                    models.CharField(
                        choices=[
                            ("remote", "Remote"),
                            ("hybrid", "Hybrid"),
                            ("onsite", "On site"),
                            ("unknown", "Unknown"),
                        ],
                        default="unknown",
                        max_length=8,
                    ),
                ),
                (
                    "employment_type",
                    models.CharField(
                        choices=[
                            ("full_time", "Full time"),
                            ("part_time", "Part time"),
                            ("contract", "Contract"),
                            ("temporary", "Temporary"),
                            ("internship", "Internship"),
                            ("unknown", "Unknown"),
                        ],
                        default="unknown",
                        max_length=12,
                    ),
                ),
                ("description_text", models.TextField(blank=True, default="")),
                (
                    "salary_min",
                    models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
                ),
                (
                    "salary_max",
                    models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
                ),
                ("salary_currency", models.CharField(blank=True, default="", max_length=3)),
                (
                    "salary_period",
                    models.CharField(
                        choices=[
                            ("year", "Year"),
                            ("month", "Month"),
                            ("week", "Week"),
                            ("day", "Day"),
                            ("hour", "Hour"),
                            ("unknown", "Unknown"),
                        ],
                        default="unknown",
                        max_length=8,
                    ),
                ),
                (
                    "salary_origin",
                    models.CharField(
                        choices=[
                            ("structured", "Structured field"),
                            ("text", "Posting text"),
                            ("none", "Not stated"),
                        ],
                        default="none",
                        max_length=12,
                    ),
                ),
                ("application_deadline", models.DateField(blank=True, null=True)),
                ("language", models.CharField(blank=True, default="", max_length=8)),
                (
                    "ai_screening",
                    models.CharField(
                        choices=[("yes", "Yes"), ("no", "No"), ("unknown", "Unknown")],
                        default="unknown",
                        max_length=8,
                    ),
                ),
                (
                    "existing_vacancy",
                    models.CharField(
                        choices=[("yes", "Yes"), ("no", "No"), ("unknown", "Unknown")],
                        default="unknown",
                        max_length=8,
                    ),
                ),
                ("raw", models.JSONField(blank=True, default=dict)),
                ("content_hash", models.CharField(blank=True, default="", max_length=64)),
                (
                    "extraction_status",
                    models.CharField(
                        choices=[
                            ("pending", "Being read"),
                            ("extracted", "Read by the model"),
                            ("not_evaluated", "Not evaluated"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("extraction", models.JSONField(blank=True, null=True)),
                ("extraction_error", models.CharField(blank=True, default="", max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("source__in", ["paste", "url"])),
                        name="user_posting_source_valid",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("extraction_status__in", ["pending", "extracted", "not_evaluated"])
                        ),
                        name="user_posting_extraction_status_valid",
                    ),
                ],
            },
        ),
        # Row-level security, and references that also match the owner (ADR 0006).
        sql.enable_tenant_rls("postings_userposting"),
        sql.tenant_key("postings_userposting"),
    ]
