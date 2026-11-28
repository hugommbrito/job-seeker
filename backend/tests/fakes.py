"""Stand-ins for the services the app reaches over the network. No test ever calls a real one."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from apps.llm.gateway import GatewayRequest, GatewayResult


@dataclass
class FakeGateway:
    """Answers each request with the next scripted result, or with ``answer(request)``."""

    results: list[GatewayResult] = field(default_factory=list)
    answer: Callable[[GatewayRequest], GatewayResult] | None = None
    requests: list[GatewayRequest] = field(default_factory=list)

    def run(self, request: GatewayRequest) -> GatewayResult:
        self.requests.append(request)
        if self.answer is not None:
            return self.answer(request)
        return self.results.pop(0)


@dataclass
class FakeBot:
    """A Telegram bot that records what it would send and serves a scripted inbox."""

    inbox: list = field(default_factory=list)
    sent: list[tuple[int, str]] = field(default_factory=list)
    fail_with: str | None = None

    def send(self, chat_id: int, text: str):
        from apps.notifications.telegram import SendResult

        if self.fail_with:
            return SendResult(False, self.fail_with)
        self.sent.append((chat_id, text))
        return SendResult(True)

    def updates(self, offset: int):
        return [update for update in self.inbox if update.update_id >= offset]
