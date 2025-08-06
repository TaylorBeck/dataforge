"""
Service layer for Celery task management and status tracking.

This service provides an abstraction layer over Celery tasks, making it easier
to switch between different task queue implementations and providing a consistent
API for the rest of the application.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from celery.result import AsyncResult
from celery.exceptions import WorkerLostError, Retry

from app.celery_app import celery_app
from app.models.schemas import JobStatusResponse, GenerationResponse, GenerationRequest
from app.services.celery_tasks import run_generation_task, run_augmented_generation_task

logger = logging.getLogger(__name__)


class CeleryJobService:
    """Service for managing Celery-based background jobs."""
    
    def __init__(self):
        """Initialize the Celery job service."""
        self.celery_app = celery_app
    
    def create_generation_job(self, request: GenerationRequest) -> str:
        """
        Create a new generation job using Celery.
        
        Args:
            request: Generation request parameters
            
        Returns:
            Task ID (job ID) for tracking
        """
        try:
            logger.info(f"Creating Celery generation job for product: {request.product}")
            
            # Submit task to Celery
            task = run_generation_task.delay(request.dict())
            
            logger.info(f"Created Celery generation job {task.id}")
            return task.id
            
        except Exception as e:
            logger.error(f"Failed to create Celery generation job: {e}")
            raise
    
    def create_augmented_generation_job(
        self, 
        request: GenerationRequest,
        augmentation_strategies: List[str],
        augment_ratio: float
    ) -> str:
        """
        Create a new augmented generation job using Celery.
        
        Args:
            request: Generation request parameters
            augmentation_strategies: List of augmentation strategies to apply
            augment_ratio: Ratio of augmented to original samples
            
        Returns:
            Task ID (job ID) for tracking
        """
        try:
            logger.info(
                f"Creating Celery augmented generation job for product: {request.product} "
                f"with strategies: {augmentation_strategies}"
            )
            
            # Submit task to Celery
            task = run_augmented_generation_task.delay(
                request.dict(),
                augmentation_strategies,
                augment_ratio
            )
            
            logger.info(f"Created Celery augmented generation job {task.id}")
            return task.id
            
        except Exception as e:
            logger.error(f"Failed to create Celery augmented generation job: {e}")
            raise
    
    def get_job_status(self, job_id: str) -> Optional[JobStatusResponse]:
        """
        Get job status from Celery.
        
        Args:
            job_id: Task ID to check status for
            
        Returns:
            Job status response or None if not found
        """
        try:
            # Get task result from Celery
            task = self.celery_app.AsyncResult(job_id)
            
            # Map Celery states to our application states
            status_mapping = {
                'PENDING': 'pending',
                'STARTED': 'running',
                'PROGRESS': 'running', 
                'SUCCESS': 'completed',
                'FAILURE': 'error',
                'RETRY': 'running',
                'REVOKED': 'error'
            }
            
            status = status_mapping.get(task.state, 'unknown')
            
            # Create base response
            response = JobStatusResponse(
                job_id=job_id,
                status=status,
                created_at=datetime.now(timezone.utc),  # Celery doesn't provide creation time easily
                updated_at=datetime.now(timezone.utc)
            )
            
            # Add progress information if available
            if task.state == 'PROGRESS' and task.info:
                meta = task.info
                response.progress = meta.get('current', 0)
                
            # Add results if completed successfully
            elif task.state == 'SUCCESS' and task.result:
                result_data = task.result.get('result', {})
                if result_data:
                    response.result = GenerationResponse(**result_data)
                    
            # Add error information if failed
            elif task.state == 'FAILURE':
                if task.info:
                    if isinstance(task.info, dict):
                        response.error_message = task.info.get('error', str(task.info))
                    else:
                        response.error_message = str(task.info)
                else:
                    response.error_message = "Task failed with unknown error"
            
            return response
            
        except Exception as e:
            logger.error(f"Failed to get job status for {job_id}: {e}")
            return None
    
    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a running job.
        
        Args:
            job_id: Task ID to cancel
            
        Returns:
            True if cancellation was successful
        """
        try:
            task = self.celery_app.AsyncResult(job_id)
            
            # Only cancel if not already finished
            if task.state not in ['SUCCESS', 'FAILURE']:
                task.revoke(terminate=True)
                logger.info(f"Cancelled Celery job {job_id}")
                return True
            else:
                logger.warning(f"Cannot cancel job {job_id} - already finished with state {task.state}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to cancel job {job_id}: {e}")
            return False
    
    def get_job_stats(self) -> Dict[str, Any]:
        """
        Get statistics about active jobs and workers.
        
        Returns:
            Dictionary with job statistics
        """
        try:
            # Get active tasks from Celery
            inspect = self.celery_app.control.inspect()
            
            # Get active tasks across all workers
            active_tasks = inspect.active()
            scheduled_tasks = inspect.scheduled()
            reserved_tasks = inspect.reserved()
            
            # Count total tasks
            total_active = 0
            total_scheduled = 0
            total_reserved = 0
            
            if active_tasks:
                total_active = sum(len(tasks) for tasks in active_tasks.values())
            if scheduled_tasks:
                total_scheduled = sum(len(tasks) for tasks in scheduled_tasks.values())
            if reserved_tasks:
                total_reserved = sum(len(tasks) for tasks in reserved_tasks.values())
            
            # Get worker statistics
            stats = inspect.stats()
            active_workers = len(stats) if stats else 0
            
            return {
                "active_jobs": total_active,
                "scheduled_jobs": total_scheduled,
                "reserved_jobs": total_reserved,
                "total_pending_jobs": total_active + total_scheduled + total_reserved,
                "active_workers": active_workers,
                "worker_stats": stats
            }
            
        except Exception as e:
            logger.error(f"Failed to get job stats: {e}")
            return {
                "active_jobs": 0,
                "scheduled_jobs": 0,
                "reserved_jobs": 0,
                "total_pending_jobs": 0,
                "active_workers": 0,
                "error": str(e)
            }
    
    def health_check(self) -> bool:
        """
        Check if Celery workers are available and healthy.
        
        Returns:
            True if Celery is healthy
        """
        try:
            # Check if any workers are available
            inspect = self.celery_app.control.inspect()
            stats = inspect.stats()
            
            # Return True if at least one worker is active
            return stats is not None and len(stats) > 0
            
        except Exception as e:
            logger.error(f"Celery health check failed: {e}")
            return False


# Global service instance
_celery_job_service: Optional[CeleryJobService] = None


def get_celery_job_service() -> CeleryJobService:
    """Get global Celery job service instance."""
    global _celery_job_service
    if _celery_job_service is None:
        _celery_job_service = CeleryJobService()
    return _celery_job_service