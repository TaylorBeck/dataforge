"""
Pydantic models for request/response schemas and data validation.
"""
from datetime import datetime
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field
from pydantic import field_validator
from pydantic.config import ConfigDict


class GenerationRequest(BaseModel):
    """Request model for generating synthetic text data."""
    
    product: str = Field(
        ..., 
        min_length=2, 
        max_length=200,
        description="Product or topic for which to generate support requests"
    )
    count: int = Field(
        5, 
        ge=1, 
        le=50,
        description="Number of samples to generate (1-50)"
    )
    version: str = Field(
        "v1",
        min_length=1,
        max_length=20,
        description="Prompt template version to use"
    )
    temperature: float = Field(
        0.7,
        ge=0.0,
        le=2.0,
        description="LLM sampling temperature (0.0-2.0)"
    )
    
    @field_validator('product')
    @classmethod
    def sanitize_product(cls, v: str) -> str:
        """Sanitize product string to prevent injection attacks."""
        if not v or not v.strip():
            raise ValueError('Product cannot be empty')
        # Remove potentially dangerous characters but keep useful punctuation
        cleaned = ''.join(c for c in v if c.isalnum() or c in ' .,!?-_()[]{}')
        return cleaned.strip()


class GeneratedSample(BaseModel):
    """Model for a single generated text sample with metadata."""
    
    id: str = Field(..., description="Unique identifier for this sample")
    product: str = Field(..., description="Product this sample was generated for")
    prompt_version: str = Field(..., description="Version of prompt template used")
    generated_at: datetime = Field(..., description="UTC timestamp when sample was generated")
    text: str = Field(..., description="Generated text content")
    tokens_estimated: int = Field(..., ge=0, description="Estimated token count")
    temperature: float = Field(..., description="Temperature used for generation")
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict, 
        description="Additional metadata including augmentation information"
    )
    
    model_config = ConfigDict()


class GenerationResponse(BaseModel):
    """Response model containing generated samples."""
    
    samples: List[GeneratedSample] = Field(..., description="List of generated samples")
    total_samples: int = Field(..., description="Total number of samples generated")
    total_tokens_estimated: int = Field(..., description="Total estimated tokens across all samples")
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional metadata such as quality metrics, filter stats, augmentation info"
    )


class JobStatusResponse(BaseModel):
    """Response model for job status and results."""
    
    job_id: str = Field(..., description="Unique job identifier")
    status: Literal['pending', 'running', 'completed', 'error'] = Field(
        ..., 
        description="Current job status"
    )
    created_at: datetime = Field(..., description="Job creation timestamp")
    updated_at: datetime = Field(..., description="Last status update timestamp")
    error_message: Optional[str] = Field(None, description="Error message if status is 'error'")
    result: Optional[GenerationResponse] = Field(None, description="Generated samples if completed")
    progress: Optional[int] = Field(None, ge=0, le=100, description="Completion percentage (0-100)")
    
    model_config = ConfigDict()


class HealthCheckResponse(BaseModel):
    """Health check response model."""
    
    status: Literal['healthy', 'unhealthy'] = Field(..., description="Service health status")
    timestamp: datetime = Field(..., description="Health check timestamp")
    redis_connected: bool = Field(..., description="Redis connection status")
    version: str = Field(..., description="API version")
    
    model_config = ConfigDict()