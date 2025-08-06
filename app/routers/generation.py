"""
FastAPI routes for text generation endpoints.
"""
import asyncio
import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from app.models.schemas import (
    GenerationRequest, 
    JobStatusResponse, 
    HealthCheckResponse
)
from app.services.job_manager import get_job_manager
from app.services.generation_service import get_generation_service, run_generation_job
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


# Error handling is managed by the global exception handler in main.py