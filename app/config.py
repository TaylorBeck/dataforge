"""
Configuration management for the DataForge application.
"""
import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # API Configuration
    api_title: str = Field("DataForge API", description="API title")
    api_version: str = Field("1.0.0", description="API version")
    api_description: str = Field(
        "Modern synthetic text data generation using LLMs", 
        description="API description"
    )
    debug: bool = Field(False, description="Debug mode")
    
    # Redis Configuration
    redis_url: str = Field(
        "redis://localhost:6379/0", 
        description="Redis connection URL"
    )
    redis_job_expire_seconds: int = Field(
        3600, 
        description="Job expiration time in Redis (seconds)"
    )
    redis_result_expire_seconds: int = Field(
        7200,
        description="Result expiration time in Redis (seconds)"
    )
    
    # Job Processing Configuration
    max_samples_per_request: int = Field(
        50, 
        ge=1, 
        le=1000,
        description="Maximum samples allowed per generation request"
    )
    max_concurrent_jobs: int = Field(
        10,
        ge=1,
        le=100,
        description="Maximum concurrent generation jobs"
    )
    job_timeout_seconds: int = Field(
        300,
        ge=60,
        le=3600,
        description="Job timeout in seconds"
    )
    
    # LLM Configuration
    openai_api_key: Optional[str] = Field(
        None, 
        description="OpenAI API key"
    )
    openai_model: str = Field(
        "gpt-4", 
        description="OpenAI model to use"
    )
    openai_max_tokens: int = Field(
        500,
        ge=1,
        le=4000,
        description="Maximum tokens per generation"
    )
    openai_timeout_seconds: int = Field(
        60,
        ge=5,
        le=300,
        description="OpenAI API timeout"
    )
    
    # Anthropic Configuration (for future use)
    anthropic_api_key: Optional[str] = Field(
        None,
        description="Anthropic API key"
    )
    anthropic_model: str = Field(
        "claude-3-sonnet-20240229",
        description="Anthropic model to use"
    )
    
    # Default LLM Provider
    default_llm_provider: str = Field(
        "openai",
        description="Default LLM provider (openai, anthropic, mock)"
    )
    
    # Template Configuration
    prompt_template_dir: str = Field(
        "app/templates",
        description="Directory containing prompt templates"
    )
    default_prompt_template: str = Field(
        "support_request.j2",
        description="Default prompt template file"
    )
    
    # Rate Limiting (for future implementation)
    rate_limit_per_minute: int = Field(
        60,
        ge=1,
        le=1000,
        description="Rate limit per minute per IP"
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings instance."""
    return settings


def validate_settings() -> None:
    """Validate critical settings and raise errors if misconfigured."""
    if settings.default_llm_provider == "openai" and not settings.openai_api_key:
        raise ValueError(
            "OpenAI API key is required when using OpenAI as the default provider. "
            "Set OPENAI_API_KEY environment variable."
        )
    
    if settings.default_llm_provider == "anthropic" and not settings.anthropic_api_key:
        raise ValueError(
            "Anthropic API key is required when using Anthropic as the default provider. "
            "Set ANTHROPIC_API_KEY environment variable."
        )
    
    if settings.redis_url.startswith("redis://localhost") and not settings.debug:
        print("WARNING: Using localhost Redis in production mode")


# Validate settings on import
if os.getenv("SKIP_VALIDATION") != "true":
    try:
        validate_settings()
    except ValueError as e:
        if settings.default_llm_provider != "mock":
            print(f"Configuration Warning: {e}")
            print("Continuing with mock LLM provider for development...")