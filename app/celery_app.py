"""
Celery application configuration for DataForge background task processing.
"""
import os
from celery import Celery
from app.config import get_settings

# Get settings
settings = get_settings()

# Create Celery app
celery_app = Celery(
    "dataforge",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=['app.services.celery_tasks']
)

# Configure Celery
celery_app.conf.update(
    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    
    # Timezone
    timezone='UTC',
    enable_utc=True,
    
    # Task tracking
    task_track_started=True,
    task_track_progress=True,
    
    # Task routing - different queues for different workloads
    task_routes={
        'app.services.celery_tasks.run_generation_task': {'queue': 'generation'},
        'app.services.celery_tasks.run_augmented_generation_task': {'queue': 'augmentation'},
        'app.services.celery_tasks.cleanup_expired_results': {'queue': 'maintenance'},
    },
    
    # Worker configuration
    worker_prefetch_multiplier=1,  # One task at a time for better memory management
    task_acks_late=True,  # Acknowledge tasks only after completion
    worker_disable_rate_limits=False,
    worker_max_tasks_per_child=100,  # Restart worker after 100 tasks to prevent memory leaks
    
    # Result backend configuration
    result_expires=7200,  # Results expire after 2 hours
    result_persistent=True,  # Persist results across broker restarts
    
    # Retry configuration
    task_reject_on_worker_lost=True,
    task_default_retry_delay=60,  # 1 minute default retry delay
    task_max_retries=3,  # Maximum 3 retries
    
    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
    
    # Beat scheduler for periodic tasks
    beat_schedule={
        'cleanup-expired-results': {
            'task': 'app.services.celery_tasks.cleanup_expired_results',
            'schedule': 3600.0,  # Run every hour
            'options': {'queue': 'maintenance'}
        },
    },
)

# Optional: Configure different queues with priorities
celery_app.conf.task_default_queue = 'default'
celery_app.conf.task_queues = {
    'generation': {
        'exchange': 'generation',
        'exchange_type': 'direct',
        'routing_key': 'generation',
    },
    'augmentation': {
        'exchange': 'augmentation', 
        'exchange_type': 'direct',
        'routing_key': 'augmentation',
    },
    'maintenance': {
        'exchange': 'maintenance',
        'exchange_type': 'direct', 
        'routing_key': 'maintenance',
    }
}

# Health check task
@celery_app.task(name='health_check')
def health_check():
    """Simple health check task for monitoring."""
    return {'status': 'healthy', 'message': 'Celery worker is operational'}

if __name__ == '__main__':
    celery_app.start()