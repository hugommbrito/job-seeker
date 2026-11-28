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
            name="LlmCall",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("task", models.CharField(max_length=32)),
                ("entity_type", models.CharField(max_length=32)),
                ("entity_id", models.BigIntegerField()),
                ("prompt_version", models.CharField(max_length=32)),
                ("input_hash", models.CharField(max_length=64)),
                ("model", models.CharField(blank=True, default="", max_length=100)),
                (
                    "outcome",
                    models.CharField(
                        choices=[
                            ("ok", "Answered"),
                            ("refused", "Refused by the model"),
                            ("truncated", "Cut off at the token limit"),
                            ("invalid", "Answer did not match the schema"),
                            ("error", "Gateway or network error"),
                            ("duplicate", "Answered twice"),
                            ("unavailable", "No gateway configured"),
                            ("over_budget", "Daily limit reached"),
                            ("denied", "Not available to this account"),
                        ],
                        max_length=16,
                    ),
                ),
                ("response", models.JSONField(blank=True, null=True)),
                ("error", models.CharField(blank=True, default="", max_length=100)),
                ("input_tokens", models.PositiveIntegerField(default=0)),
                ("output_tokens", models.PositiveIntegerField(default=0)),
                ("cache_creation_input_tokens", models.PositiveIntegerField(default=0)),
                ("cache_read_input_tokens", models.PositiveIntegerField(default=0)),
                (
                    "estimated_cost_usd",
                    models.DecimalField(blank=True, decimal_places=6, max_digits=10, null=True),
                ),
                ("latency_ms", models.PositiveIntegerField(blank=True, null=True)),
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
                "indexes": [
                    models.Index(
                        fields=["user", "created_at"], name="llm_llmcall_user_id_2f9820_idx"
                    )
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            (
                                "outcome__in",
                                [
                                    "ok",
                                    "refused",
                                    "truncated",
                                    "invalid",
                                    "error",
                                    "duplicate",
                                    "unavailable",
                                    "over_budget",
                                    "denied",
                                ],
                            )
                        ),
                        name="llm_call_outcome_valid",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("outcome", "ok")),
                        fields=(
                            "user",
                            "task",
                            "entity_type",
                            "entity_id",
                            "prompt_version",
                            "input_hash",
                        ),
                        name="llm_call_one_answer_per_input",
                    ),
                ],
            },
        ),
        # Row-level security, and references that also match the owner (ADR 0006).
        sql.enable_tenant_rls("llm_llmcall"),
    ]
