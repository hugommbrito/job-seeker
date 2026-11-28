import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from apps.tenancy import sql


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0001_grants"),
        ("profiles", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="hard",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="profile",
            name="home_label",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="profile",
            name="home_latitude",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name="profile",
            name="home_longitude",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name="profile",
            name="notify",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="profile",
            name="onboarded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="Track",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("name", models.CharField(max_length=100)),
                ("target_titles", models.JSONField(blank=True, default=list)),
                ("summary", models.TextField(blank=True, default="")),
                ("filter_overrides", models.JSONField(blank=True, default=dict)),
                ("active", models.BooleanField(default=True)),
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
            options={
                "abstract": False,
            },
        ),
        # Row-level security, and references that also match the owner (ADR 0006).
        sql.enable_tenant_rls("profiles_track"),
    ]
