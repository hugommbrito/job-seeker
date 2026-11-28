"""What a call is estimated to cost, from its token counts.

An estimate for the owner's eyes; the gateway's budget is what actually stops spending. Prices
are USD per million tokens, from Anthropic's published list. A cache write costs 1.25 times the
input price (five-minute cache); a cache read is the reduced price the model lists.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings


@dataclass(frozen=True)
class Price:
    input: Decimal
    output: Decimal
    cache_write: Decimal
    cache_read: Decimal


PRICES: dict[str, Price] = {
    "claude-opus-5-5": Price(
        input=Decimal("4.00"),
        output=Decimal("20.00"),
        cache_write=Decimal("5.00"),
        cache_read=Decimal("0.20"),
    ),
}

MILLION = Decimal(1_000_000)


def price_for(model: str) -> Price | None:
    """The price of the model the gateway reported; aliases are priced as LLM_PRICED_AS."""
    name = model.rsplit("/", 1)[-1]
    return PRICES.get(name) or PRICES.get(settings.LLM_PRICED_AS)


def estimate(
    model: str, *, input_tokens: int, output_tokens: int, cache_write: int, cache_read: int
) -> Decimal | None:
    price = price_for(model)
    if price is None:
        return None
    total = (
        input_tokens * price.input
        + output_tokens * price.output
        + cache_write * price.cache_write
        + cache_read * price.cache_read
    )
    return (total / MILLION).quantize(Decimal("0.000001"))
