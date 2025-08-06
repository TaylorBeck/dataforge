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
from app.services.job_manager import get_job_manager
from app.services.generation_service import get_generation_service, run_generation_job
from app.services.rate_limiting_service import get_rate_limit_manager
from app.utils.llm_client import get_llm_client, test_llm_client
from app.config import get_settings
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Create router instance
router = APIRouter(prefix="/api", tags=["generation"])


@router.post("/generate", response_model=JobStatusResponse)
async def create_generation_job(
    request: GenerationRequest,
    background_tasks: BackgroundTasks
) -> JobStatusResponse:
    """
    Create a new text generation job.
    
    This endpoint accepts a generation request and returns a job ID immediately.
    The actual generation happens in the background.
    
    Args:
        request: Generation parameters including product, count, and version
        background_tasks: FastAPI background tasks for async processing
        
    Returns:
        Job status response with job ID and initial status
        
    Raises:
        HTTPException: On validation errors or system unavailability
    """
    try:
        logger.info(f"Creating generation job for product: {request.product}")
        
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
        
        # Create job
        job_manager = await get_job_manager()
        job_id = await job_manager.create_job(request)
        
        # Start background generation task
        background_tasks.add_task(run_generation_job, request, job_id)
        
        # Return job status
        job_status = await job_manager.get_job_status(job_id)
        if not job_status:
            raise HTTPException(status_code=500, detail="Failed to create job")
        
        logger.info(f"Created generation job {job_id}")
        return job_status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create generation job: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/result/{job_id}", response_model=JobStatusResponse)
async def get_job_result(job_id: str) -> JobStatusResponse:
    """
    Get job status and results.
    
    Args:
        job_id: Unique job identifier
        
    Returns:
        Job status with results if completed
        
    Raises:
        HTTPException: If job not found
    """
    try:
        job_manager = await get_job_manager()
        job_status = await job_manager.get_job_status(job_id)
        
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
        
        # Check Redis connection
        redis_connected = False
        try:
            job_manager = await get_job_manager()
            redis_connected = await job_manager.health_check()
        except Exception as e:
            logger.warning(f"Redis health check failed: {e}")
        
        # Determine overall health
        status = "healthy" if redis_connected else "unhealthy"
        
        return HealthCheckResponse(
            status=status,
            timestamp=datetime.now(timezone.utc),
            redis_connected=redis_connected,
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


@router.get("/stats")
async def get_system_stats() -> Dict[str, Any]:
    """
    Get system statistics.
    
    Returns:
        Dictionary with system statistics
    """
    try:
        job_manager = await get_job_manager()
        generation_service = get_generation_service()
        settings = get_settings()
        
        # Get job statistics
        job_stats = await job_manager.get_job_stats()
        
        # Get LLM client info
        llm_client = get_llm_client()
        llm_info = await llm_client.get_model_info()
        
        return {
            "service": {
                "name": settings.api_title,
                "version": settings.api_version,
                "debug": settings.debug
            },
            "jobs": job_stats,
            "llm": llm_info,
            "limits": {
                "max_samples_per_request": settings.max_samples_per_request,
                "max_concurrent_jobs": settings.max_concurrent_jobs,
                "job_timeout_seconds": settings.job_timeout_seconds
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get system stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve system statistics")


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
            "request": request.dict(),
            "validation": validation
        }
        
    except Exception as e:
        logger.error(f"Request validation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


@router.delete("/job/{job_id}")
async def cancel_job(job_id: str) -> Dict[str, str]:
    """
    Cancel a running job (best effort).
    
    Note: This is a best-effort cancellation. Jobs that are already 
    generating may complete before cancellation takes effect.
    
    Args:
        job_id: Job identifier to cancel
        
    Returns:
        Cancellation status
    """
    try:
        job_manager = await get_job_manager()
        
        # Check if job exists
        job_status = await job_manager.get_job_status(job_id)
        if not job_status:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        
        # Only cancel pending or running jobs
        if job_status.status in ["completed", "error"]:
            return {
                "job_id": job_id,
                "status": "already_finished",
                "message": f"Job is already {job_status.status}"
            }
        
        # Update job status to error (cancellation)
        success = await job_manager.update_job_status(
            job_id=job_id,
            status="error",
            error_message="Job cancelled by user"
        )
        
        if success:
            logger.info(f"Cancelled job {job_id}")
            return {
                "job_id": job_id,
                "status": "cancelled",
                "message": "Job cancellation requested"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to cancel job")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Cancellation failed: {str(e)}")


@router.post("/generate-augmented", response_model=JobStatusResponse)
async def create_augmented_generation_job(
    request: GenerationRequest,
    background_tasks: BackgroundTasks,
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
        
        # Create job
        job_manager = await get_job_manager()
        job_id = await job_manager.create_job(request)
        
        # Start background augmented generation task
        background_tasks.add_task(
            run_augmented_generation_job, 
            request, 
            job_id, 
            augmentation_strategies,
            augment_ratio
        )
        
        # Return job status
        job_status = await job_manager.get_job_status(job_id)
        if not job_status:
            raise HTTPException(status_code=500, detail="Failed to create job")
        
        logger.info(f"Created augmented generation job {job_id} with strategies: {augmentation_strategies}")
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


async def run_augmented_generation_job(
    request: GenerationRequest, 
    job_id: str,
    augmentation_strategies: List[str],
    augment_ratio: float
) -> None:
    """
    Background task to run augmented generation job.
    
    Args:
        request: Generation request parameters
        job_id: Job identifier
        augmentation_strategies: List of augmentation strategies to apply
        augment_ratio: Ratio of augmented to original samples
    """
    service = get_generation_service()
    
    try:
        logger.info(f"Starting augmented generation job {job_id}")
        
        # Run generation with augmentation
        response = await service.generate_with_augmentation(
            request=request,
            augmentation_strategies=augmentation_strategies,
            augment_ratio=augment_ratio
        )
        
        # Update job with results
        job_manager = await get_job_manager()
        await job_manager.complete_job(job_id, response)
        
        logger.info(f"Augmented generation job {job_id} completed successfully")
        
    except Exception as e:
        logger.error(f"Augmented generation job {job_id} failed: {e}")
        
        # Update job with error
        job_manager = await get_job_manager()
        await job_manager.fail_job(job_id, str(e))


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


# Error handling is managed by the global exception handler in main.py