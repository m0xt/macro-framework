"""Static weekly Anthropic token-cost estimates for the iteration surface."""
from __future__ import annotations

# Anthropic pricing (USD per million tokens). Match the public pricing page.
PRICING_AS_OF = "2026-05-27"
MODEL_PRICES_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-sonnet-4-5-20250929": (3.00, 15.00),
    "claude-opus-4-1-20250805": (15.00, 75.00),
}

# One row per Claude call site. Tokens are hand-tuned estimates that include
# the actual system/user prompts plus typical WebSearch context, refreshed by
# hand when prompts or cadence change materially.
COST_ESTIMATES: list[dict[str, str | int]] = [
    {
        "site": "weekly_briefs.py:market brief",
        "model": "claude-sonnet-4-5-20250929",
        "calls_per_week": 1,
        "tokens_in": 8_000,
        "tokens_out": 600,
    },
    {
        "site": "weekly_briefs.py:economy brief",
        "model": "claude-sonnet-4-5-20250929",
        "calls_per_week": 1,
        "tokens_in": 8_500,
        "tokens_out": 600,
    },
    {
        "site": "weekly_briefs.py:top brief",
        "model": "claude-sonnet-4-5-20250929",
        "calls_per_week": 1,
        "tokens_in": 7_500,
        "tokens_out": 600,
    },
]
