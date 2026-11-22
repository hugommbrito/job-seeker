from django.apps import AppConfig


class TenancyConfig(AppConfig):
    name = "apps.tenancy"

    def ready(self) -> None:
        # Imported for its side effect: registering the database-role system check.
        from apps.tenancy import checks  # noqa: F401
