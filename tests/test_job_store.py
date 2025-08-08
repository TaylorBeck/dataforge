import types
from typing import Dict, Any, Optional

from datetime import datetime, timezone
from app.models.schemas import JobStatusResponse, GenerationRequest
from app.services import job_store as job_store_module


class MockCeleryJobService:
    def __init__(self):
        self.created_jobs: Dict[str, Dict[str, Any]] = {}
        self.cancelled: set[str] = set()

    def create_generation_job(self, request: GenerationRequest) -> str:
        job_id = "job-123"
        self.created_jobs[job_id] = {
            "status": "pending",
            "request": request,
        }
        return job_id

    def create_enhanced_generation_job(self, *args, **kwargs) -> str:
        return "job-enhanced-123"

    def create_augmented_generation_job(self, *args, **kwargs) -> str:
        return "job-aug-123"

    def get_job_status(self, job_id: str) -> Optional[JobStatusResponse]:
        if job_id not in self.created_jobs:
            return None
        return JobStatusResponse(
            job_id=job_id,
            status="pending",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    def cancel_job(self, job_id: str) -> bool:
        if job_id in self.created_jobs:
            self.cancelled.add(job_id)
            self.created_jobs[job_id]["status"] = "cancelled"
            return True
        return False

    def get_job_stats(self) -> Dict[str, Any]:
        return {
            "active_jobs": 0,
            "scheduled_jobs": 0,
            "reserved_jobs": 0,
            "total_pending_jobs": 0,
            "active_workers": 0,
        }


def test_job_store_basic_operations(monkeypatch):
    # Patch get_celery_job_service to return our mock
    mock_service = MockCeleryJobService()
    monkeypatch.setattr(job_store_module, "get_celery_job_service", lambda: mock_service)

    store = job_store_module.get_job_store()

    req = GenerationRequest(product="widget", count=1, version="v1", temperature=0.7)
    job_id = store.create_generation_job(req)
    assert job_id == "job-123"

    status = store.get_status(job_id)
    assert status is not None
    assert status.job_id == job_id
    assert status.status in {"pending", "running", "completed", "error"}

    stats = store.get_stats()
    assert isinstance(stats, dict)
    assert "active_jobs" in stats

    cancelled = store.cancel(job_id)
    assert cancelled is True


def test_job_store_enhanced_and_augmented(monkeypatch):
    mock_service = MockCeleryJobService()
    monkeypatch.setattr(job_store_module, "get_celery_job_service", lambda: mock_service)

    store = job_store_module.get_job_store()
    req = GenerationRequest(product="gadget", count=2, version="v1", temperature=0.5)

    jid1 = store.create_enhanced_generation_job(req, sentiment_intensity=3, tone="polite")
    jid2 = store.create_augmented_generation_job(req, ["CDA"], 0.5)

    assert jid1 == "job-enhanced-123"
    assert jid2 == "job-aug-123"

