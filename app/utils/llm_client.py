"""
Pluggable async LLM client interface and implementations.
"""
import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import aiohttp
from openai import AsyncOpenAI
from app.config import get_settings

logger = logging.getLogger(__name__)


class LLMClientInterface(ABC):
    """Abstract base class for LLM clients."""
    
    @abstractmethod
    async def generate(
        self, 
        prompt: str, 
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Generate text using the LLM.
        
        Args:
            prompt: Input prompt text
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate
            
        Returns:
            Generated text string
            
        Raises:
            LLMException: On generation failure
        """
        pass
    
    @abstractmethod
    async def get_model_info(self) -> Dict[str, Any]:
        """Get information about the current model."""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the LLM service is available."""
        pass


class LLMException(Exception):
    """Exception raised by LLM clients."""
    pass


class OpenAIClient(LLMClientInterface):
    """OpenAI GPT client implementation."""
    
    def __init__(self, api_key: str, model: str = "gpt-4", timeout: int = 60):
        """
        Initialize OpenAI client.
        
        Args:
            api_key: OpenAI API key
            model: Model name (e.g., "gpt-4", "gpt-3.5-turbo")
            timeout: Request timeout in seconds
        """
        self.client = AsyncOpenAI(api_key=api_key, timeout=timeout)
        self.model = model
        self.timeout = timeout
    
    async def generate(
        self, 
        prompt: str, 
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        """Generate text using OpenAI API with advanced rate limiting."""
        settings = get_settings()
        max_tokens = max_tokens or settings.openai_max_tokens
        
        # Import rate limiting inside function to avoid circular imports
        try:
            from app.services.rate_limiting_service import get_rate_limit_manager, RateLimitError
            rate_limit_manager = get_rate_limit_manager()
            use_rate_limiting = True
        except ImportError:
            logger.warning("Rate limiting service not available, proceeding without rate limiting")
            use_rate_limiting = False
        
        # Estimate tokens for rate limiting (rough approximation)
        estimated_tokens = len(prompt) // 4 + (max_tokens or 0)
        
        try:
            if use_rate_limiting:
                async with rate_limit_manager.rate_limited_request(estimated_tokens=estimated_tokens) as limiter:
                    response = await self._make_openai_request(prompt, temperature, max_tokens)
                    
                    # Extract rate limit headers and update manager
                    if hasattr(response, '_raw_response') and hasattr(response._raw_response, 'headers'):
                        headers = dict(response._raw_response.headers)
                        rate_limit_manager.update_rate_limits_from_headers(headers)
                    
                    return self._process_openai_response(response)
            else:
                response = await self._make_openai_request(prompt, temperature, max_tokens)
                return self._process_openai_response(response)
                
        except Exception as e:
            if use_rate_limiting and "RateLimitError" in str(type(e)):
                logger.error(f"Rate limit error: {e}")
                raise LLMException(f"OpenAI rate limit exceeded: {e}")
            
            logger.error(f"OpenAI generation failed: {e}")
            if "rate limit" in str(e).lower() or "429" in str(e):
                raise LLMException(f"OpenAI rate limit exceeded: {e}")
            elif "timeout" in str(e).lower():
                raise LLMException(f"OpenAI request timeout: {e}")
            else:
                raise LLMException(f"OpenAI generation failed: {e}")
    
    async def _make_openai_request(self, prompt: str, temperature: float, max_tokens: int):
        """Make the actual OpenAI API request"""
        return await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=self.timeout
        )
    
    def _process_openai_response(self, response):
        """Process OpenAI API response"""
        if not response.choices:
            raise LLMException("No response choices returned from OpenAI")
        
        content = response.choices[0].message.content
        if content is None:
            raise LLMException("Empty content returned from OpenAI")
            
        return content.strip()
    
    async def get_model_info(self) -> Dict[str, Any]:
        """Get OpenAI model information."""
        return {
            "provider": "openai",
            "model": self.model,
            "timeout": self.timeout
        }
    
    async def health_check(self) -> bool:
        """Check OpenAI API availability."""
        try:
            # Simple test generation with minimal tokens
            await self.generate("Test", temperature=0.1, max_tokens=1)
            return True
        except Exception as e:
            logger.warning(f"OpenAI health check failed: {e}")
            return False


class AnthropicClient(LLMClientInterface):
    """Anthropic Claude client implementation (placeholder for future)."""
    
    def __init__(self, api_key: str, model: str = "claude-3-sonnet-20240229"):
        """Initialize Anthropic client."""
        self.api_key = api_key
        self.model = model
        # NOTE: This is a placeholder - actual implementation would use anthropic library
    
    async def generate(
        self, 
        prompt: str, 
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        """Generate text using Anthropic API."""
        # Placeholder implementation
        raise NotImplementedError("Anthropic client not yet implemented")
    
    async def get_model_info(self) -> Dict[str, Any]:
        """Get Anthropic model information."""
        return {
            "provider": "anthropic",
            "model": self.model
        }
    
    async def health_check(self) -> bool:
        """Check Anthropic API availability."""
        return False  # Not implemented yet


class MockLLMClient(LLMClientInterface):
    """Mock LLM client for testing and development."""
    
    def __init__(self, delay: float = 1.0):
        """
        Initialize mock client.
        
        Args:
            delay: Artificial delay in seconds to simulate API latency
        """
        self.delay = delay
    
    async def generate(
        self, 
        prompt: str, 
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        """Generate mock text response."""
        await asyncio.sleep(self.delay)  # Simulate API latency
        
        # Extract product from prompt for more realistic mock responses
        product = "the product"
        if "{{" in prompt and "}}" in prompt:
            # Try to extract product from Jinja2 template context
            import re
            product_match = re.search(r'about\s+([^.]+)', prompt.lower())
            if product_match:
                product = product_match.group(1).strip()
        
        mock_responses = [
            f"I'm experiencing issues with {product} and need immediate assistance. The problem started yesterday and is affecting my productivity.",
            f"Your {product} service is not working as expected. I've tried multiple troubleshooting steps but the issue persists.",
            f"I'm frustrated with the recent changes to {product}. The new interface is confusing and has broken my workflow.",
            f"There seems to be a bug in {product} that's preventing me from completing my tasks. Please investigate this urgently.",
            f"The {product} feature I rely on daily has stopped working. This is impacting my business operations significantly."
        ]
        
        # Use temperature to add some randomness
        import random
        random.seed(hash(prompt + str(temperature)))
        response = random.choice(mock_responses)
        
        # Adjust response length based on max_tokens
        if max_tokens and len(response.split()) > max_tokens:
            words = response.split()[:max_tokens]
            response = " ".join(words)
        
        return response
    
    async def get_model_info(self) -> Dict[str, Any]:
        """Get mock model information."""
        return {
            "provider": "mock",
            "model": "mock-gpt-4",
            "delay": self.delay
        }
    
    async def health_check(self) -> bool:
        """Mock health check always passes."""
        return True


def get_llm_client(provider: Optional[str] = None) -> LLMClientInterface:
    """
    Factory function to get LLM client instance.
    
    Args:
        provider: LLM provider name ("openai", "anthropic", "mock")
                 If None, uses default from settings
    
    Returns:
        LLM client instance
        
    Raises:
        ValueError: If provider is not supported or configuration is invalid
    """
    settings = get_settings()
    provider = provider or settings.default_llm_provider
    
    if provider == "openai":
        if not settings.openai_api_key:
            logger.warning("OpenAI API key not found, falling back to mock client")
            return MockLLMClient()
        return OpenAIClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeout=settings.openai_timeout_seconds
        )
    
    elif provider == "anthropic":
        if not settings.anthropic_api_key:
            logger.warning("Anthropic API key not found, falling back to mock client")
            return MockLLMClient()
        return AnthropicClient(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model
        )
    
    elif provider == "mock":
        return MockLLMClient()
    
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")


async def test_llm_client(client: LLMClientInterface) -> Dict[str, Any]:
    """
    Test LLM client functionality.
    
    Args:
        client: LLM client to test
        
    Returns:
        Test results dictionary
    """
    results = {
        "health_check": False,
        "generation_test": False,
        "model_info": {},
        "error": None
    }
    
    try:
        # Health check
        results["health_check"] = await client.health_check()
        
        # Model info
        results["model_info"] = await client.get_model_info()
        
        # Test generation
        test_prompt = "Generate a brief test message."
        response = await client.generate(test_prompt, temperature=0.1, max_tokens=20)
        results["generation_test"] = bool(response and len(response.strip()) > 0)
        results["test_response"] = response
        
    except Exception as e:
        results["error"] = str(e)
        logger.error(f"LLM client test failed: {e}")
    
    return results