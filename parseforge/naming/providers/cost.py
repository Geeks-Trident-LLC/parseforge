"""Cost estimation for naming's LLM calls.

Reuses textfsm-ai's own pricing table (already a hard dependency, for
generation) rather than maintaining a second one here. Naming never calls
textfsm-ai's run_pipeline() itself — it talks to the Anthropic/OpenAI SDKs
directly — so this reaches into its pricing module specifically rather
than the full pipeline.

If cost estimation ever moves to its own standalone package (shared
across projects instead of borrowed from textfsm-ai), this is the one
place that import needs to change.
"""

from __future__ import annotations

from textfsm_ai.core.pricing import estimate_cost as _estimate_cost


def estimate_cost(
    input_tokens: int, output_tokens: int, total_tokens: int, provider: str, model: str
) -> float:
    return _estimate_cost(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        currency="USD",
        provider=provider,
        model=model,
    ).estimated_cost
