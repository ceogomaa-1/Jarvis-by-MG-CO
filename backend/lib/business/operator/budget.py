"""
Operator Agent budget enforcement.

Tracks cost per Anthropic call (approximated by model + max_tokens) and stops
the run when cumulative spend hits the user's daily cap.

Cost approximations are conservative high-side — better to under-budget than
to surprise the user with a bill.
"""

# Per-1K-token output cost approximations, conservative high side (USD).
_COST_PER_1K_OUTPUT = {
    "claude-haiku-4-5-20251001": 0.005,
    "claude-sonnet-4-6": 0.015,
    "claude-opus-4-7": 0.075,
}

# Per-1K-token input cost approximations.
_COST_PER_1K_INPUT = {
    "claude-haiku-4-5-20251001": 0.001,
    "claude-sonnet-4-6": 0.003,
    "claude-opus-4-7": 0.015,
}


class BudgetTracker:
    """One per operator run. Call .charge() after each API call."""

    def __init__(self, daily_budget_usd: float):
        self.daily_budget_usd = float(daily_budget_usd or 5.0)
        self.spent_usd = 0.0
        self.calls = 0

    def estimate_call_cost(
        self,
        model: str,
        input_tokens_est: int,
        max_output_tokens: int,
    ) -> float:
        """Worst-case cost for one call."""
        out_rate = _COST_PER_1K_OUTPUT.get(model, 0.075)
        in_rate = _COST_PER_1K_INPUT.get(model, 0.015)
        return (max_output_tokens / 1000.0) * out_rate + (input_tokens_est / 1000.0) * in_rate

    def can_afford(self, model: str, input_tokens_est: int, max_output_tokens: int) -> bool:
        cost = self.estimate_call_cost(model, input_tokens_est, max_output_tokens)
        return (self.spent_usd + cost) <= self.daily_budget_usd

    def charge(self, model: str, input_tokens_est: int, max_output_tokens: int) -> float:
        """Record a call's cost. Returns the charged amount."""
        cost = self.estimate_call_cost(model, input_tokens_est, max_output_tokens)
        self.spent_usd += cost
        self.calls += 1
        return cost

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.daily_budget_usd - self.spent_usd)

    @property
    def is_exhausted(self) -> bool:
        return self.spent_usd >= self.daily_budget_usd
