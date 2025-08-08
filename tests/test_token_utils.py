from app.utils.token_utils import estimate_tokens, estimate_completion_cost, estimate_request_cost
from app.config import get_settings


def test_estimate_tokens_fallback():
    # Should not raise even if tiktoken is unavailable
    tokens = estimate_tokens("hello world", model="gpt-4")
    assert isinstance(tokens, int)
    assert tokens >= 1


def test_estimate_completion_cost_and_request_cost(monkeypatch):
    settings = get_settings()
    # Force specific model and pricing to avoid env dependence
    settings.openai_model = "gpt-4"
    settings.openai_prompt_rate_per_1k = 0.03
    settings.openai_completion_rate_per_1k = 0.06

    prompt_tokens = 100
    completion_tokens = 200
    cost = estimate_completion_cost(prompt_tokens, completion_tokens, settings.openai_model)
    # 100/1000*0.03 + 200/1000*0.06 = 0.003 + 0.012 = 0.015
    assert abs(cost - 0.015) < 1e-6

    pt, total_cost = estimate_request_cost("some prompt text", expected_completion_tokens=50)
    assert isinstance(pt, int)
    assert total_cost >= 0.0
