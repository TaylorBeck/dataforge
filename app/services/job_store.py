"""
Unified job store abstraction over Celery (and optionally legacy backends).
"""
from typing import Optional, Dict, Any
from app.models.schemas import JobStatusResponse, GenerationRequest
from app.services.celery_service import get_celery_job_service


class JobStore:
    """Abstraction for job status, cancellation, and stats."""

    def get_status(self, job_id: str) -> Optional[JobStatusResponse]:
        service = get_celery_job_service()
        return service.get_job_status(job_id)

    def cancel(self, job_id: str) -> bool:
        service = get_celery_job_service()
        return service.cancel_job(job_id)

    def get_stats(self) -> Dict[str, Any]:
        service = get_celery_job_service()
        return service.get_job_stats()

    # Creation wrappers
    def create_generation_job(self, request: GenerationRequest) -> str:
        service = get_celery_job_service()
        return service.create_generation_job(request)

    def create_enhanced_generation_job(
        self,
        request: GenerationRequest,
        *,
        sentiment_intensity: int | None = None,
        tone: str | None = None,
        enable_few_shot: bool = True,
        enable_quality_filter: bool = True,
        min_quality_score: float = 0.6,
    ) -> str:
        service = get_celery_job_service()
        return service.create_enhanced_generation_job(
            request,
            sentiment_intensity=sentiment_intensity,
            tone=tone,
            enable_few_shot=enable_few_shot,
            enable_quality_filter=enable_quality_filter,
            min_quality_score=min_quality_score,
        )

    def create_augmented_generation_job(
        self,
        request: GenerationRequest,
        augmentation_strategies: list[str],
        augment_ratio: float,
    ) -> str:
        service = get_celery_job_service()
        return service.create_augmented_generation_job(
            request,
            augmentation_strategies,
            augment_ratio,
        )


_job_store: Optional[JobStore] = None


def get_job_store() -> JobStore:
    global _job_store
    if _job_store is None:
        _job_store = JobStore()
    return _job_store

