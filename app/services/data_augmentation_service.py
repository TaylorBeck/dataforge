"""
Advanced Data Augmentation Service implementing CDA, ADA, and CADA strategies.

Based on expert research findings from sentiment analysis training data generation:
- Context-Focused Data Augmentation (CDA): Changes contextual words while preserving aspect terms
- Aspect-Focused Data Augmentation (ADA): Replaces aspect terms with suitable alternatives
- Context-Aspect Data Augmentation (CADA): Combines both CDA and ADA strategies
"""

import asyncio
import logging
import re
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field

from app.config import get_settings
from app.models.schemas import GeneratedSample
from app.utils.llm_client import get_llm_client, LLMException

logger = logging.getLogger(__name__)


class AugmentationStrategy(Enum):
    """Available data augmentation strategies."""
    CDA = "context_focused"  # Context-Focused Data Augmentation
    ADA = "aspect_focused"   # Aspect-Focused Data Augmentation
    CADA = "context_aspect"  # Context-Aspect Data Augmentation


@dataclass
class AugmentationRequest:
    """Request for data augmentation with strategy and parameters."""
    text: str
    strategy: AugmentationStrategy
    num_variants: int = 3
    preserve_sentiment: bool = True
    preserve_length: bool = True
    min_similarity: float = 0.8
    product: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AugmentationResult:
    """Result of data augmentation operation."""
    original_text: str
    augmented_texts: List[str]
    strategy_used: AugmentationStrategy
    quality_scores: List[float]
    preserved_aspects: List[str]
    changed_elements: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


class AugmentationStrategyBase(ABC):
    """Base class for data augmentation strategies."""
    
    def __init__(self):
        self.settings = get_settings()
        self._aspect_keywords = self._load_aspect_keywords()
        self._sentiment_words = self._load_sentiment_words()
    
    @abstractmethod
    async def augment(self, request: AugmentationRequest) -> AugmentationResult:
        """Generate augmented text variants using this strategy."""
        pass
    
    @abstractmethod
    def _extract_aspects(self, text: str) -> List[str]:
        """Extract aspect terms from text."""
        pass
    
    def _load_aspect_keywords(self) -> Set[str]:
        """Load common aspect keywords for different domains."""
        # Common aspect terms for customer service, products, etc.
        return {
            # Product aspects
            'quality', 'price', 'cost', 'value', 'design', 'appearance',
            'performance', 'speed', 'reliability', 'durability', 'features',
            'functionality', 'usability', 'interface', 'battery', 'display',
            'size', 'weight', 'color', 'style', 'brand', 'packaging',
            
            # Service aspects  
            'service', 'support', 'help', 'assistance', 'response', 'delivery',
            'shipping', 'installation', 'setup', 'training', 'documentation',
            'warranty', 'guarantee', 'refund', 'return', 'exchange',
            
            # Experience aspects
            'experience', 'satisfaction', 'convenience', 'ease', 'simplicity',
            'comfort', 'safety', 'security', 'privacy', 'trust', 'confidence'
        }
    
    def _load_sentiment_words(self) -> Dict[str, List[str]]:
        """Load sentiment-bearing words for validation."""
        return {
            'positive': [
                'excellent', 'amazing', 'great', 'wonderful', 'fantastic',
                'outstanding', 'superb', 'brilliant', 'perfect', 'love',
                'like', 'enjoy', 'pleased', 'satisfied', 'happy', 'delighted'
            ],
            'negative': [
                'terrible', 'awful', 'horrible', 'disappointing', 'frustrating',
                'annoying', 'poor', 'bad', 'worst', 'hate', 'dislike',
                'unhappy', 'dissatisfied', 'angry', 'upset', 'confused'
            ],
            'neutral': [
                'okay', 'fine', 'average', 'standard', 'normal', 'typical',
                'regular', 'basic', 'simple', 'plain', 'moderate'
            ]
        }
    
    async def _validate_preservation(self, 
                                   original: str, 
                                   augmented: str,
                                   aspects_to_preserve: List[str]) -> Tuple[bool, float]:
        """Validate that important aspects are preserved in augmented text."""
        try:
            # Check aspect preservation
            preserved_aspects = 0
            for aspect in aspects_to_preserve:
                if aspect.lower() in augmented.lower():
                    preserved_aspects += 1
            
            aspect_preservation = preserved_aspects / len(aspects_to_preserve) if aspects_to_preserve else 1.0
            
            # Use LLM for semantic similarity check if available
            similarity_score = await self._calculate_semantic_similarity(original, augmented)
            
            # Combined validation score
            validation_score = (aspect_preservation + similarity_score) / 2
            is_valid = validation_score >= 0.8  # Threshold for acceptance
            
            return is_valid, validation_score
            
        except Exception as e:
            logger.warning(f"Validation failed: {e}")
            return False, 0.0
    
    async def _calculate_semantic_similarity(self, text1: str, text2: str) -> float:
        """Calculate semantic similarity between two texts using LLM."""
        try:
            llm_client = get_llm_client()
            
            prompt = f"""
            Please rate the semantic similarity between these two texts on a scale of 0.0 to 1.0:
            
            Text 1: "{text1}"
            Text 2: "{text2}"
            
            Consider:
            - Overall meaning preservation
            - Sentiment consistency
            - Key information retention
            
            Respond with only a number between 0.0 and 1.0:
            """
            
            response = await llm_client.generate(prompt, temperature=0.0, max_tokens=10)
            
            # Extract numeric score
            score_match = re.search(r'(\d+\.?\d*)', response.strip())
            if score_match:
                score = float(score_match.group(1))
                return min(max(score, 0.0), 1.0)  # Clamp between 0 and 1
            
            return 0.5  # Default if parsing fails
            
        except Exception as e:
            logger.warning(f"Similarity calculation failed: {e}")
            return 0.5


class ContextFocusedAugmentation(AugmentationStrategyBase):
    """
    Context-Focused Data Augmentation (CDA) Strategy.
    
    Changes contextual words while preserving aspect terms and sentiment polarity.
    Uses paraphrasing to increase semantic richness and diversity.
    """
    
    async def augment(self, request: AugmentationRequest) -> AugmentationResult:
        """Generate CDA variants by paraphrasing context while preserving aspects."""
        aspects = self._extract_aspects(request.text)
        augmented_texts = []
        quality_scores = []
        preserved_aspects = aspects.copy()
        changed_elements = []
        
        for i in range(request.num_variants):
            try:
                # Generate paraphrase with aspect preservation
                variant = await self._generate_context_paraphrase(
                    request.text, 
                    aspects, 
                    request.preserve_sentiment
                )
                
                if variant and variant != request.text:
                    # Validate preservation
                    is_valid, score = await self._validate_preservation(
                        request.text, variant, aspects
                    )
                    
                    if is_valid and score >= request.min_similarity:
                        augmented_texts.append(variant)
                        quality_scores.append(score)
                        
                        # Track what changed
                        changes = self._identify_changes(request.text, variant, aspects)
                        changed_elements.extend(changes)
                
            except Exception as e:
                logger.warning(f"CDA variant {i} generation failed: {e}")
                continue
        
        return AugmentationResult(
            original_text=request.text,
            augmented_texts=augmented_texts,
            strategy_used=AugmentationStrategy.CDA,
            quality_scores=quality_scores,
            preserved_aspects=preserved_aspects,
            changed_elements=list(set(changed_elements)),
            metadata={
                'requested_variants': request.num_variants,
                'successful_variants': len(augmented_texts),
                'avg_quality_score': sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
            }
        )
    
    def _extract_aspects(self, text: str) -> List[str]:
        """Extract aspect terms from text using keyword matching."""
        text_lower = text.lower()
        found_aspects = []
        
        for aspect in self._aspect_keywords:
            if aspect in text_lower:
                found_aspects.append(aspect)
        
        # Also look for product names and specific nouns
        product_patterns = [
            r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b',  # Proper nouns
            r'\b(?:app|software|device|product|service|system|platform)\b'
        ]
        
        for pattern in product_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            found_aspects.extend([m.lower() for m in matches])
        
        return list(set(found_aspects))
    
    async def _generate_context_paraphrase(self, 
                                         text: str, 
                                         aspects: List[str],
                                         preserve_sentiment: bool) -> str:
        """Generate paraphrase that preserves aspects and sentiment."""
        llm_client = get_llm_client()
        
        # Create constraint instructions
        aspect_constraint = ""
        if aspects:
            aspect_constraint = f"Keep these key terms unchanged: {', '.join(aspects)}"
        
        sentiment_constraint = ""
        if preserve_sentiment:
            sentiment_constraint = "Maintain the same sentiment and emotional tone."
        
        prompt = f"""
        Generate a new sentence using paraphrasing. The requirements are:
        1. {aspect_constraint}
        2. {sentiment_constraint}
        3. Keep the semantics and core meaning unchanged
        4. Change the sentence structure and contextual words for variety
        5. Maintain similar length and readability
        
        Original: "{text}"
        
        Paraphrase:
        """
        
        response = await llm_client.generate(prompt, temperature=0.7, max_tokens=150)
        return response.strip().strip('"')
    
    def _identify_changes(self, original: str, variant: str, aspects: List[str]) -> List[str]:
        """Identify what elements changed between original and variant."""
        original_words = set(original.lower().split())
        variant_words = set(variant.lower().split())
        aspect_words = set(aspect.lower() for aspect in aspects)
        
        # Words that were changed (not in aspects)
        added_words = variant_words - original_words - aspect_words
        removed_words = original_words - variant_words - aspect_words
        
        changes = []
        changes.extend([f"added: {word}" for word in added_words])
        changes.extend([f"removed: {word}" for word in removed_words])
        
        return changes


class AspectFocusedAugmentation(AugmentationStrategyBase):
    """
    Aspect-Focused Data Augmentation (ADA) Strategy.
    
    Replaces aspect terms with semantically suitable alternatives while preserving context.
    Increases diversity of aspect terms and improves model robustness.
    """
    
    async def augment(self, request: AugmentationRequest) -> AugmentationResult:
        """Generate ADA variants by replacing aspects with alternatives."""
        aspects = self._extract_aspects(request.text)
        augmented_texts = []
        quality_scores = []
        changed_elements = []
        
        if not aspects:
            logger.warning("No aspects found for ADA augmentation")
            return AugmentationResult(
                original_text=request.text,
                augmented_texts=[],
                strategy_used=AugmentationStrategy.ADA,
                quality_scores=[],
                preserved_aspects=[],
                changed_elements=[],
                metadata={'no_aspects_found': True}
            )
        
        for i in range(request.num_variants):
            try:
                # Select aspect to replace
                aspect_to_replace = aspects[i % len(aspects)]
                
                # Generate alternative aspect
                alternative = await self._generate_aspect_alternative(
                    aspect_to_replace, 
                    request.text,
                    request.product
                )
                
                if alternative and alternative != aspect_to_replace:
                    # Replace in text
                    variant = self._replace_aspect_in_text(
                        request.text, 
                        aspect_to_replace, 
                        alternative
                    )
                    
                    if variant != request.text:
                        # Validate preservation
                        remaining_aspects = [a for a in aspects if a != aspect_to_replace]
                        is_valid, score = await self._validate_preservation(
                            request.text, variant, remaining_aspects
                        )
                        
                        if is_valid and score >= request.min_similarity:
                            augmented_texts.append(variant)
                            quality_scores.append(score)
                            changed_elements.append(f"replaced '{aspect_to_replace}' with '{alternative}'")
                
            except Exception as e:
                logger.warning(f"ADA variant {i} generation failed: {e}")
                continue
        
        return AugmentationResult(
            original_text=request.text,
            augmented_texts=augmented_texts,
            strategy_used=AugmentationStrategy.ADA,
            quality_scores=quality_scores,
            preserved_aspects=[a for a in aspects if a not in [ce.split("'")[1] for ce in changed_elements if "replaced" in ce]],
            changed_elements=changed_elements,
            metadata={
                'original_aspects': aspects,
                'successful_replacements': len(changed_elements)
            }
        )
    
    def _extract_aspects(self, text: str) -> List[str]:
        """Extract aspect terms with more sophisticated NLP techniques."""
        return super()._extract_aspects(text)
    
    async def _generate_aspect_alternative(self, 
                                         aspect: str, 
                                         context: str,
                                         product: Optional[str] = None) -> str:
        """Generate semantically suitable alternative for an aspect term."""
        llm_client = get_llm_client()
        
        product_context = f" in the context of {product}" if product else ""
        
        prompt = f"""
        Generate a semantically similar alternative for the aspect term "{aspect}"{product_context}.
        
        Context sentence: "{context}"
        
        Requirements:
        1. The alternative should be semantically related but different
        2. It should fit naturally in the context
        3. Maintain the same domain and meaning category
        4. Ensure it's a valid substitute
        
        Provide only the alternative term, no explanation:
        """
        
        response = await llm_client.generate(prompt, temperature=0.8, max_tokens=20)
        alternative = response.strip().strip('"').lower()
        
        # Verify it's actually different
        if alternative == aspect.lower():
            return None
        
        return alternative
    
    def _replace_aspect_in_text(self, text: str, old_aspect: str, new_aspect: str) -> str:
        """Replace aspect term in text while preserving context."""
        # Case-sensitive replacement with word boundaries
        pattern = r'\b' + re.escape(old_aspect) + r'\b'
        result = re.sub(pattern, new_aspect, text, flags=re.IGNORECASE)
        return result


class ContextAspectAugmentation(AugmentationStrategyBase):
    """
    Context-Aspect Data Augmentation (CADA) Strategy.
    
    Combines both CDA and ADA strategies for maximum diversity.
    Achieves best performance with diversification of both sentence structure and aspect terms.
    """
    
    def __init__(self):
        super().__init__()
        self.cda_strategy = ContextFocusedAugmentation()
        self.ada_strategy = AspectFocusedAugmentation()
    
    async def augment(self, request: AugmentationRequest) -> AugmentationResult:
        """Generate CADA variants by combining CDA and ADA strategies."""
        aspects = self._extract_aspects(request.text)
        augmented_texts = []
        quality_scores = []
        changed_elements = []
        preserved_aspects = aspects.copy()
        
        # Split variants between strategies
        cda_variants = max(1, request.num_variants // 2)
        ada_variants = request.num_variants - cda_variants
        
        # Generate CDA variants
        cda_request = AugmentationRequest(
            text=request.text,
            strategy=AugmentationStrategy.CDA,
            num_variants=cda_variants,
            preserve_sentiment=request.preserve_sentiment,
            preserve_length=request.preserve_length,
            min_similarity=request.min_similarity,
            product=request.product
        )
        
        cda_result = await self.cda_strategy.augment(cda_request)
        augmented_texts.extend(cda_result.augmented_texts)
        quality_scores.extend(cda_result.quality_scores)
        changed_elements.extend([f"CDA: {change}" for change in cda_result.changed_elements])
        
        # Generate ADA variants
        ada_request = AugmentationRequest(
            text=request.text,
            strategy=AugmentationStrategy.ADA,
            num_variants=ada_variants,
            preserve_sentiment=request.preserve_sentiment,
            preserve_length=request.preserve_length,
            min_similarity=request.min_similarity,
            product=request.product
        )
        
        ada_result = await self.ada_strategy.augment(ada_request)
        augmented_texts.extend(ada_result.augmented_texts)
        quality_scores.extend(ada_result.quality_scores)
        changed_elements.extend([f"ADA: {change}" for change in ada_result.changed_elements])
        
        # Generate combined variants (apply both strategies sequentially)
        combined_variants = min(2, request.num_variants // 3) if request.num_variants > 3 else 0
        
        for i in range(combined_variants):
            try:
                # First apply CDA
                cda_intermediate = await self.cda_strategy._generate_context_paraphrase(
                    request.text, aspects, request.preserve_sentiment
                )
                
                if cda_intermediate and cda_intermediate != request.text:
                    # Then apply ADA to the CDA result
                    cda_aspects = self.ada_strategy._extract_aspects(cda_intermediate)
                    if cda_aspects:
                        aspect_to_replace = cda_aspects[0]
                        alternative = await self.ada_strategy._generate_aspect_alternative(
                            aspect_to_replace, cda_intermediate, request.product
                        )
                        
                        if alternative:
                            combined_variant = self.ada_strategy._replace_aspect_in_text(
                                cda_intermediate, aspect_to_replace, alternative
                            )
                            
                            # Validate combined variant
                            remaining_aspects = [a for a in aspects if a != aspect_to_replace]
                            is_valid, score = await self._validate_preservation(
                                request.text, combined_variant, remaining_aspects
                            )
                            
                            if is_valid and score >= request.min_similarity:
                                augmented_texts.append(combined_variant)
                                quality_scores.append(score)
                                changed_elements.append(f"CADA: context + aspect replacement")
            
            except Exception as e:
                logger.warning(f"CADA combined variant {i} generation failed: {e}")
                continue
        
        return AugmentationResult(
            original_text=request.text,
            augmented_texts=augmented_texts,
            strategy_used=AugmentationStrategy.CADA,
            quality_scores=quality_scores,
            preserved_aspects=preserved_aspects,
            changed_elements=changed_elements,
            metadata={
                'cda_variants': len(cda_result.augmented_texts),
                'ada_variants': len(ada_result.augmented_texts),
                'combined_variants': combined_variants,
                'total_variants': len(augmented_texts),
                'avg_quality_score': sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
            }
        )
    
    def _extract_aspects(self, text: str) -> List[str]:
        """Use the more comprehensive aspect extraction."""
        return self.cda_strategy._extract_aspects(text)


class DataAugmentationService:
    """
    Main service for advanced data augmentation with multiple strategies.
    
    Provides a unified interface to access CDA, ADA, and CADA augmentation strategies
    with quality validation and performance monitoring.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.strategies = {
            AugmentationStrategy.CDA: ContextFocusedAugmentation(),
            AugmentationStrategy.ADA: AspectFocusedAugmentation(),
            AugmentationStrategy.CADA: ContextAspectAugmentation()
        }
    
    async def augment_text(self, request: AugmentationRequest) -> AugmentationResult:
        """Augment text using the specified strategy."""
        try:
            if request.strategy not in self.strategies:
                raise ValueError(f"Unknown augmentation strategy: {request.strategy}")
            
            strategy = self.strategies[request.strategy]
            result = await strategy.augment(request)
            
            logger.info(
                f"Augmentation completed: {request.strategy.value}, "
                f"generated {len(result.augmented_texts)} variants, "
                f"avg quality: {result.metadata.get('avg_quality_score', 0.0):.3f}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Augmentation failed: {e}")
            raise
    
    async def augment_batch(self, 
                          texts: List[str], 
                          strategy: AugmentationStrategy,
                          **kwargs) -> List[AugmentationResult]:
        """Augment a batch of texts using the same strategy."""
        results = []
        
        for text in texts:
            request = AugmentationRequest(
                text=text,
                strategy=strategy,
                **kwargs
            )
            
            try:
                result = await self.augment_text(request)
                results.append(result)
            except Exception as e:
                logger.warning(f"Failed to augment text '{text[:50]}...': {e}")
                # Add empty result to maintain batch consistency
                results.append(AugmentationResult(
                    original_text=text,
                    augmented_texts=[],
                    strategy_used=strategy,
                    quality_scores=[],
                    preserved_aspects=[],
                    changed_elements=[],
                    metadata={'error': str(e)}
                ))
        
        return results
    
    async def create_augmented_samples(self, 
                                     original_sample: GeneratedSample,
                                     strategy: AugmentationStrategy,
                                     num_variants: int = 3) -> List[GeneratedSample]:
        """Create augmented GeneratedSample objects from an original sample."""
        request = AugmentationRequest(
            text=original_sample.text,
            strategy=strategy,
            num_variants=num_variants,
            product=original_sample.product
        )
        
        result = await self.augment_text(request)
        
        augmented_samples = []
        for i, (text, quality_score) in enumerate(zip(result.augmented_texts, result.quality_scores)):
            augmented_sample = GeneratedSample(
                id=str(uuid.uuid4()),
                product=original_sample.product,
                prompt_version=f"{original_sample.prompt_version}_aug_{strategy.value}",
                generated_at=datetime.now(timezone.utc),
                text=text,
                tokens_estimated=len(text.split()) * 1.3,  # Rough approximation
                temperature=original_sample.temperature,
                # Add augmentation metadata
                metadata={
                    'augmentation_strategy': strategy.value,
                    'quality_score': quality_score,
                    'original_sample_id': original_sample.id,
                    'variant_index': i,
                    'preserved_aspects': result.preserved_aspects,
                    'changed_elements': result.changed_elements
                }
            )
            augmented_samples.append(augmented_sample)
        
        return augmented_samples
    
    def get_strategy_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information about available augmentation strategies."""
        return {
            'CDA': {
                'name': 'Context-Focused Data Augmentation',
                'description': 'Changes contextual words while preserving aspect terms and sentiment polarity',
                'best_for': 'Increasing semantic richness and diversity while maintaining key aspects'
            },
            'ADA': {
                'name': 'Aspect-Focused Data Augmentation', 
                'description': 'Replaces aspect terms with semantically suitable alternatives',
                'best_for': 'Increasing diversity of aspect terms and improving model robustness'
            },
            'CADA': {
                'name': 'Context-Aspect Data Augmentation',
                'description': 'Combines both CDA and ADA strategies for maximum diversity',
                'best_for': 'Achieving best performance with comprehensive diversification'
            }
        }


# Global service instance
_augmentation_service: Optional[DataAugmentationService] = None


def get_augmentation_service() -> DataAugmentationService:
    """Get the global data augmentation service instance."""
    global _augmentation_service
    if _augmentation_service is None:
        _augmentation_service = DataAugmentationService()
    return _augmentation_service