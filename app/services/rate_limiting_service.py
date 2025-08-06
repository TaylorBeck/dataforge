"""
Advanced Rate Limiting and API Management Service

Implements comprehensive rate limiting with exponential backoff, batch processing 
optimization, and rate limit header monitoring based on OpenAI best practices.

Features:
- Exponential backoff with jitter for rate limit errors
- Batch processing optimization for multiple requests
- Rate limit header monitoring and usage tracking
- Concurrent request management with semaphores
- Request/token per minute (RPM/TPM) limit enforcement
- Proactive rate limit monitoring
"""

import asyncio
import logging
import random
import time
import weakref
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any, Callable, Union
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class RateLimitType(Enum):
    """Types of rate limits"""
    REQUESTS_PER_MINUTE = "rpm"
    TOKENS_PER_MINUTE = "tpm"
    REQUESTS_PER_DAY = "rpd"
    TOKENS_PER_DAY = "tpd"


@dataclass
class RateLimitInfo:
    """Information about rate limits from API headers"""
    limit: int
    remaining: int
    reset_time: datetime
    reset_duration: Optional[float] = None  # seconds until reset
    
    @property
    def usage_percentage(self) -> float:
        """Calculate current usage as percentage"""
        return ((self.limit - self.remaining) / self.limit) * 100 if self.limit > 0 else 0.0
    
    @property
    def is_near_limit(self, threshold: float = 0.8) -> bool:
        """Check if usage is near the limit threshold"""
        return self.usage_percentage >= (threshold * 100)


@dataclass
class RateLimitMetrics:
    """Rate limit metrics tracking"""
    total_requests: int = 0
    successful_requests: int = 0
    rate_limited_requests: int = 0
    retried_requests: int = 0
    average_response_time: float = 0.0
    peak_rpm: int = 0
    peak_tpm: int = 0
    last_reset: Optional[datetime] = None
    
    def update_response_time(self, response_time: float):
        """Update average response time with exponential moving average"""
        alpha = 0.1  # Smoothing factor
        if self.average_response_time == 0:
            self.average_response_time = response_time
        else:
            self.average_response_time = (alpha * response_time + 
                                       (1 - alpha) * self.average_response_time)


class RateLimitError(Exception):
    """Custom exception for rate limit errors"""
    def __init__(self, message: str, retry_after: Optional[float] = None, 
                 rate_limit_info: Optional[RateLimitInfo] = None):
        self.retry_after = retry_after
        self.rate_limit_info = rate_limit_info
        super().__init__(message)


class ExponentialBackoff:
    """
    Implements exponential backoff with jitter for retries
    
    Based on OpenAI best practices and AWS recommendations
    """
    
    def __init__(self, 
                 initial_delay: float = 1.0,
                 max_delay: float = 60.0,
                 exponential_base: float = 2.0,
                 jitter: bool = True,
                 max_retries: int = 6):
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.max_retries = max_retries
    
    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number"""
        if attempt <= 0:
            return 0.0
        
        # Exponential backoff: initial_delay * (base ^ attempt)
        delay = self.initial_delay * (self.exponential_base ** (attempt - 1))
        
        # Cap at max delay
        delay = min(delay, self.max_delay)
        
        # Add jitter to prevent thundering herd
        if self.jitter:
            jitter_range = delay * 0.1  # 10% jitter
            delay += random.uniform(-jitter_range, jitter_range)
        
        return max(0.0, delay)
    
    async def sleep(self, attempt: int):
        """Sleep for calculated delay"""
        delay = self.calculate_delay(attempt)
        if delay > 0:
            logger.debug(f"Exponential backoff: sleeping {delay:.2f}s for attempt {attempt}")
            await asyncio.sleep(delay)


class TokenBucket:
    """
    Token bucket algorithm for rate limiting
    
    Allows burst requests up to bucket size while maintaining average rate
    """
    
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate  # tokens per second
        self.tokens = capacity
        self.last_refill = time.time()
        self._lock = asyncio.Lock()
    
    async def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens, return True if successful"""
        async with self._lock:
            now = time.time()
            
            # Refill tokens based on elapsed time
            elapsed = now - self.last_refill
            new_tokens = elapsed * self.refill_rate
            self.tokens = min(self.capacity, self.tokens + new_tokens)
            self.last_refill = now
            
            # Check if we have enough tokens
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False
    
    async def wait_for_tokens(self, tokens: int = 1, timeout: Optional[float] = None) -> bool:
        """Wait until tokens are available"""
        start_time = time.time()
        
        while True:
            if await self.consume(tokens):
                return True
            
            if timeout and (time.time() - start_time) >= timeout:
                return False
            
            # Calculate how long to wait for next tokens
            async with self._lock:
                tokens_needed = tokens - self.tokens
                wait_time = min(1.0, tokens_needed / self.refill_rate)
            
            await asyncio.sleep(wait_time)


class BatchProcessor:
    """
    Optimizes multiple API requests through intelligent batching
    """
    
    def __init__(self, 
                 max_batch_size: int = 10,
                 max_wait_time: float = 0.5,
                 max_tokens_per_batch: int = 4000):
        self.max_batch_size = max_batch_size
        self.max_wait_time = max_wait_time
        self.max_tokens_per_batch = max_tokens_per_batch
        self._pending_requests: deque = deque()
        self._batch_lock = asyncio.Lock()
    
    async def add_request(self, request_data: Dict[str, Any], 
                         estimated_tokens: int = 100) -> Any:
        """Add request to batch and wait for processing"""
        future = asyncio.Future()
        request = {
            'data': request_data,
            'tokens': estimated_tokens,
            'future': future,
            'timestamp': time.time()
        }
        
        async with self._batch_lock:
            self._pending_requests.append(request)
        
        # Trigger batch processing if conditions are met
        await self._maybe_process_batch()
        
        # Wait for result
        return await future
    
    async def _maybe_process_batch(self):
        """Process batch if criteria are met"""
        async with self._batch_lock:
            if not self._pending_requests:
                return
            
            # Check if we should process the batch
            should_process = (
                len(self._pending_requests) >= self.max_batch_size or
                (self._pending_requests and 
                 time.time() - self._pending_requests[0]['timestamp'] >= self.max_wait_time)
            )
            
            if should_process:
                batch = []
                total_tokens = 0
                
                # Collect requests for batch
                while (self._pending_requests and 
                       len(batch) < self.max_batch_size and
                       total_tokens < self.max_tokens_per_batch):
                    
                    request = self._pending_requests.popleft()
                    batch.append(request)
                    total_tokens += request['tokens']
        
        if should_process and batch:
            # Process batch in background
            asyncio.create_task(self._process_batch(batch))
    
    async def _process_batch(self, batch: List[Dict[str, Any]]):
        """Process a batch of requests"""
        try:
            # Here you would implement actual batch processing
            # For now, we'll simulate processing each request individually
            for request in batch:
                try:
                    # Simulate processing
                    await asyncio.sleep(0.1)
                    result = {"processed": True, "data": request['data']}
                    request['future'].set_result(result)
                except Exception as e:
                    request['future'].set_exception(e)
        except Exception as e:
            # If batch processing fails, fail all requests
            for request in batch:
                if not request['future'].done():
                    request['future'].set_exception(e)


class RateLimitManager:
    """
    Comprehensive rate limit manager with monitoring and enforcement
    """
    
    def __init__(self, 
                 requests_per_minute: int = 60,
                 tokens_per_minute: int = 40000,
                 max_concurrent_requests: int = 10):
        
        self.requests_per_minute = requests_per_minute
        self.tokens_per_minute = tokens_per_minute
        self.max_concurrent_requests = max_concurrent_requests
        
        # Token buckets for rate limiting
        self.request_bucket = TokenBucket(
            capacity=requests_per_minute, 
            refill_rate=requests_per_minute / 60.0
        )
        self.token_bucket = TokenBucket(
            capacity=tokens_per_minute,
            refill_rate=tokens_per_minute / 60.0
        )
        
        # Concurrency control
        self.semaphore = asyncio.Semaphore(max_concurrent_requests)
        
        # Exponential backoff
        self.backoff = ExponentialBackoff()
        
        # Batch processor
        self.batch_processor = BatchProcessor()
        
        # Metrics tracking
        self.metrics = RateLimitMetrics()
        self._rate_limit_info: Dict[RateLimitType, RateLimitInfo] = {}
        
        # Request tracking
        self._request_times: deque = deque()
        self._token_usage: deque = deque()
    
    def update_rate_limits_from_headers(self, headers: Dict[str, str]):
        """Update rate limit info from API response headers"""
        try:
            # Parse OpenAI rate limit headers
            rpm_limit = int(headers.get('x-ratelimit-limit-requests', 0))
            rpm_remaining = int(headers.get('x-ratelimit-remaining-requests', 0))
            rpm_reset = headers.get('x-ratelimit-reset-requests', '0s')
            
            tpm_limit = int(headers.get('x-ratelimit-limit-tokens', 0))
            tpm_remaining = int(headers.get('x-ratelimit-remaining-tokens', 0))
            tpm_reset = headers.get('x-ratelimit-reset-tokens', '0s')
            
            # Parse reset times (format like "6m0s" or "1s")
            def parse_duration(duration_str: str) -> float:
                """Parse duration string to seconds"""
                if not duration_str:
                    return 0.0
                
                total_seconds = 0.0
                duration_str = duration_str.strip()
                
                # Handle formats like "6m0s", "1s", "2m"
                import re
                matches = re.findall(r'(\d+)([a-zA-Z])', duration_str)
                for value, unit in matches:
                    value = int(value)
                    if unit in ['s', 'sec']:
                        total_seconds += value
                    elif unit in ['m', 'min']:
                        total_seconds += value * 60
                    elif unit in ['h', 'hour']:
                        total_seconds += value * 3600
                
                return total_seconds
            
            now = datetime.now(timezone.utc)
            
            # Update request rate limit info
            if rpm_limit > 0:
                rpm_reset_seconds = parse_duration(rpm_reset)
                self._rate_limit_info[RateLimitType.REQUESTS_PER_MINUTE] = RateLimitInfo(
                    limit=rpm_limit,
                    remaining=rpm_remaining,
                    reset_time=now + timedelta(seconds=rpm_reset_seconds),
                    reset_duration=rpm_reset_seconds
                )
            
            # Update token rate limit info
            if tpm_limit > 0:
                tpm_reset_seconds = parse_duration(tpm_reset)
                self._rate_limit_info[RateLimitType.TOKENS_PER_MINUTE] = RateLimitInfo(
                    limit=tpm_limit,
                    remaining=tpm_remaining,
                    reset_time=now + timedelta(seconds=tpm_reset_seconds),
                    reset_duration=tpm_reset_seconds
                )
                
        except (ValueError, KeyError) as e:
            logger.warning(f"Failed to parse rate limit headers: {e}")
    
    def get_rate_limit_info(self, limit_type: RateLimitType) -> Optional[RateLimitInfo]:
        """Get current rate limit information"""
        return self._rate_limit_info.get(limit_type)
    
    async def check_proactive_limits(self, estimated_tokens: int = 0) -> Tuple[bool, Optional[str]]:
        """
        Proactively check if request would exceed rate limits
        Returns (can_proceed, reason_if_blocked)
        """
        # Check request rate limit
        rpm_info = self.get_rate_limit_info(RateLimitType.REQUESTS_PER_MINUTE)
        if rpm_info and rpm_info.remaining <= 0:
            return False, f"Request rate limit exceeded. Reset in {rpm_info.reset_duration}s"
        
        # Check token rate limit
        tpm_info = self.get_rate_limit_info(RateLimitType.TOKENS_PER_MINUTE)
        if tpm_info and tpm_info.remaining < estimated_tokens:
            return False, f"Token rate limit would be exceeded. Need {estimated_tokens}, have {tpm_info.remaining}"
        
        # Check if approaching limits (proactive throttling)
        if rpm_info and rpm_info.is_near_limit(threshold=0.9):
            logger.warning(f"Approaching request rate limit: {rpm_info.usage_percentage:.1f}% used")
        
        if tpm_info and tpm_info.is_near_limit(threshold=0.9):
            logger.warning(f"Approaching token rate limit: {tpm_info.usage_percentage:.1f}% used")
        
        return True, None
    
    @asynccontextmanager
    async def rate_limited_request(self, estimated_tokens: int = 100):
        """
        Context manager for rate-limited API requests with comprehensive monitoring
        """
        start_time = time.time()
        attempt = 0
        
        async with self.semaphore:  # Limit concurrent requests
            while attempt < self.backoff.max_retries:
                attempt += 1
                self.metrics.total_requests += 1
                
                try:
                    # Proactive rate limit check
                    can_proceed, reason = await self.check_proactive_limits(estimated_tokens)
                    if not can_proceed:
                        logger.warning(f"Proactive rate limit block: {reason}")
                        await self.backoff.sleep(attempt)
                        continue
                    
                    # Wait for token bucket availability
                    request_allowed = await self.request_bucket.consume(1)
                    tokens_allowed = await self.token_bucket.consume(estimated_tokens)
                    
                    if not request_allowed:
                        logger.warning("Request bucket rate limit reached")
                        await self.backoff.sleep(attempt)
                        continue
                    
                    if not tokens_allowed:
                        logger.warning(f"Token bucket rate limit reached for {estimated_tokens} tokens")
                        await self.backoff.sleep(attempt)
                        continue
                    
                    # Track request timing
                    self._request_times.append(time.time())
                    self._token_usage.append(estimated_tokens)
                    
                    # Clean old tracking data (keep last 5 minutes)
                    cutoff_time = time.time() - 300
                    while self._request_times and self._request_times[0] < cutoff_time:
                        self._request_times.popleft()
                    while self._token_usage and len(self._token_usage) > len(self._request_times):
                        self._token_usage.popleft()
                    
                    yield self
                    
                    # Success
                    response_time = time.time() - start_time
                    self.metrics.successful_requests += 1
                    self.metrics.update_response_time(response_time)
                    return
                    
                except RateLimitError as e:
                    self.metrics.rate_limited_requests += 1
                    logger.warning(f"Rate limit error on attempt {attempt}: {e}")
                    
                    if e.retry_after:
                        await asyncio.sleep(e.retry_after)
                    else:
                        await self.backoff.sleep(attempt)
                    
                    if attempt < self.backoff.max_retries:
                        self.metrics.retried_requests += 1
                    
                except Exception as e:
                    logger.error(f"Unexpected error in rate limited request: {e}")
                    raise
            
            # All retries exhausted
            raise RateLimitError(f"Max retries ({self.backoff.max_retries}) exceeded")
    
    def get_current_usage(self) -> Dict[str, Any]:
        """Get current rate limiting usage statistics"""
        now = time.time()
        last_minute = now - 60
        
        # Count requests and tokens in last minute
        recent_requests = sum(1 for t in self._request_times if t > last_minute)
        recent_tokens = sum(tokens for i, tokens in enumerate(self._token_usage) 
                          if i < len(self._request_times) and self._request_times[i] > last_minute)
        
        return {
            'requests_last_minute': recent_requests,
            'tokens_last_minute': recent_tokens,
            'requests_per_minute_limit': self.requests_per_minute,
            'tokens_per_minute_limit': self.tokens_per_minute,
            'request_usage_percentage': (recent_requests / self.requests_per_minute) * 100,
            'token_usage_percentage': (recent_tokens / self.tokens_per_minute) * 100,
            'concurrent_requests': self.max_concurrent_requests - self.semaphore._value,
            'metrics': self.metrics
        }


# Global rate limit manager instance
_rate_limit_manager: Optional[RateLimitManager] = None


def get_rate_limit_manager() -> RateLimitManager:
    """Get or create global rate limit manager instance"""
    global _rate_limit_manager
    if _rate_limit_manager is None:
        from app.config import get_settings
        settings = get_settings()
        
        _rate_limit_manager = RateLimitManager(
            requests_per_minute=getattr(settings, 'openai_requests_per_minute', 60),
            tokens_per_minute=getattr(settings, 'openai_tokens_per_minute', 40000),
            max_concurrent_requests=getattr(settings, 'openai_max_concurrent_requests', 10)
        )
    
    return _rate_limit_manager


def reset_rate_limit_manager():
    """Reset global rate limit manager (useful for testing)"""
    global _rate_limit_manager
    _rate_limit_manager = None