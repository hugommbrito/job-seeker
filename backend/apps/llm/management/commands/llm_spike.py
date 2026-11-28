"""Check that the model gateway does what the app relies on. Spends a few cents; never in CI.

    manage.py llm_spike [--model ALIAS_OR_ID]

Run on the worker, which holds the gateway key. See apps/llm/spike.py for what is checked.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.llm.gateway import AnthropicGateway, gateway_key
from apps.llm.spike import run_spike


class Command(BaseCommand):
    help = "Check structured output, caching and thinking through the gateway (makes real calls)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--model", help="Alias or model id; default: the extractor's.")

    def handle(self, *args: Any, **options: Any) -> None:
        key = gateway_key()
        if not settings.LLM_GATEWAY_URL or not key:
            raise CommandError(
                "No gateway configured: set LLM_GATEWAY_URL, and LLM_GATEWAY_KEY or "
                "LLM_GATEWAY_KEY_FILE."
            )
        model = options["model"] or settings.LLM_TASKS["extractor"]["model"]
        checks = run_spike(AnthropicGateway(settings.LLM_GATEWAY_URL, key).client, model)
        for check in checks:
            mark = self.style.SUCCESS("PASS") if check.passed else self.style.ERROR("FAIL")
            self.stdout.write(f"{mark} {check.name}: {check.detail}")
        if any(not check.passed and check.gating for check in checks):
            raise CommandError(
                "The gateway's Anthropic endpoint lacks something the app needs. Point "
                "LLM_GATEWAY_URL at LiteLLM's pass-through route (/anthropic) and set the "
                "LLM_MODEL_* variables to model ids, then run this again."
            )
        self.stdout.write(self.style.SUCCESS("llm_spike: the gateway is usable as configured"))
