import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from apps.tenancy import sql


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0001_grants"),
        ("applications", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Contact",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("name", models.CharField(max_length=200)),
                ("role", models.CharField(blank=True, default="", max_length=200)),
                ("email", models.EmailField(blank=True, default="", max_length=254)),
                ("phone", models.CharField(blank=True, default="", max_length=50)),
                ("profile_url", models.URLField(blank=True, default="", max_length=500)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "application",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="contacts",
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
            options={
                "abstract": False,
            },
        ),
        # Row-level security, and references that also match the owner (ADR 0006).
        sql.enable_tenant_rls("applications_contact"),
        sql.same_tenant_foreign_key(
            "applications_contact", "application_id", "applications_application"
        ),
    ]
