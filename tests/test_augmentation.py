import pytest
from datetime import datetime, timezone

from app.models.schemas import GeneratedSample
from app.services.data_augmentation_service import (
    DataAugmentationService,
    AugmentationStrategy,
)


@pytest.mark.asyncio
async def test_augmentation_service_with_mock_llm(monkeypatch):
    # Force mock LLM provider via settings
    from app.config import get_settings

    settings = get_settings()
    settings.default_llm_provider = "mock"

    svc = DataAugmentationService()

    original = GeneratedSample(
        id="orig-1",
        product="widget",
        prompt_version="v1",
        generated_at=datetime.now(timezone.utc),
        text="The widget battery life is disappointing and affects my usage.",
        tokens_estimated=50,
        temperature=0.7,
    )

    # Try CDA strategy end-to-end
    augmented = await svc.create_augmented_samples(original, AugmentationStrategy.CDA, num_variants=1)
    assert isinstance(augmented, list)
    # May be empty in rare cases; ensure no crash and proper structure
    for s in augmented:
        assert s.product == original.product
        assert "augmentation_strategy" in (s.metadata or {})
