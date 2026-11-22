from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("tenancy", "0001_grants"),
    ]

    operations = [
        migrations.CreateModel(
            name="LoginThrottle",
            fields=[
                ("key", models.CharField(max_length=64, primary_key=True, serialize=False)),
                ("failures", models.PositiveIntegerField()),
                ("window_start", models.DateTimeField()),
            ],
        ),
        migrations.CreateModel(
            name="Session",
            fields=[
                ("session_data", models.TextField(verbose_name="session data")),
                ("expire_date", models.DateTimeField(db_index=True, verbose_name="expire date")),
                (
                    "session_key",
                    models.CharField(
                        db_column="key_hash", max_length=64, primary_key=True, serialize=False
                    ),
                ),
            ],
            options={
                "verbose_name": "session",
                "verbose_name_plural": "sessions",
                "db_table": "accounts_session",
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="User",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                ("email", models.EmailField(max_length=254, unique=True)),
                (
                    "role",
                    models.CharField(
                        choices=[("owner", "Owner"), ("member", "Member"), ("demo", "Demo")],
                        max_length=16,
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("role__in", ["owner", "member", "demo"])),
                        name="accounts_user_role_valid",
                    )
                ],
            },
        ),
    ]
