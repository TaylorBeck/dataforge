"""
FastAPI routes for text generation endpoints.
"""
import asyncio
import logging
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Query
from fastapi.responses import JSONResponse
from app.models.schemas import (
    GenerationRequest, 
    JobStatusResponse, 
    HealthCheckResponse
)
from app.services.generation_service import get_generation_service, run_generation_job
from app.services.job_store import get_job_store
from app.services.rate_limiting_service import get_rate_limit_manager
from app.utils.llm_client import get_llm_client, test_llm_client
from app.config import get_settings
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Create router instance
router = APIRouter(prefix="/api", tags=["generation"])


@router.post("/generate", response_model=JobStatusResponse)
async def create_generation_job(
    request: GenerationRequest
) -> JobStatusResponse:
    """
    Create a new text generation job using Celery.
    
    This endpoint accepts a generation request and returns a job ID immediately.
    The actual generation happens in Celery worker processes for better scalability.
    
    Args:
        request: Generation parameters including product, count, and version
        
    Returns:
        Job status response with job ID and initial status
        
    Raises:
        HTTPException: On validation errors or system unavailability
    """
    try:
        logger.info(f"Creating Celery generation job for product: {request.product}")
        
        # Validate request
        generation_service = get_generation_service()
        validation = await generation_service.validate_generation_request(request)
        
        if not validation["valid"]:
            error_message = "; ".join(validation["errors"])
            raise HTTPException(status_code=400, detail=f"Invalid request: {error_message}")
        
        # Log warnings if any
        if validation["warnings"]:
            for warning in validation["warnings"]:
                logger.warning(f"Generation request warning: {warning}")
        
        # Create job via JobStore
        job_store = get_job_store()
        job_id = job_store.create_generation_job(request)
        
        # Return job status
        job_status = job_store.get_status(job_id)
        if not job_status:
            raise HTTPException(status_code=500, detail="Failed to create job")
        
        logger.info(f"Created Celery generation job {job_id}")
        return job_status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create generation job: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/result/{job_id}", response_model=JobStatusResponse)
async def get_job_result(job_id: str) -> JobStatusResponse:
    """
    Get job status and results from Celery.
    
    Args:
        job_id: Unique job identifier (Celery task ID)
        
    Returns:
        Job status with results if completed
        
    Raises:
        HTTPException: If job not found
    """
    try:
        job_store = get_job_store()
        job_status = job_store.get_status(job_id)
        
        if not job_status:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        
        return job_status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job result for {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/health", response_model=HealthCheckResponse)
async def health_check() -> HealthCheckResponse:
    """
    Health check endpoint.
    
    Returns:
        Health status of the service and its dependencies
    """
    try:
        settings = get_settings()
        
        # Check Celery workers via JobStore
        celery_healthy = False
        try:
            job_store = get_job_store()
            stats = job_store.get_stats()
            celery_healthy = stats.get("active_workers", 0) > 0 or bool(stats)
        except Exception as e:
            logger.warning(f"Celery health check failed: {e}")

        # Determine overall health based on Celery availability
        status = "healthy" if celery_healthy else "unhealthy"
        
        return HealthCheckResponse(
            status=status,
            timestamp=datetime.now(timezone.utc),
            # Legacy field retained for schema compatibility; no longer using Redis directly
            redis_connected=False,
            version=settings.api_version
        )
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthCheckResponse(
            status="unhealthy",
            timestamp=datetime.now(timezone.utc),
            redis_connected=False,
            version="unknown"
        )


@router.post("/test-llm")
async def test_llm_connection() -> Dict[str, Any]:
    """
    Test LLM connection and functionality.
    
    Returns:
        Test results dictionary
    """
    try:
        llm_client = get_llm_client()
        test_results = await test_llm_client(llm_client)
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "results": test_results
        }
        
    except Exception as e:
        logger.error(f"LLM test failed: {e}")
        raise HTTPException(status_code=500, detail=f"LLM test failed: {str(e)}")


@router.post("/validate")
async def validate_generation_request(request: GenerationRequest) -> Dict[str, Any]:
    """
    Validate a generation request without creating a job.
    
    Args:
        request: Generation request to validate
        
    Returns:
        Validation results
    """
    try:
        generation_service = get_generation_service()
        validation = await generation_service.validate_generation_request(request)
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request": request.model_dump(),
            "validation": validation
        }
        
    except Exception as e:
        logger.error(f"Request validation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


@router.delete("/job/{job_id}")
async def cancel_job(job_id: str) -> Dict[str, str]:
    """
    Cancel a running Celery job.
    
    Celery provides better cancellation capabilities than the legacy system,
    with the ability to terminate running tasks.
    
    Args:
        job_id: Job identifier (Celery task ID) to cancel
        
    Returns:
        Cancellation status
    """
    try:
        job_store = get_job_store()
        
        # Check if job exists
        job_status = job_store.get_status(job_id)
        if not job_status:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        
        # Only cancel pending or running jobs
        if job_status.status in ["completed", "error"]:
            return {
                "job_id": job_id,
                "status": "already_finished",
                "message": f"Job is already {job_status.status}"
            }
        
        # Cancel the Celery task
        success = job_store.cancel(job_id)
        
        if success:
            logger.info(f"Cancelled Celery job {job_id}")
            return {
                "job_id": job_id,
                "status": "cancelled",
                "message": "Job cancellation requested and sent to workers"
            }
        else:
            return {
                "job_id": job_id,
                "status": "cancel_failed", 
                "message": "Job could not be cancelled (may have already finished)"
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Cancellation failed: {str(e)}")


@router.post("/generate-enhanced", response_model=JobStatusResponse)
async def create_enhanced_generation_job(
    request: GenerationRequest,
    sentiment_intensity: int = Query(
        default=None,
        ge=1,
        le=5,
        description="Sentiment intensity scale 1-5 (1=Very Negative, 5=Very Positive)"
    ),
    tone: str = Query(
        default=None,
        description="Desired tone (frustrated, polite, urgent, professional, etc.)"
    ),
    enable_few_shot: bool = Query(
        default=True,
        description="Enable few-shot learning with examples"
    ),
    enable_quality_filter: bool = Query(
        default=True,
        description="Enable quality filtering and deduplication"
    ),
    min_quality_score: float = Query(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Minimum quality score threshold for filtering"
    )
) -> JobStatusResponse:
    """
    Create an enhanced generation job with few-shot learning and quality filtering.
    
    Features:
    - Few-shot learning with domain-specific examples
    - Sentiment intensity control (1-5 scale)
    - Tone specification for consistent output
    - Quality filtering with deduplication
    - Enhanced prompt engineering
    
    Args:
        request: Generation parameters
        sentiment_intensity: Sentiment scale 1-5
        tone: Desired tone for generation
        enable_few_shot: Whether to include few-shot examples
        enable_quality_filter: Whether to apply quality filtering
        min_quality_score: Minimum quality threshold
        
    Returns:
        Job status response with job ID
    """
    try:
        logger.info(f"Creating enhanced generation job for product: {request.product}")
        
        # Validate request
        generation_service = get_generation_service()
        validation = await generation_service.validate_generation_request(request)
        
        if not validation["valid"]:
            error_message = "; ".join(validation["errors"])
            raise HTTPException(status_code=400, detail=f"Invalid request: {error_message}")
        
        # Create enhanced generation job with parameters
        job_store = get_job_store()
        job_id = job_store.create_enhanced_generation_job(
            request=request,
            sentiment_intensity=sentiment_intensity,
            tone=tone,
            enable_few_shot=enable_few_shot,
            enable_quality_filter=enable_quality_filter,
            min_quality_score=min_quality_score
        )
        
        # Return job status
        job_status = job_store.get_status(job_id)
        if not job_status:
            raise HTTPException(status_code=500, detail="Failed to create enhanced job")
        
        logger.info(f"Created enhanced generation job {job_id}")
        return job_status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create enhanced generation job: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/generate-augmented", response_model=JobStatusResponse)
async def create_augmented_generation_job(
    request: GenerationRequest,
    augmentation_strategies: List[str] = Query(
        default=["CDA"], 
        description="Augmentation strategies to apply: CDA, ADA, CADA"
    ),
    augment_ratio: float = Query(
        default=0.5, 
        ge=0.0, 
        le=1.0,
        description="Ratio of augmented to original samples"
    )
) -> JobStatusResponse:
    """
    Create a generation job with data augmentation.
    
    Uses advanced data augmentation strategies based on expert research:
    - CDA: Context-Focused Data Augmentation (paraphrasing)
    - ADA: Aspect-Focused Data Augmentation (aspect term replacement) 
    - CADA: Context-Aspect Data Augmentation (combined approach)
    
    Args:
        request: Generation parameters
        background_tasks: FastAPI background tasks
        augmentation_strategies: List of augmentation strategies to apply
        augment_ratio: Ratio of augmented to original samples (0.0-1.0)
        
    Returns:
        Job status response with job ID
    """
    try:
        logger.info(f"Creating augmented generation job for product: {request.product}")
        
        # Validate request
        generation_service = get_generation_service()
        validation = await generation_service.validate_generation_request(request)
        
        if not validation["valid"]:
            error_message = "; ".join(validation["errors"])
            raise HTTPException(status_code=400, detail=f"Invalid request: {error_message}")
        
        # Validate augmentation strategies
        valid_strategies = {"CDA", "ADA", "CADA"}
        invalid_strategies = set(augmentation_strategies) - valid_strategies
        if invalid_strategies:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid augmentation strategies: {invalid_strategies}. "
                      f"Valid options: {valid_strategies}"
            )
        
        # Create job via JobStore
        job_store = get_job_store()
        job_id = job_store.create_augmented_generation_job(
            request,
            augmentation_strategies,
            augment_ratio
        )
        
        # Return job status
        job_status = job_store.get_status(job_id)
        if not job_status:
            raise HTTPException(status_code=500, detail="Failed to create job")
        
        logger.info(f"Created Celery augmented generation job {job_id} with strategies: {augmentation_strategies}")
        return job_status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create augmented generation job: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/augmentation/strategies")
async def get_augmentation_strategies():
    """
    Get information about available data augmentation strategies.
    
    Returns:
        Dictionary with strategy information and capabilities
    """
    try:
        from app.services.data_augmentation_service import get_augmentation_service
        
        augmentation_service = get_augmentation_service()
        strategy_info = augmentation_service.get_strategy_info()
        
        return {
            "strategies": strategy_info,
            "available": list(strategy_info.keys()),
            "recommended_combinations": [
                ["CDA"],
                ["ADA"], 
                ["CADA"],
                ["CDA", "ADA"]
            ],
            "usage_notes": {
                "CDA": "Best for increasing semantic diversity while preserving meaning",
                "ADA": "Best for improving robustness to different aspect terms",
                "CADA": "Best overall performance but computationally intensive"
            }
        }
        
    except ImportError:
        return {
            "error": "Data augmentation service not available",
            "strategies": {},
            "available": []
        }
    except Exception as e:
        logger.error(f"Failed to get augmentation strategies: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# Note: run_augmented_generation_job function removed - now handled by Celery tasks


@router.get("/rate-limit-status")
async def get_rate_limit_status() -> Dict[str, Any]:
    """
    Get current rate limiting status and usage statistics.
    
    Returns comprehensive information about:
    - Current usage vs limits for requests and tokens
    - Rate limiting metrics and performance
    - Concurrent request usage
    - Historical usage patterns
    """
    try:
        rate_limit_manager = get_rate_limit_manager()
        usage_stats = rate_limit_manager.get_current_usage()
        
        # Add additional metadata
        response = {
            "status": "active",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rate_limiting": {
                "enabled": True,
                "requests": {
                    "current_usage": usage_stats["requests_last_minute"],
                    "limit": usage_stats["requests_per_minute_limit"],
                    "usage_percentage": usage_stats["request_usage_percentage"],
                    "remaining": max(0, usage_stats["requests_per_minute_limit"] - usage_stats["requests_last_minute"])
                },
                "tokens": {
                    "current_usage": usage_stats["tokens_last_minute"],
                    "limit": usage_stats["tokens_per_minute_limit"],
                    "usage_percentage": usage_stats["token_usage_percentage"],
                    "remaining": max(0, usage_stats["tokens_per_minute_limit"] - usage_stats["tokens_last_minute"])
                },
                "concurrent_requests": {
                    "active": usage_stats["concurrent_requests"],
                    "limit": rate_limit_manager.max_concurrent_requests
                }
            },
            "metrics": {
                "total_requests": usage_stats["metrics"].total_requests,
                "successful_requests": usage_stats["metrics"].successful_requests,
                "rate_limited_requests": usage_stats["metrics"].rate_limited_requests,
                "retried_requests": usage_stats["metrics"].retried_requests,
                "average_response_time": round(usage_stats["metrics"].average_response_time, 3),
                "success_rate": (
                    usage_stats["metrics"].successful_requests / usage_stats["metrics"].total_requests * 100
                    if usage_stats["metrics"].total_requests > 0 else 0.0
                )
            }
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Failed to get rate limit status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve rate limit status: {str(e)}"
        )


@router.get("/config")
async def get_generation_config() -> Dict[str, Any]:
    """
    Get current generation configuration and capabilities.
    
    Returns:
        Available features, templates, and configuration options
    """
    try:
        from app.services.prompt_service import get_template_service
        from app.services.data_augmentation_service import get_augmentation_service
        
        template_service = get_template_service()
        augmentation_service = get_augmentation_service()
        settings = get_settings()
        
        config = {
            "features": {
                "few_shot_learning": True,
                "quality_filtering": True,
                "data_augmentation": True,
                "sentiment_intensity_control": True,
                "tone_control": True,
                "rate_limiting": True
            },
            "templates": {
                "available": template_service.list_templates(),
                "default": settings.default_prompt_template
            },
            "sentiment_intensity": {
                "scale": "1-5",
                "descriptions": {
                    1: "Very Negative - Highly dissatisfied, angry, or frustrated",
                    2: "Negative - Dissatisfied or disappointed",
                    3: "Neutral - Balanced or indifferent", 
                    4: "Positive - Satisfied or pleased",
                    5: "Very Positive - Extremely satisfied, delighted, or enthusiastic"
                }
            },
            "tone_options": [
                "frustrated", "polite", "urgent", "professional", "casual",
                "formal", "friendly", "concerned", "enthusiastic", "neutral"
            ],
            "augmentation_strategies": augmentation_service.get_strategy_info(),
            "quality_filtering": {
                "default_min_score": 0.6,
                "metrics": ["overall_score", "coherence_score", "relevance_score", "uniqueness_score"],
                "deduplication": True
            },
            "limits": {
                "max_samples": getattr(settings, 'max_samples_per_request', 100),
                "min_samples": 1,
                "max_tokens": settings.openai_max_tokens
            }
        }
        
        return config
        
    except Exception as e:
        logger.error(f"Failed to get generation config: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/quality-stats")
async def get_quality_filter_stats() -> Dict[str, Any]:
    """
    Get quality filtering statistics and performance metrics.
    
    Returns:
        Quality filtering performance and statistics
    """
    try:
        from app.services.quality_service import get_quality_service
        
        quality_service = get_quality_service()
        stats = quality_service.get_filter_stats()
        
        return {
            "filter_stats": stats,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get quality stats: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# Error handling is managed by the global exception handler in main.py