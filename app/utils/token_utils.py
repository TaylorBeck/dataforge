"""
Token estimation and cost calculation utilities.
Uses tiktoken if available for accurate tokenization; falls back to heuristic.
"""
from typing import Tuple
from app.config import get_settings


def estimate_tokens(text: str, model: str) -> int:
    try:
        import tiktoken  # type: ignore
        enc = tiktoken.encoding_for_model(model)
        return len(enc.encode(text))
    except Exception:
        # Fallback heuristic: ~4 chars per token
        return max(1, len(text) // 4)


def estimate_completion_cost(prompt_tokens: int, completion_tokens: int, model: str) -> float:
    """Estimate USD cost based on model. Values are placeholders; adjust per model/pricing."""
    # Basic example pricing map (USD per 1K tokens)
    pricing = {
        # example placeholders; update with current pricing as needed
        "gpt-4": (0.03, 0.06),
        "gpt-4o": (0.005, 0.015),
        "gpt-3.5-turbo": (0.0015, 0.002),
    }
    settings = get_settings()
    default_prompt_rate, default_completion_rate = pricing.get(model, pricing.get("gpt-4", (0.03, 0.06)))
    prompt_rate = settings.openai_prompt_rate_per_1k or default_prompt_rate
    completion_rate = settings.openai_completion_rate_per_1k or default_completion_rate
    return (prompt_tokens / 1000.0) * prompt_rate + (completion_tokens / 1000.0) * completion_rate


def estimate_request_cost(prompt_text: str, expected_completion_tokens: int) -> Tuple[int, float]:
    settings = get_settings()
    model = settings.openai_model
    prompt_tokens = estimate_tokens(prompt_text, model)
    cost = estimate_completion_cost(prompt_tokens, expected_completion_tokens, model)
    return prompt_tokens, cost

