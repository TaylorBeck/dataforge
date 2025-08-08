"""
LLM-powered text generation service with async batching and metadata collection.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any
from app.config import get_settings
from app.models.schemas import GenerationRequest, GeneratedSample, GenerationResponse
from app.utils.llm_client import get_llm_client, LLMException
from app.services.prompt_service import render_enhanced_prompt, get_default_template_context
from app.services.quality_service import get_quality_service, QualityFilterConfig, QualityMetrics
from app.services.job_store import get_job_store
from app.utils.token_utils import estimate_request_cost

logger = logging.getLogger(__name__)


class GenerationService:
    """Service for generating synthetic text data using LLMs."""
    
    def __init__(self):
        """Initialize generation service."""
        self.settings = get_settings()
        self.quality_service = get_quality_service()
        
    async def generate_single_sample(
        self,
        request: GenerationRequest,
        sample_index: int = 0,
        sentiment_intensity: int = None,
        tone: str = None,
        enable_few_shot: bool = True
    ) -> GeneratedSample:
        """
        Generate a single text sample.
        
        Args:
            request: Generation request parameters
            sample_index: Index of this sample in the batch
            
        Returns:
            Generated sample with metadata
            
        Raises:
            LLMException: On generation failure
        """
        try:
            # Get LLM client (reused per batch when available)
            llm_client = getattr(self, "_llm_client", None) or get_llm_client()
            
            # Prepare template context
            context = get_default_template_context(request.product)
            
            # Render enhanced prompt template with few-shot learning
            template_name = self.settings.default_prompt_template
            prompt = render_enhanced_prompt(
                template_name=template_name,
                context=context,
                sentiment_intensity=sentiment_intensity,
                tone=tone,
                enable_few_shot=enable_few_shot,
                domain_constraints=["Include realistic details", "Be specific and actionable"],
                min_length=50,
                max_length=200
            )
            
            # Generate text
            generated_text = await llm_client.generate(
                prompt=prompt,
                temperature=request.temperature,
                max_tokens=self.settings.openai_max_tokens
            )
            
            # Estimate token count (rough approximation)
            tokens_estimated = len(generated_text.split()) * 1.3  # ~1.3 tokens per word
            
            # Create sample with metadata
            sample = GeneratedSample(
                id=str(uuid.uuid4()),
                product=request.product,
                prompt_version=request.version,
                generated_at=datetime.now(timezone.utc),
                text=generated_text,
                tokens_estimated=int(tokens_estimated),
                temperature=request.temperature
            )
            
            logger.debug(f"Generated sample {sample_index + 1} for product: {request.product}")
            return sample
            
        except Exception as e:
            logger.error(f"Failed to generate sample {sample_index}: {e}")
            raise LLMException(f"Generation failed: {e}")
    
    async def generate_batch(
        self,
        request: GenerationRequest,
        progress_callback=None,
        enable_quality_filter: bool = True,
        sentiment_intensity: int = None,
        tone: str = None,
        enable_few_shot: bool = True
    ) -> GenerationResponse:
        """
        Generate a batch of text samples concurrently.
        
        Args:
            request: Generation request parameters
            progress_callback: Optional callback for progress updates
            
        Returns:
            Generation response with all samples
            
        Raises:
            LLMException: On generation failure
        """
        logger.info(f"Starting batch generation: {request.count} samples for '{request.product}'")
        
        try:
            # Create or reuse a single LLM client for the whole batch to reduce overhead
            self._llm_client = get_llm_client()

            # Create generation tasks with enhanced features
            tasks = [
                self.generate_single_sample(
                    request, i, sentiment_intensity, tone, enable_few_shot
                )
                for i in range(request.count)
            ]
            
            # Execute tasks concurrently with progress tracking
            samples = []
            completed = 0
            
            # Process in smaller chunks to provide progress updates
            chunk_size = min(5, request.count)  # Process max 5 at a time
            
            for i in range(0, len(tasks), chunk_size):
                chunk_tasks = tasks[i:i + chunk_size]
                
                # Execute chunk
                chunk_results = await asyncio.gather(*chunk_tasks, return_exceptions=True)
                
                # Process results
                for result in chunk_results:
                    if isinstance(result, Exception):
                        logger.error(f"Sample generation failed: {result}")
                        raise result
                    samples.append(result)
                    completed += 1
                
                # Report progress
                if progress_callback:
                    progress = int((completed / request.count) * 100)
                    await progress_callback(progress)
            
            # Apply quality filtering if enabled
            filtered_samples = samples
            quality_metrics = []
            filter_stats = {}
            
            if enable_quality_filter and samples:
                logger.info(f"Applying quality filtering to {len(samples)} samples")
                
                # Filter samples based on quality
                context = {
                    'template_type': self.settings.default_prompt_template,
                    'product': request.product
                }
                
                filtered_samples, quality_metrics = await self.quality_service.filter_batch(
                    samples, context
                )
                
                filter_stats = self.quality_service.get_filter_stats()
                
                logger.info(
                    f"Quality filtering completed: {len(filtered_samples)}/{len(samples)} samples passed "
                    f"(pass rate: {filter_stats.get('pass_rate', 0.0):.1%})"
                )
            
            # Calculate total tokens for filtered samples
            total_tokens = sum(sample.tokens_estimated for sample in filtered_samples)
            
            # Create response with quality information
            response = GenerationResponse(
                samples=filtered_samples,
                total_samples=len(filtered_samples),
                total_tokens_estimated=total_tokens
            )
            
            # Add quality metadata to response
            if quality_metrics:
                avg_quality = sum(m.overall_score for m in quality_metrics) / len(quality_metrics)
                response.metadata = {
                    'quality_filter_enabled': enable_quality_filter,
                    'original_sample_count': len(samples),
                    'filtered_sample_count': len(filtered_samples),
                    'filter_stats': filter_stats,
                    'average_quality_score': avg_quality,
                    'quality_metrics': [
                        {
                            'sample_id': sample.id,
                            'overall_score': metric.overall_score,
                            'coherence_score': metric.coherence_score,
                            'relevance_score': metric.relevance_score,
                            'uniqueness_score': metric.uniqueness_score
                        }
                        for sample, metric in zip(filtered_samples, quality_metrics)
                    ] if len(quality_metrics) <= 10 else []  # Limit metadata size
                }
            
            logger.info(f"Batch generation completed: {len(filtered_samples)} samples, ~{total_tokens} tokens")
            return response
            
        except Exception as e:
            logger.error(f"Batch generation failed: {e}")
            raise
        finally:
            # Ensure per-batch client is released
            if hasattr(self, "_llm_client"):
                delattr(self, "_llm_client")
    
    async def generate_with_job_tracking(
        self,
        request: GenerationRequest,
        job_id: str
    ) -> GenerationResponse:
        """
        Generate samples with job status tracking.
        
        Args:
            request: Generation request parameters
            job_id: Job identifier for tracking
            
        Returns:
            Generation response
        """
        # Use Celery task state for progress in workers; JobStore manages creation/cancellation
        job_store = get_job_store()
        worker_id = f"worker-{uuid.uuid4().hex[:8]}"
        
        try:
            # Update job status to running
            # No-op for Celery pathway; progress is tracked in Celery task meta
            
            # Progress callback for job updates
            async def update_progress(progress: int):
                # No-op; keep signature for compatibility if needed in future
                return None
            
            # Generate samples
            result = await self.generate_batch(request, update_progress)
            
            # Store results and update status
            # In Celery flow, results are stored in backend and retrieved via JobStore
            
            return result
            
        except Exception as e:
            raise
    
    async def validate_generation_request(self, request: GenerationRequest) -> Dict[str, Any]:
        """
        Validate generation request and check system readiness.
        
        Args:
            request: Generation request to validate
            
        Returns:
            Validation results dictionary
        """
        results = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "estimated_cost": 0.0,
            "estimated_duration": 0.0
        }
        
        try:
            # Check LLM client availability
            llm_client = get_llm_client()
            if not await llm_client.health_check():
                results["errors"].append("LLM service unavailable")
                results["valid"] = False
            
            # Estimate cost using tokenizer/pricing map if using OpenAI
            if self.settings.default_llm_provider == "openai":
                # Build a representative prompt to estimate prompt tokens
                context = get_default_template_context(request.product)
                template_name = self.settings.default_prompt_template
                prompt = render_enhanced_prompt(
                    template_name=template_name,
                    context=context,
                    sentiment_intensity=None,
                    tone=None,
                    enable_few_shot=False,
                    domain_constraints=[],
                    min_length=50,
                    max_length=200
                )
                expected_completion_tokens = min(self.settings.openai_max_tokens, 200)
                _, est_cost = estimate_request_cost(prompt, expected_completion_tokens)
                # Total cost roughly scales with count (upper bound)
                results["estimated_cost"] = round(est_cost * request.count, 4)
            
            # Estimate duration (rough approximation)
            # Assume ~2 seconds per sample with concurrent execution
            estimated_duration = (request.count / 5) * 2  # 5 concurrent requests
            results["estimated_duration"] = round(estimated_duration, 1)
            
            # Check if count exceeds limits
            if request.count > self.settings.max_samples_per_request:
                results["errors"].append(
                    f"Sample count {request.count} exceeds maximum {self.settings.max_samples_per_request}"
                )
                results["valid"] = False
            
            # Add warnings for large requests
            if request.count > 20:
                results["warnings"].append("Large requests may take several minutes to complete")
            
            if results.get("estimated_cost", 0.0) > 1.0:
                results["warnings"].append(f"Estimated cost: ${results['estimated_cost']:.2f}")
            
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            results["errors"].append(f"Validation error: {e}")
            results["valid"] = False
        
        return results
    
    async def generate_with_augmentation(self,
                                       request: GenerationRequest,
                                       augmentation_strategies: List[str] = None,
                                       augment_ratio: float = 0.5) -> GenerationResponse:
        """
        Generate samples with optional data augmentation.
        
        Args:
            request: Base generation request
            augmentation_strategies: List of strategies to apply ('CDA', 'ADA', 'CADA')
            augment_ratio: Ratio of augmented to original samples (0.0 to 1.0)
            
        Returns:
            Generation response with original and augmented samples
        """
        try:
            from app.services.data_augmentation_service import (
                get_augmentation_service, AugmentationStrategy, AugmentationRequest
            )
            
            # Generate original samples
            base_response = await self.generate_batch(request)
            samples = base_response.samples.copy()
            
            # Apply augmentation if requested
            if augmentation_strategies and augment_ratio > 0:
                augmentation_service = get_augmentation_service()
                
                # Calculate how many samples to augment
                num_original = len(samples)
                num_to_augment = min(num_original, max(1, int(num_original * augment_ratio)))
                
                # Select strategies
                strategy_map = {
                    'CDA': AugmentationStrategy.CDA,
                    'ADA': AugmentationStrategy.ADA, 
                    'CADA': AugmentationStrategy.CADA
                }
                
                for strategy_name in augmentation_strategies:
                    if strategy_name not in strategy_map:
                        logger.warning(f"Unknown augmentation strategy: {strategy_name}")
                        continue
                    
                    strategy = strategy_map[strategy_name]
                    
                    # Apply to selected samples
                    for i in range(num_to_augment):
                        if i < len(samples):
                            original_sample = samples[i]
                            
                            try:
                                augmented_samples = await augmentation_service.create_augmented_samples(
                                    original_sample=original_sample,
                                    strategy=strategy,
                                    num_variants=2  # Generate 2 variants per strategy
                                )
                                
                                samples.extend(augmented_samples)
                                
                            except Exception as e:
                                logger.warning(f"Augmentation failed for sample {i} with {strategy_name}: {e}")
                                continue
            
            # Create enhanced response
            enhanced_response = GenerationResponse(samples=samples)
            
            logger.info(
                f"Generation with augmentation completed: "
                f"{len(base_response.samples)} original + "
                f"{len(samples) - len(base_response.samples)} augmented = "
                f"{len(samples)} total samples"
            )
            
            return enhanced_response
            
        except ImportError:
            logger.warning("Data augmentation service not available, returning base generation")
            return await self.generate_batch(request)
        except Exception as e:
            logger.error(f"Enhanced generation failed: {e}")
            # Fall back to basic generation
            return await self.generate_batch(request)


# Global generation service instance
_generation_service: GenerationService = None


def get_generation_service() -> GenerationService:
    """Get global generation service instance."""
    global _generation_service
    if _generation_service is None:
        _generation_service = GenerationService()
    return _generation_service


async def run_generation_job(request: GenerationRequest, job_id: str) -> None:
    """
    Background task to run generation job.
    
    Args:
        request: Generation request parameters
        job_id: Job identifier
    """
    service = get_generation_service()
    
    try:
        logger.info(f"Starting generation job {job_id}")
        
        # Run generation with job tracking
        await service.generate_with_job_tracking(request, job_id)
        
        logger.info(f"Generation job {job_id} completed successfully")
        
    except Exception as e:
        logger.error(f"Generation job {job_id} failed: {e}")
        # Error handling is done in generate_with_job_tracking