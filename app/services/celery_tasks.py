"""
Celery tasks for DataForge background processing.

This module contains all Celery tasks that replace the Redis-based JobManager
for better scalability, reliability, and monitoring.
"""
import asyncio
import logging
import traceback
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from celery import current_task
from celery.exceptions import Retry

from app.celery_app import celery_app
from app.config import get_settings
from app.models.schemas import GenerationRequest, GenerationResponse, GeneratedSample
# Avoid circular import: import GenerationService lazily inside task functions
from app.utils.llm_client import get_llm_client, LLMException

logger = logging.getLogger(__name__)


def run_async_in_sync(coro):
    """Helper to run async functions in sync Celery tasks."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        return loop.run_until_complete(coro)
    finally:
        # Don't close the loop as it might be reused
        pass


@celery_app.task(
    bind=True, 
    name='run_generation_task',
    autoretry_for=(LLMException, ConnectionError),
    retry_kwargs={'max_retries': 3, 'countdown': 60},
    soft_time_limit=300,  # 5 minutes soft limit
    time_limit=600  # 10 minutes hard limit
)
def run_generation_task(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Celery task for text generation.
    
    Args:
        request_data: Serialized GenerationRequest data
        
    Returns:
        Dictionary containing task results
        
    Raises:
        Retry: If task should be retried
        Exception: If task fails permanently
    """
    try:
        logger.info(f"Starting generation task {self.request.id}")
        
        # Update task state to PROGRESS
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 0, 
                'total': request_data['count'], 
                'status': 'Initializing generation...',
                'started_at': datetime.now(timezone.utc).isoformat()
            }
        )
        
        # Convert dict back to Pydantic model
        request = GenerationRequest(**request_data)
        
        # Create generation service (lazy import to avoid circular import)
        from app.services.generation_service import GenerationService
        service = GenerationService()
        
        # Progress callback for Celery state updates
        def progress_callback(progress: int):
            """Update Celery task progress."""
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': progress,
                    'total': 100,
                    'status': f'Generating samples... {progress}%',
                    'started_at': datetime.now(timezone.utc).isoformat()
                }
            )
        
        # Run the async generation logic in sync context
        async def run_generation():
            return await service.generate_batch(request, progress_callback)
        
        # Execute the generation
        result = run_async_in_sync(run_generation())
        
        # Update final state
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 100,
                'total': 100,
                'status': 'Generation completed successfully',
                'started_at': datetime.now(timezone.utc).isoformat(),
                'completed_at': datetime.now(timezone.utc).isoformat()
            }
        )
        
        logger.info(
            f"Generation task {self.request.id} completed: "
            f"{result.total_samples} samples, ~{result.total_tokens_estimated} tokens"
        )
        
        return {
            'status': 'SUCCESS',
            'result': result.model_dump(),
            'task_id': self.request.id,
            'completed_at': datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as exc:
        logger.error(f"Generation task {self.request.id} failed: {exc}")
        logger.error(traceback.format_exc())
        
        # Update state with error information
        self.update_state(
            state='FAILURE',
            meta={
                'error': str(exc),
                'error_type': type(exc).__name__,
                'failed_at': datetime.now(timezone.utc).isoformat(),
                'traceback': traceback.format_exc()
            }
        )
        
        # Re-raise for Celery to handle
        raise exc


@celery_app.task(
    bind=True,
    name='run_enhanced_generation_task',
    autoretry_for=(LLMException, ConnectionError),
    retry_kwargs={'max_retries': 3, 'countdown': 60},
    soft_time_limit=300,  # 5 minutes soft limit
    time_limit=600  # 10 minutes hard limit
)
def run_enhanced_generation_task(self, enhanced_params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Celery task for enhanced text generation with few-shot learning and quality filtering.
    
    Args:
        enhanced_params: Dictionary containing:
            - request: Generation request parameters
            - sentiment_intensity: Sentiment scale 1-5
            - tone: Desired tone
            - enable_few_shot: Whether to use few-shot learning
            - enable_quality_filter: Whether to apply quality filtering
            - min_quality_score: Minimum quality threshold
    
    Returns:
        Task result dictionary with generation response
    """
    try:
        logger.info(f"Starting enhanced generation task {self.request.id}")
        
        # Extract parameters
        request_data = enhanced_params['request']
        request = GenerationRequest(**request_data)
        
        sentiment_intensity = enhanced_params.get('sentiment_intensity')
        tone = enhanced_params.get('tone')
        enable_few_shot = enhanced_params.get('enable_few_shot', True)
        enable_quality_filter = enhanced_params.get('enable_quality_filter', True)
        min_quality_score = enhanced_params.get('min_quality_score', 0.6)
        
        # Update quality filter config if specified
        if enable_quality_filter:
            from app.services.quality_service import QualityFilterConfig, get_quality_service
            quality_config = QualityFilterConfig(min_overall_score=min_quality_score)
            # Reset service to use new config
            from app.services.quality_service import reset_quality_service
            reset_quality_service()
            get_quality_service(quality_config)
        
        # Initialize generation service (lazy import to avoid circular import)
        from app.services.generation_service import GenerationService
        service = GenerationService()
        
        # Progress callback for updates
        async def progress_callback(progress: int):
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': progress,
                    'total': 100,
                    'status': f'Enhanced generation... {progress}%',
                    'started_at': datetime.now(timezone.utc).isoformat(),
                    'features': {
                        'few_shot_learning': enable_few_shot,
                        'quality_filtering': enable_quality_filter,
                        'sentiment_intensity': sentiment_intensity,
                        'tone': tone
                    }
                }
            )
        
        # Run the enhanced generation logic
        async def run_enhanced_generation():
            return await service.generate_batch(
                request=request,
                progress_callback=progress_callback,
                enable_quality_filter=enable_quality_filter,
                sentiment_intensity=sentiment_intensity,
                tone=tone,
                enable_few_shot=enable_few_shot
            )
        
        # Execute the enhanced generation
        result = run_async_in_sync(run_enhanced_generation())
        
        # Update final state with enhanced metadata
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 100,
                'total': 100,
                'status': 'Enhanced generation completed successfully',
                'started_at': datetime.now(timezone.utc).isoformat(),
                'completed_at': datetime.now(timezone.utc).isoformat(),
                'features_used': {
                    'few_shot_learning': enable_few_shot,
                    'quality_filtering': enable_quality_filter,
                    'sentiment_intensity': sentiment_intensity,
                    'tone': tone
                },
                'quality_info': result.metadata if hasattr(result, 'metadata') and result.metadata else {}
            }
        )
        
        logger.info(
            f"Enhanced generation task {self.request.id} completed: "
            f"{result.total_samples} samples, ~{result.total_tokens_estimated} tokens, "
            f"quality_filter={enable_quality_filter}, few_shot={enable_few_shot}"
        )
        
        return {
            'status': 'SUCCESS',
            'result': result.model_dump(),
            'task_id': self.request.id,
            'completed_at': datetime.now(timezone.utc).isoformat(),
            'enhancement_features': {
                'few_shot_learning': enable_few_shot,
                'quality_filtering': enable_quality_filter,
                'sentiment_intensity': sentiment_intensity,
                'tone': tone,
                'min_quality_score': min_quality_score
            }
        }
        
    except Exception as exc:
        logger.error(f"Enhanced generation task {self.request.id} failed: {exc}")
        logger.error(traceback.format_exc())
        
        # Update state with error information
        self.update_state(
            state='FAILURE',
            meta={
                'error': str(exc),
                'error_type': type(exc).__name__,
                'failed_at': datetime.now(timezone.utc).isoformat(),
                'traceback': traceback.format_exc(),
                'enhancement_features': enhanced_params
            }
        )
        
        # Re-raise for Celery to handle
        raise exc


@celery_app.task(
    bind=True,
    name='run_augmented_generation_task', 
    autoretry_for=(LLMException, ConnectionError),
    retry_kwargs={'max_retries': 3, 'countdown': 60},
    soft_time_limit=600,  # 10 minutes soft limit
    time_limit=1200  # 20 minutes hard limit (augmentation takes longer)
)
def run_augmented_generation_task(
    self, 
    request_data: Dict[str, Any],
    augmentation_strategies: List[str],
    augment_ratio: float
) -> Dict[str, Any]:
    """
    Celery task for augmented text generation.
    
    Args:
        request_data: Serialized GenerationRequest data
        augmentation_strategies: List of strategies to apply ('CDA', 'ADA', 'CADA')
        augment_ratio: Ratio of augmented to original samples (0.0 to 1.0)
        
    Returns:
        Dictionary containing task results
    """
    try:
        logger.info(
            f"Starting augmented generation task {self.request.id} "
            f"with strategies: {augmentation_strategies}"
        )
        
        # Update task state
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 0,
                'total': 100,
                'status': 'Initializing augmented generation...',
                'strategies': augmentation_strategies,
                'augment_ratio': augment_ratio,
                'started_at': datetime.now(timezone.utc).isoformat()
            }
        )
        
        # Convert dict back to Pydantic model
        request = GenerationRequest(**request_data)
        
        # Create generation service (lazy import to avoid circular import)
        from app.services.generation_service import GenerationService
        service = GenerationService()
        
        # Progress callback
        def progress_callback(progress: int):
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': progress,
                    'total': 100,
                    'status': f'Running augmented generation... {progress}%',
                    'strategies': augmentation_strategies,
                    'augment_ratio': augment_ratio,
                    'started_at': datetime.now(timezone.utc).isoformat()
                }
            )
        
        # Run the async augmented generation
        async def run_augmented_generation():
            return await service.generate_with_augmentation(
                request=request,
                augmentation_strategies=augmentation_strategies,
                augment_ratio=augment_ratio
            )
        
        # Execute the generation
        result = run_async_in_sync(run_augmented_generation())
        
        logger.info(
            f"Augmented generation task {self.request.id} completed: "
            f"{result.total_samples} total samples"
        )
        
        return {
            'status': 'SUCCESS',
            'result': result.model_dump(),
            'task_id': self.request.id,
            'strategies_used': augmentation_strategies,
            'augment_ratio': augment_ratio,
            'completed_at': datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as exc:
        logger.error(f"Augmented generation task {self.request.id} failed: {exc}")
        logger.error(traceback.format_exc())
        
        self.update_state(
            state='FAILURE',
            meta={
                'error': str(exc),
                'error_type': type(exc).__name__,
                'failed_at': datetime.now(timezone.utc).isoformat(),
                'traceback': traceback.format_exc()
            }
        )
        
        raise exc


@celery_app.task(name='cleanup_expired_results')
def cleanup_expired_results() -> Dict[str, Any]:
    """
    Periodic maintenance task to cleanup expired results.
    
    This task runs periodically to clean up old task results
    and maintain system performance.
    
    Returns:
        Cleanup statistics
    """
    try:
        logger.info("Starting cleanup of expired results")
        
        # Get settings for cleanup configuration
        settings = get_settings()
        
        # This is a placeholder for actual cleanup logic
        # In a real implementation, you might:
        # 1. Query the result backend for old results
        # 2. Remove results older than a certain threshold
        # 3. Clean up any temporary files or data
        
        cleanup_count = 0  # Placeholder
        
        logger.info(f"Cleanup completed: {cleanup_count} items removed")
        
        return {
            'status': 'SUCCESS',
            'cleaned_items': cleanup_count,
            'cleaned_at': datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as exc:
        logger.error(f"Cleanup task failed: {exc}")
        return {
            'status': 'ERROR',
            'error': str(exc),
            'failed_at': datetime.now(timezone.utc).isoformat()
        }


@celery_app.task(name='validate_generation_request')
def validate_generation_request(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Task to validate generation requests asynchronously.
    
    This can be useful for pre-validation of large requests
    before queueing the actual generation task.
    
    Args:
        request_data: Serialized GenerationRequest data
        
    Returns:
        Validation results
    """
    try:
        request = GenerationRequest(**request_data)
        from app.services.generation_service import GenerationService
        service = GenerationService()
        
        # Run async validation
        async def run_validation():
            return await service.validate_generation_request(request)
        
        validation_result = run_async_in_sync(run_validation())
        
        return {
            'status': 'SUCCESS',
            'validation': validation_result,
            'validated_at': datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as exc:
        logger.error(f"Validation task failed: {exc}")
        return {
            'status': 'ERROR',
            'error': str(exc),
            'failed_at': datetime.now(timezone.utc).isoformat()
        }


# Health check task (already defined in celery_app.py but we can extend it here)
@celery_app.task(name='worker_health_check')
def worker_health_check() -> Dict[str, Any]:
    """
    Comprehensive health check for worker nodes.
    
    Returns:
        Health status including system information
    """
    try:
        # Check LLM client availability
        async def check_llm():
            llm_client = get_llm_client()
            return await llm_client.health_check()
        
        llm_healthy = run_async_in_sync(check_llm())
        
        return {
            'status': 'healthy',
            'llm_available': llm_healthy,
            'checked_at': datetime.now(timezone.utc).isoformat(),
            'worker_id': current_task.request.hostname if current_task else 'unknown'
        }
        
    except Exception as exc:
        return {
            'status': 'unhealthy',
            'error': str(exc),
            'checked_at': datetime.now(timezone.utc).isoformat()
        }