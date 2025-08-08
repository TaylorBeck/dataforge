import asyncio
import pytest
from datetime import datetime, timezone

from app.models.schemas import GeneratedSample
from app.services.quality_service import QualityFilterService, QualityFilterConfig


@pytest.mark.asyncio
async def test_quality_filtering_pass_and_fail(monkeypatch):
    # Create samples: one too short, one acceptable
    short_sample = GeneratedSample(
        id="s1",
        product="widget",
        prompt_version="v1",
        generated_at=datetime.now(timezone.utc),
        text="Too short.",
        tokens_estimated=5,
        temperature=0.7,
    )

    good_text = "This is a sufficiently long and coherent sample text about the widget product that should pass basic length checks."
    good_sample = GeneratedSample(
        id="s2",
        product="widget",
        prompt_version="v1",
        generated_at=datetime.now(timezone.utc),
        text=good_text,
        tokens_estimated=100,
        temperature=0.7,
    )

    # Use higher threshold but still lenient for default heuristic scores
    service = QualityFilterService(QualityFilterConfig(min_overall_score=0.3))

    filtered, metrics = await service.filter_samples([short_sample, good_sample])
    assert any(s.id == "s2" for s in filtered)
    assert all(s.id != "s1" for s in filtered)

    stats = service.get_filter_stats()
    assert stats["total_processed"] == 2
    assert stats["passed_filter"] >= 1
