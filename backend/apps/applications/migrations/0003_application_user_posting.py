import django.db.models.deletion
from django.db import migrations, models

from apps.tenancy import sql


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0001_grants"),
        ("applications", "0002_contact"),
        ("postings", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="application",
            name="user_posting",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="applications",
                to="postings.userposting",
            ),
        ),
        # Row-level security, and references that also match the owner (ADR 0006).
        sql.same_tenant_foreign_key(
            "applications_application", "user_posting_id", "postings_userposting"
        ),
    ]
