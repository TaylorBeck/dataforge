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
from app.services.prompt_service import render_prompt, get_default_template_context
from app.services.job_manager import get_job_manager

logger = logging.getLogger(__name__)


class GenerationService:
    """Service for generating synthetic text data using LLMs."""
    
    def __init__(self):
        """Initialize generation service."""
        self.settings = get_settings()
        
    async def generate_single_sample(
        self,
        request: GenerationRequest,
        sample_index: int = 0
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
            # Get LLM client
            llm_client = get_llm_client()
            
            # Prepare template context
            context = get_default_template_context(request.product)
            
            # Render prompt template
            template_name = self.settings.default_prompt_template
            prompt = render_prompt(template_name, context, request.version)
            
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
        progress_callback=None
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
            # Create generation tasks
            tasks = [
                self.generate_single_sample(request, i)
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
            
            # Calculate total tokens
            total_tokens = sum(sample.tokens_estimated for sample in samples)
            
            response = GenerationResponse(
                samples=samples,
                total_samples=len(samples),
                total_tokens_estimated=total_tokens
            )
            
            logger.info(f"Batch generation completed: {len(samples)} samples, ~{total_tokens} tokens")
            return response
            
        except Exception as e:
            logger.error(f"Batch generation failed: {e}")
            raise
    
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
        job_manager = await get_job_manager()
        worker_id = f"worker-{uuid.uuid4().hex[:8]}"
        
        try:
            # Update job status to running
            await job_manager.update_job_status(
                job_id=job_id,
                status="running",
                progress=0,
                worker_id=worker_id
            )
            
            # Progress callback for job updates
            async def update_progress(progress: int):
                await job_manager.update_job_status(
                    job_id=job_id,
                    status="running",
                    progress=progress,
                    worker_id=worker_id
                )
            
            # Generate samples
            result = await self.generate_batch(request, update_progress)
            
            # Store results and update status
            await job_manager.store_job_result(job_id, result)
            await job_manager.update_job_status(
                job_id=job_id,
                status="completed",
                progress=100,
                worker_id=worker_id
            )
            
            return result
            
        except Exception as e:
            # Update job status to error
            await job_manager.update_job_status(
                job_id=job_id,
                status="error",
                error_message=str(e),
                worker_id=worker_id
            )
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
            
            # Estimate cost (rough approximation for OpenAI)
            if self.settings.default_llm_provider == "openai":
                # Assume ~100 tokens per sample for cost estimation
                estimated_tokens = request.count * 100
                # GPT-4 pricing (approximate): $0.03 per 1K tokens
                estimated_cost = (estimated_tokens / 1000) * 0.03
                results["estimated_cost"] = round(estimated_cost, 4)
            
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
            
            if estimated_cost > 1.0:
                results["warnings"].append(f"Estimated cost: ${estimated_cost:.2f}")
            
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            results["errors"].append(f"Validation error: {e}")
            results["valid"] = False
        
        return results


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