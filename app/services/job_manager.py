"""
Redis-based job management service for background task orchestration.
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import redis.asyncio as redis
from app.config import get_settings
from app.models.schemas import GenerationRequest, JobStatusResponse, GenerationResponse

logger = logging.getLogger(__name__)

# In-memory fallback storage when Redis is unavailable
_memory_jobs: Dict[str, Dict[str, Any]] = {}
_memory_results: Dict[str, GenerationResponse] = {}


class JobManager:
    """Redis-based job manager for handling background generation tasks."""
    
    def __init__(self, redis_url: str = None):
        """
        Initialize job manager.
        
        Args:
            redis_url: Redis connection URL
        """
        settings = get_settings()
        self.redis_url = redis_url or settings.redis_url
        self.job_expire_seconds = settings.redis_job_expire_seconds
        self.result_expire_seconds = settings.redis_result_expire_seconds
        self.max_concurrent_jobs = settings.max_concurrent_jobs
        self.job_timeout_seconds = settings.job_timeout_seconds
        
        # Redis client (will be initialized async)
        self.redis_client: Optional[redis.Redis] = None
        
        # Job key prefixes
        self.job_prefix = "dataforge:job:"
        self.result_prefix = "dataforge:result:"
        self.active_jobs_key = "dataforge:active_jobs"
        self.job_counter_key = "dataforge:job_counter"
    
    async def initialize(self) -> None:
        """Initialize Redis connection."""
        try:
            self.redis_client = redis.from_url(
                self.redis_url, 
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # Test connection
            await self.redis_client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            logger.warning("Job persistence will be disabled - jobs will only exist in memory")
            self.redis_client = None  # Set to None to indicate failure
    
    async def close(self) -> None:
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Redis connection closed")
    
    async def health_check(self) -> bool:
        """Check Redis connection health."""
        try:
            if not self.redis_client:
                return False
            await self.redis_client.ping()
            return True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False
    
    def _job_key(self, job_id: str) -> str:
        """Get Redis key for job data."""
        return f"{self.job_prefix}{job_id}"
    
    def _result_key(self, job_id: str) -> str:
        """Get Redis key for job results."""
        return f"{self.result_prefix}{job_id}"
    
    async def create_job(self, request: GenerationRequest) -> str:
        """
        Create a new generation job.
        
        Args:
            request: Generation request parameters
            
        Returns:
            Job ID string
            
        Raises:
            Exception: If job creation fails or too many active jobs
        """
        # Check active job limit
        if self.redis_client:
            active_count = await self.redis_client.scard(self.active_jobs_key)
        else:
            # Use in-memory fallback
            active_count = len([j for j in _memory_jobs.values() if j.get('status') in ['pending', 'running']])
        
        if active_count >= self.max_concurrent_jobs:
            raise Exception(f"Too many active jobs ({active_count}). Maximum: {self.max_concurrent_jobs}")
        
        # Generate unique job ID
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        # Job data
        job_data = {
            "job_id": job_id,
            "status": "pending",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "request": request.dict(),
            "progress": 0,
            "error_message": None,
            "worker_id": None
        }
        
        try:
            if self.redis_client:
                # Store job data in Redis
                job_key = self._job_key(job_id)
                await self.redis_client.hset(job_key, mapping={
                    k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                    for k, v in job_data.items()
                })
                await self.redis_client.expire(job_key, self.job_expire_seconds)
                
                # Add to active jobs set
                await self.redis_client.sadd(self.active_jobs_key, job_id)
                
                # Increment job counter
                await self.redis_client.incr(self.job_counter_key)
            else:
                # Store job data in memory
                _memory_jobs[job_id] = job_data
                logger.warning(f"Job {job_id} stored in memory - will not persist across restarts")
            
            logger.info(f"Created job {job_id}")
            return job_id
            
        except Exception as e:
            logger.error(f"Failed to create job: {e}")
            # Cleanup on failure
            await self._cleanup_job(job_id)
            raise
    
    async def get_job_status(self, job_id: str) -> Optional[JobStatusResponse]:
        """
        Get job status and results.
        
        Args:
            job_id: Job identifier
            
        Returns:
            Job status response or None if not found
        """
        try:
            job_data = None
            
            if self.redis_client:
                job_key = self._job_key(job_id)
                job_data = await self.redis_client.hgetall(job_key)
                # Convert Redis strings back to proper types
                if job_data:
                    for key, value in job_data.items():
                        if key == "request":
                            job_data[key] = json.loads(value)
                        elif key in ["progress"]:
                            job_data[key] = int(value)
            else:
                # Use in-memory storage
                job_data = _memory_jobs.get(job_id)
            
            if not job_data:
                return None
            
            # Parse job data
            status = job_data.get("status", "unknown")
            created_at = datetime.fromisoformat(job_data.get("created_at"))
            updated_at = datetime.fromisoformat(job_data.get("updated_at"))
            error_message = job_data.get("error_message")
            progress = int(job_data.get("progress", 0))
            
            # Get results if completed
            result = None
            if status == "completed":
                if self.redis_client:
                    result_key = self._result_key(job_id)
                    result_data = await self.redis_client.get(result_key)
                    if result_data:
                        result = GenerationResponse(**json.loads(result_data))
                else:
                    # Use in-memory storage
                    result = _memory_results.get(job_id)
            
            return JobStatusResponse(
                job_id=job_id,
                status=status,
                created_at=created_at,
                updated_at=updated_at,
                error_message=error_message,
                result=result,
                progress=progress if progress > 0 else None
            )
            
        except Exception as e:
            logger.error(f"Failed to get job status for {job_id}: {e}")
            return None
    
    async def update_job_status(
        self, 
        job_id: str, 
        status: str,
        progress: Optional[int] = None,
        error_message: Optional[str] = None,
        worker_id: Optional[str] = None
    ) -> bool:
        """
        Update job status.
        
        Args:
            job_id: Job identifier
            status: New status
            progress: Progress percentage (0-100)
            error_message: Error message if status is 'error'
            worker_id: Worker identifier
            
        Returns:
            True if update successful
        """
        try:
            now = datetime.now(timezone.utc)
            
            updates = {
                "status": status,
                "updated_at": now.isoformat()
            }
            
            if progress is not None:
                updates["progress"] = progress
            if error_message is not None:
                updates["error_message"] = error_message
            if worker_id is not None:
                updates["worker_id"] = worker_id
            
            if self.redis_client:
                # Update job data in Redis
                job_key = self._job_key(job_id)
                redis_updates = {
                    k: str(v) for k, v in updates.items()
                }
                await self.redis_client.hset(job_key, mapping=redis_updates)
                
                # Remove from active jobs if completed or errored
                if status in ["completed", "error"]:
                    await self.redis_client.srem(self.active_jobs_key, job_id)
            else:
                # Update job data in memory
                if job_id in _memory_jobs:
                    _memory_jobs[job_id].update(updates)
            
            logger.info(f"Updated job {job_id} status to {status}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update job {job_id}: {e}")
            return False
    
    async def store_job_result(self, job_id: str, result: GenerationResponse) -> bool:
        """
        Store job results.
        
        Args:
            job_id: Job identifier
            result: Generation results
            
        Returns:
            True if storage successful
        """
        try:
            if self.redis_client:
                result_key = self._result_key(job_id)
                result_json = result.json()
                
                await self.redis_client.set(
                    result_key, 
                    result_json, 
                    ex=self.result_expire_seconds
                )
            else:
                # Store in memory
                _memory_results[job_id] = result
            
            logger.info(f"Stored results for job {job_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store results for job {job_id}: {e}")
            return False
    
    async def cleanup_expired_jobs(self) -> int:
        """
        Cleanup expired jobs from active set.
        
        Returns:
            Number of jobs cleaned up
        """
        if not self.redis_client:
            return 0
        
        try:
            active_jobs = await self.redis_client.smembers(self.active_jobs_key)
            cleaned = 0
            
            for job_id in active_jobs:
                job_key = self._job_key(job_id)
                exists = await self.redis_client.exists(job_key)
                
                if not exists:
                    await self.redis_client.srem(self.active_jobs_key, job_id)
                    cleaned += 1
            
            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} expired jobs")
            
            return cleaned
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired jobs: {e}")
            return 0
    
    async def get_job_stats(self) -> Dict[str, Any]:
        """
        Get job statistics.
        
        Returns:
            Job statistics dictionary
        """
        if not self.redis_client:
            return {}
        
        try:
            active_count = await self.redis_client.scard(self.active_jobs_key)
            total_count = await self.redis_client.get(self.job_counter_key) or 0
            
            return {
                "active_jobs": active_count,
                "total_jobs_created": int(total_count),
                "max_concurrent_jobs": self.max_concurrent_jobs
            }
            
        except Exception as e:
            logger.error(f"Failed to get job stats: {e}")
            return {}
    
    async def _cleanup_job(self, job_id: str) -> None:
        """Cleanup job data on failure."""
        if not self.redis_client:
            return
        
        try:
            job_key = self._job_key(job_id)
            result_key = self._result_key(job_id)
            
            await self.redis_client.delete(job_key, result_key)
            await self.redis_client.srem(self.active_jobs_key, job_id)
            
        except Exception as e:
            logger.error(f"Failed to cleanup job {job_id}: {e}")


# Global job manager instance
_job_manager: Optional[JobManager] = None


async def get_job_manager() -> JobManager:
    """Get global job manager instance."""
    global _job_manager
    if _job_manager is None:
        _job_manager = JobManager()
        await _job_manager.initialize()
    return _job_manager


async def cleanup_job_manager() -> None:
    """Cleanup global job manager."""
    global _job_manager
    if _job_manager:
        await _job_manager.close()
        _job_manager = None