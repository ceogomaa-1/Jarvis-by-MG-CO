"""
Per-request API cost accounting for Jarvis Business chat.

Anthropic bills four token buckets per request:
  - input_tokens               — uncached prompt tokens, full input price
  - cache_creation_input_tokens — written to the prompt cache, 1.25x input price
  - cache_read_input_tokens     — served from the prompt cache, 0.10x input price
  - output_tokens               — generated tokens, output price

A single Business chat turn can span several model round-trips (one per tool
round). `UsageAccumulator` sums the buckets across every round so we can report
the true cost of the whole turn — and, crucially, show how much the prompt cache
saved vs. what an uncached run would have cost.

Prices are per 1M tokens, from the Anthropic pricing table (2026):
  Opus 4.8   $5 in / $25 out
  Sonnet 4.6 $3 in / $15 out
  Haiku 4.5  $1 in / $5 out
"""
from __future__ import annotations

# model id (prefix-matched) -> (input_per_mtok, output_per_mtok) in USD
_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus": (5.0, 25.0),
    "claude-sonnet": (3.0, 15.0),
    "claude-haiku": (1.0, 5.0),
}

# Cache write costs 1.25x the base input rate; cache read costs 0.10x.
_CACHE_WRITE_MULT = 1.25
_CACHE_READ_MULT = 0.10

_FALLBACK = (3.0, 15.0)  # default to Sonnet pricing for an unknown model id


def _rates(model: str) -> tuple[float, float]:
    for prefix, rates in _PRICING.items():
        if model.startswith(prefix):
            return rates
    return _FALLBACK


class UsageAccumulator:
    """Sums Anthropic usage buckets across the tool-use rounds of one chat turn."""

    def __init__(self, model: str, provider: str = "claude"):
        self.model = model
        self.provider = provider
        self.input_tokens = 0
        self.cache_creation_input_tokens = 0
        self.cache_read_input_tokens = 0
        self.output_tokens = 0
        self.rounds = 0

    def add_message_start(self, usage: dict) -> None:
        """Apply the usage block from a `message_start` event (input buckets)."""
        if not usage:
            return
        self.rounds += 1
        self.input_tokens += int(usage.get("input_tokens") or 0)
        self.cache_creation_input_tokens += int(usage.get("cache_creation_input_tokens") or 0)
        self.cache_read_input_tokens += int(usage.get("cache_read_input_tokens") or 0)
        # message_start carries a small initial output_tokens; the final count
        # arrives on message_delta, so don't add it here (avoid double counting).

    def add_sdk_usage(self, usage) -> None:
        """Apply the `usage` object returned by a non-streaming SDK call (one round).

        The SDK returns final per-call counts, so input AND output are added here.
        """
        if usage is None:
            return
        self.rounds += 1
        self.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
        self.cache_creation_input_tokens += int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
        self.cache_read_input_tokens += int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        self.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)

    def add_round_output(self, output_tokens: int) -> None:
        """Apply the final output_tokens for one completed round.

        message_delta reports a running total for the CURRENT message, so the
        caller tracks the latest value per round and passes it here once, when
        that round's stream ends — never on every delta (that would double-count).
        """
        self.output_tokens += int(output_tokens or 0)

    def cost(self) -> dict:
        """Return the dollar breakdown for everything accumulated so far."""
        in_rate, out_rate = _rates(self.model)
        input_cost = self.input_tokens / 1_000_000 * in_rate
        cache_write_cost = self.cache_creation_input_tokens / 1_000_000 * in_rate * _CACHE_WRITE_MULT
        cache_read_cost = self.cache_read_input_tokens / 1_000_000 * in_rate * _CACHE_READ_MULT
        output_cost = self.output_tokens / 1_000_000 * out_rate
        total = input_cost + cache_write_cost + cache_read_cost + output_cost

        # What the same tokens would have cost with NO prompt caching: every
        # cached-read and cache-write token billed at the full input rate.
        cached_tokens = self.cache_creation_input_tokens + self.cache_read_input_tokens
        uncached_total = (
            (self.input_tokens + cached_tokens) / 1_000_000 * in_rate
            + output_cost
        )
        saved = max(uncached_total - total, 0.0)

        return {
            "provider": self.provider,
            "model": self.model,
            "rounds": self.rounds,
            "input_tokens": self.input_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "output_tokens": self.output_tokens,
            "total_usd": round(total, 6),
            "uncached_usd": round(uncached_total, 6),
            "cache_saved_usd": round(saved, 6),
        }

    def log_line(self) -> str:
        c = self.cost()
        return (
            f"[COST] provider={c['provider']} model={c['model']} rounds={c['rounds']} "
            f"in={c['input_tokens']} cache_w={c['cache_creation_input_tokens']} "
            f"cache_r={c['cache_read_input_tokens']} out={c['output_tokens']} "
            f"=> ${c['total_usd']:.4f} (uncached ${c['uncached_usd']:.4f}, "
            f"cache saved ${c['cache_saved_usd']:.4f})"
        )
