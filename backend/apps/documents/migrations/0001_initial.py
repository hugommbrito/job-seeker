import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from apps.tenancy import sql


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("tenancy", "0001_grants"),
        ("applications", "0002_contact"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Document",
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
                            ("cv", "CV"),
                            ("cover_letter", "Cover letter"),
                            ("email", "Email"),
                            ("other", "Other"),
                        ],
                        default="other",
                        max_length=16,
                    ),
                ),
                ("filename", models.CharField(max_length=200)),
                ("content_type", models.CharField(max_length=100)),
                ("size", models.PositiveIntegerField()),
                ("sha256", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "application",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documents",
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
            name="DocumentBlob",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("content", models.BinaryField()),
                (
                    "document",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="blob",
                        to="documents.document",
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
        migrations.AddConstraint(
            model_name="document",
            constraint=models.CheckConstraint(
                condition=models.Q(("kind__in", ["cv", "cover_letter", "email", "other"])),
                name="documents_kind_valid",
            ),
        ),
        # Row-level security, and references that also match the owner (ADR 0006).
        sql.enable_tenant_rls("documents_document"),
        sql.enable_tenant_rls("documents_documentblob"),
        sql.tenant_key("documents_document"),
        sql.same_tenant_foreign_key(
            "documents_document", "application_id", "applications_application"
        ),
        sql.same_tenant_foreign_key("documents_documentblob", "document_id", "documents_document"),
    ]
