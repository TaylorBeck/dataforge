import asyncio
import pytest

from app.services.rate_limiting_service import RateLimitManager, RateLimitType


@pytest.mark.asyncio
async def test_rate_limiter_basic_flow():
    rlm = RateLimitManager(requests_per_minute=5, tokens_per_minute=100, max_concurrent_requests=2)

    # Should allow a small request within limits
    async with rlm.rate_limited_request(estimated_tokens=10):
        pass

    usage = rlm.get_current_usage()
    assert usage["requests_last_minute"] >= 1
    assert usage["tokens_last_minute"] >= 10


def test_update_rate_limits_from_headers():
    rlm = RateLimitManager()
    headers = {
        "x-ratelimit-limit-requests": "60",
        "x-ratelimit-remaining-requests": "50",
        "x-ratelimit-reset-requests": "10s",
        "x-ratelimit-limit-tokens": "40000",
        "x-ratelimit-remaining-tokens": "35000",
        "x-ratelimit-reset-tokens": "1m",
    }
    rlm.update_rate_limits_from_headers(headers)
    info_rpm = rlm.get_rate_limit_info(RateLimitType.REQUESTS_PER_MINUTE)
    info_tpm = rlm.get_rate_limit_info(RateLimitType.TOKENS_PER_MINUTE)
    assert info_rpm is not None and info_rpm.limit == 60
    assert info_tpm is not None and info_tpm.limit == 40000
