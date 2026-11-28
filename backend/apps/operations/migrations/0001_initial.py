from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [("tenancy", "0001_grants")]

    operations = [
        migrations.CreateModel(
            name="TaskRun",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("name", models.CharField(max_length=100)),
                ("started_at", models.DateTimeField()),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                (
                    "outcome",
                    models.CharField(
                        choices=[("running", "Running"), ("ok", "OK"), ("error", "Error")],
                        default="running",
                        max_length=16,
                    ),
                ),
                ("counts", models.JSONField(blank=True, default=dict)),
                ("error", models.CharField(blank=True, default="", max_length=200)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["name", "-started_at"], name="operations__name_9cdd22_idx")
                ],
            },
        ),
    ]
