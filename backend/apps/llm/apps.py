from django.apps import AppConfig


class LlmConfig(AppConfig):
    name = "apps.llm"

    def ready(self) -> None:
        # Imported for its side effect: registering the "no model key in the api" check.
        from apps.llm import checks  # noqa: F401
