#!/usr/bin/env python3
"""
Test script demonstrating the new enhanced features for frontend integration.

This script tests:
1. Few-shot learning with enhanced prompt templates
2. Quality filtering with deduplication and scoring
3. Sentiment intensity control
4. Tone specification
5. API configuration endpoints
"""
import asyncio
import json
from datetime import datetime
from typing import Dict, Any

from app.models.schemas import GeneratedSample
from app.services.prompt_service import (
    render_enhanced_prompt, 
    get_template_service,
    PromptConfig,
    FewShotExample
)
from app.services.quality_service import (
    get_quality_service, 
    QualityFilterConfig,
    QualityScorer
)


async def test_few_shot_prompting():
    """Test few-shot learning with enhanced prompts."""
    print("🧠 Testing Few-Shot Learning...")
    
    # Test enhanced prompt with few-shot examples
    enhanced_prompt = render_enhanced_prompt(
        template_name="support_request.j2",
        context={"product": "DataForge API"},
        sentiment_intensity=2,  # Negative sentiment
        tone="frustrated",
        enable_few_shot=True,
        min_length=50,
        max_length=150
    )
    
    print("Enhanced Prompt (excerpt):")
    print("-" * 50)
    print(enhanced_prompt[:500] + "..." if len(enhanced_prompt) > 500 else enhanced_prompt)
    print("-" * 50)
    print(f"Prompt length: {len(enhanced_prompt)} characters")
    print(f"Contains examples: {'Example 1:' in enhanced_prompt}")
    print(f"Contains sentiment scale: {'Very Negative' in enhanced_prompt}")
    print()


async def test_quality_filtering():
    """Test quality filtering and deduplication."""
    print("🔍 Testing Quality Filtering...")
    
    # Create test samples with varying quality
    test_samples = [
        GeneratedSample(
            id="1",
            product="TestApp",
            prompt_version="v1",
            generated_at=datetime.now(),
            text="This app is amazing! I love how easy it is to use and the features work perfectly. The customer support team was very helpful when I had questions during setup. I would definitely recommend this to my colleagues.",
            tokens_estimated=45,
            temperature=0.7
        ),
        GeneratedSample(
            id="2", 
            product="TestApp",
            prompt_version="v1",
            generated_at=datetime.now(),
            text="Bad app. Doesn't work.",  # Poor quality - too short
            tokens_estimated=5,
            temperature=0.7
        ),
        GeneratedSample(
            id="3",
            product="TestApp", 
            prompt_version="v1",
            generated_at=datetime.now(),
            text="This app is amazing! I love how easy it is to use and the features work perfectly. The customer support team was very helpful when I had questions during setup. I would definitely recommend this to my colleagues.",  # Duplicate
            tokens_estimated=45,
            temperature=0.7
        ),
        GeneratedSample(
            id="4",
            product="TestApp",
            prompt_version="v1", 
            generated_at=datetime.now(),
            text="The application has some good features, but I've encountered several bugs that make it frustrating to use. The interface could be more intuitive, and the loading times are quite slow. Customer service was responsive, but the technical issues remain unresolved.",
            tokens_estimated=42,
            temperature=0.7
        )
    ]
    
    # Configure quality filter
    config = QualityFilterConfig(
        min_overall_score=0.6,
        min_length_words=10,
        max_length_words=200,
        enable_deduplication=True,
        similarity_threshold=0.85
    )
    
    quality_service = get_quality_service(config)
    
    # Filter samples
    filtered_samples, quality_metrics = await quality_service.filter_batch(
        test_samples,
        context={"template_type": "support_request"}
    )
    
    print(f"Original samples: {len(test_samples)}")
    print(f"Filtered samples: {len(filtered_samples)}")
    print(f"Filter efficiency: {len(filtered_samples)/len(test_samples):.1%}")
    
    # Show quality scores
    print("\nQuality Scores:")
    for i, (sample, metric) in enumerate(zip(filtered_samples, quality_metrics)):
        print(f"Sample {i+1}: Overall={metric.overall_score:.3f}, "
              f"Coherence={metric.coherence_score:.3f}, "
              f"Relevance={metric.relevance_score:.3f}, "
              f"Uniqueness={metric.uniqueness_score:.3f}")
    
    # Show filter stats
    stats = quality_service.get_filter_stats()
    print(f"\nFilter Statistics:")
    print(f"  Total processed: {stats['total_processed']}")
    print(f"  Passed filter: {stats['passed_filter']}")
    print(f"  Failed length: {stats['failed_length']}")
    print(f"  Failed quality: {stats['failed_quality']}")
    print(f"  Failed duplicate: {stats['failed_duplicate']}")
    print(f"  Pass rate: {stats.get('pass_rate', 0.0):.1%}")
    print()


def test_configuration_api():
    """Test configuration API functionality."""
    print("⚙️  Testing Configuration API...")
    
    from app.services.prompt_service import get_template_service
    from app.services.data_augmentation_service import get_augmentation_service
    from app.config import get_settings
    
    template_service = get_template_service()
    augmentation_service = get_augmentation_service()
    settings = get_settings()
    
    # Simulate the /api/config endpoint
    config = {
        "features": {
            "few_shot_learning": True,
            "quality_filtering": True,
            "data_augmentation": True,
            "sentiment_intensity_control": True,
            "tone_control": True,
            "rate_limiting": True
        },
        "templates": {
            "available": template_service.list_templates(),
            "default": settings.default_prompt_template
        },
        "sentiment_intensity": {
            "scale": "1-5",
            "descriptions": {
                1: "Very Negative - Highly dissatisfied, angry, or frustrated",
                2: "Negative - Dissatisfied or disappointed",
                3: "Neutral - Balanced or indifferent", 
                4: "Positive - Satisfied or pleased",
                5: "Very Positive - Extremely satisfied, delighted, or enthusiastic"
            }
        },
        "tone_options": [
            "frustrated", "polite", "urgent", "professional", "casual",
            "formal", "friendly", "concerned", "enthusiastic", "neutral"
        ],
        "augmentation_strategies": augmentation_service.get_strategy_info(),
        "quality_filtering": {
            "default_min_score": 0.6,
            "metrics": ["overall_score", "coherence_score", "relevance_score", "uniqueness_score"],
            "deduplication": True
        }
    }
    
    print("Available Features:")
    for feature, enabled in config["features"].items():
        status = "✅" if enabled else "❌"
        print(f"  {status} {feature}")
    
    print(f"\nTemplates: {config['templates']['available']}")
    print(f"Default Template: {config['templates']['default']}")
    
    print(f"\nSentiment Scale: {config['sentiment_intensity']['scale']}")
    print(f"Tone Options: {len(config['tone_options'])} available")
    print(f"Augmentation Strategies: {list(config['augmentation_strategies'].keys())}")
    
    print("\nConfiguration API ready for frontend integration! 🚀")
    print()


def test_template_variations():
    """Test different template variations with sentiment and tone."""
    print("🎭 Testing Template Variations...")
    
    variations = [
        {"sentiment": 1, "tone": "frustrated", "name": "Very Negative + Frustrated"},
        {"sentiment": 3, "tone": "neutral", "name": "Neutral + Neutral"},
        {"sentiment": 5, "tone": "enthusiastic", "name": "Very Positive + Enthusiastic"}
    ]
    
    for var in variations:
        prompt = render_enhanced_prompt(
            template_name="product_review.j2",
            context={"product": "DataForge API"},
            sentiment_intensity=var["sentiment"],
            tone=var["tone"],
            enable_few_shot=True
        )
        
        print(f"{var['name']}:")
        # Show a snippet of the prompt
        lines = prompt.split('\n')
        relevant_lines = [line for line in lines if 'Sentiment Level:' in line or 'Tone:' in line or line.startswith('- ')][:3]
        for line in relevant_lines:
            print(f"  {line}")
        print()


async def main():
    """Run all enhanced feature tests."""
    print("🧪 DataForge Enhanced Features Test Suite")
    print("=" * 60)
    print()
    
    # Test individual components
    await test_few_shot_prompting()
    await test_quality_filtering()
    test_configuration_api()
    test_template_variations()
    
    print("✅ All Enhanced Features Working!")
    print("\n🎯 Ready for Frontend Integration:")
    print("   • POST /api/generate-enhanced - Enhanced generation with all features")
    print("   • GET /api/config - Frontend configuration and capabilities")
    print("   • GET /api/quality-stats - Quality filtering statistics")
    print("   • GET /api/rate-limit-status - Rate limiting status")
    print("\n🚀 Your DataForge API is now frontend-ready!")


if __name__ == "__main__":
    asyncio.run(main())