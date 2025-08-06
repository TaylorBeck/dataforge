"""
Quality filtering and scoring service for generated text samples.

Provides deduplication, quality scoring, and validation for synthetic training data.
"""
import logging
import re
import hashlib
from typing import Dict, List, Set, Tuple, Any, Optional
from dataclasses import dataclass, field
from collections import Counter
import asyncio
from datetime import datetime, timezone

from app.models.schemas import GeneratedSample
from app.utils.llm_client import get_llm_client, LLMException

logger = logging.getLogger(__name__)


@dataclass
class QualityMetrics:
    """Quality metrics for a generated sample."""
    overall_score: float
    length_score: float
    coherence_score: float
    relevance_score: float
    grammar_score: float
    diversity_score: float
    uniqueness_score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QualityFilterConfig:
    """Configuration for quality filtering."""
    min_overall_score: float = 0.6
    min_length_words: int = 10
    max_length_words: int = 500
    enable_deduplication: bool = True
    similarity_threshold: float = 0.85
    check_grammar: bool = True
    check_coherence: bool = True
    batch_size: int = 50


class TextDeduplicator:
    """Handles text deduplication using multiple strategies."""
    
    def __init__(self, similarity_threshold: float = 0.85):
        self.similarity_threshold = similarity_threshold
        self._seen_hashes: Set[str] = set()
        self._seen_normalized: Set[str] = set()
    
    def normalize_text(self, text: str) -> str:
        """Normalize text for comparison."""
        # Convert to lowercase, remove extra whitespace, punctuation
        normalized = re.sub(r'[^\w\s]', '', text.lower())
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized
    
    def get_text_hash(self, text: str) -> str:
        """Get a hash of the text for exact duplicate detection."""
        normalized = self.normalize_text(text)
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def is_duplicate(self, text: str) -> Tuple[bool, str]:
        """
        Check if text is a duplicate.
        
        Returns:
            (is_duplicate, reason)
        """
        # Check exact duplicates
        text_hash = self.get_text_hash(text)
        if text_hash in self._seen_hashes:
            return True, "exact_duplicate"
        
        # Check normalized duplicates
        normalized = self.normalize_text(text)
        if normalized in self._seen_normalized:
            return True, "normalized_duplicate"
        
        # Check semantic similarity (simplified version)
        if self._check_semantic_similarity(normalized):
            return True, "semantic_similarity"
        
        return False, ""
    
    def add_text(self, text: str) -> None:
        """Add text to the seen set."""
        text_hash = self.get_text_hash(text)
        normalized = self.normalize_text(text)
        
        self._seen_hashes.add(text_hash)
        self._seen_normalized.add(normalized)
    
    def _check_semantic_similarity(self, normalized_text: str) -> bool:
        """Simple semantic similarity check using word overlap."""
        words = set(normalized_text.split())
        
        # Check against existing normalized texts
        for seen_text in self._seen_normalized:
            seen_words = set(seen_text.split())
            
            # Calculate Jaccard similarity
            intersection = len(words.intersection(seen_words))
            union = len(words.union(seen_words))
            
            if union == 0:
                continue
                
            jaccard_similarity = intersection / union
            if jaccard_similarity >= self.similarity_threshold:
                return True
        
        return False
    
    def get_stats(self) -> Dict[str, int]:
        """Get deduplication statistics."""
        return {
            "total_seen": len(self._seen_hashes),
            "unique_normalized": len(self._seen_normalized)
        }


class QualityScorer:
    """Scores generated text quality using multiple metrics."""
    
    def __init__(self):
        self.deduplicator = TextDeduplicator()
    
    async def score_sample(self, sample: GeneratedSample, 
                          context: Optional[Dict[str, Any]] = None) -> QualityMetrics:
        """
        Calculate comprehensive quality scores for a sample.
        
        Args:
            sample: Generated sample to score
            context: Additional context for scoring
            
        Returns:
            Quality metrics
        """
        text = sample.text
        
        # Calculate individual scores
        length_score = self._score_length(text)
        coherence_score = await self._score_coherence(text)
        relevance_score = self._score_relevance(text, sample.product, context)
        grammar_score = self._score_grammar(text)
        diversity_score = self._score_diversity(text)
        uniqueness_score = self._score_uniqueness(text)
        
        # Calculate weighted overall score
        weights = {
            "length": 0.15,
            "coherence": 0.25,
            "relevance": 0.25,
            "grammar": 0.15,
            "diversity": 0.10,
            "uniqueness": 0.10
        }
        
        overall_score = (
            length_score * weights["length"] +
            coherence_score * weights["coherence"] +
            relevance_score * weights["relevance"] +
            grammar_score * weights["grammar"] +
            diversity_score * weights["diversity"] +
            uniqueness_score * weights["uniqueness"]
        )
        
        return QualityMetrics(
            overall_score=overall_score,
            length_score=length_score,
            coherence_score=coherence_score,
            relevance_score=relevance_score,
            grammar_score=grammar_score,
            diversity_score=diversity_score,
            uniqueness_score=uniqueness_score,
            metadata={
                "word_count": len(text.split()),
                "char_count": len(text),
                "sentence_count": len(re.split(r'[.!?]+', text)),
                "weights_used": weights
            }
        )
    
    def _score_length(self, text: str) -> float:
        """Score based on text length appropriateness."""
        word_count = len(text.split())
        
        # Optimal range varies by type, but generally 50-200 words
        if 50 <= word_count <= 200:
            return 1.0
        elif 30 <= word_count < 50:
            return 0.8
        elif 200 < word_count <= 300:
            return 0.8
        elif 20 <= word_count < 30:
            return 0.6
        elif 300 < word_count <= 400:
            return 0.6
        elif 10 <= word_count < 20:
            return 0.4
        elif 400 < word_count <= 500:
            return 0.4
        else:
            return 0.2  # Too short or too long
    
    async def _score_coherence(self, text: str) -> float:
        """Score text coherence using LLM evaluation."""
        try:
            llm_client = get_llm_client()
            
            prompt = f"""
            Rate the coherence of this text on a scale of 0.0 to 1.0:
            
            Text: "{text}"
            
            Consider:
            - Logical flow of ideas
            - Sentence structure and clarity
            - Overall readability
            - Consistency of tone
            
            Respond with only a number between 0.0 and 1.0:
            """
            
            response = await llm_client.generate(prompt, temperature=0.0, max_tokens=10)
            
            # Extract numeric score
            score_match = re.search(r'(\d+\.?\d*)', response.strip())
            if score_match:
                score = float(score_match.group(1))
                return min(max(score, 0.0), 1.0)
            
            return 0.7  # Default if parsing fails
            
        except Exception as e:
            logger.warning(f"Coherence scoring failed: {e}")
            return 0.7  # Default score
    
    def _score_relevance(self, text: str, product: str, 
                        context: Optional[Dict[str, Any]] = None) -> float:
        """Score relevance to the product/context."""
        if not product:
            return 0.5
        
        text_lower = text.lower()
        product_lower = product.lower()
        
        # Check if product is mentioned
        product_mentioned = product_lower in text_lower
        
        # Check for relevant keywords based on context
        relevant_keywords = []
        if context and context.get('template_type'):
            template_type = context['template_type']
            if 'support' in template_type:
                relevant_keywords = ['issue', 'problem', 'help', 'support', 'fix', 'error']
            elif 'review' in template_type:
                relevant_keywords = ['recommend', 'experience', 'quality', 'rating', 'using']
            elif 'feature' in template_type:
                relevant_keywords = ['feature', 'improvement', 'add', 'enhance', 'would like']
        
        keyword_score = sum(1 for keyword in relevant_keywords if keyword in text_lower)
        keyword_score = min(keyword_score / max(len(relevant_keywords), 1), 1.0)
        
        # Combine scores
        if product_mentioned:
            return min(0.8 + keyword_score * 0.2, 1.0)
        else:
            return keyword_score * 0.6  # Lower score if product not mentioned
    
    def _score_grammar(self, text: str) -> float:
        """Basic grammar scoring using heuristics."""
        issues = 0
        total_checks = 0
        
        # Check capitalization
        sentences = re.split(r'[.!?]+', text)
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence:
                total_checks += 1
                if not sentence[0].isupper():
                    issues += 1
        
        # Check for basic punctuation
        total_checks += 1
        if not re.search(r'[.!?]$', text.strip()):
            issues += 1
        
        # Check for excessive repetition
        words = text.lower().split()
        word_counts = Counter(words)
        for count in word_counts.values():
            if count > 5:  # Word repeated more than 5 times
                issues += 1
                total_checks += 1
        
        # Calculate score
        if total_checks == 0:
            return 0.5
        
        error_rate = issues / total_checks
        return max(1.0 - error_rate, 0.0)
    
    def _score_diversity(self, text: str) -> float:
        """Score lexical diversity."""
        words = re.findall(r'\b\w+\b', text.lower())
        if len(words) <= 1:
            return 0.0
        
        unique_words = len(set(words))
        total_words = len(words)
        
        # Type-Token Ratio
        diversity = unique_words / total_words
        
        # Normalize to 0-1 scale (TTR of 0.7+ is considered good)
        return min(diversity / 0.7, 1.0)
    
    def _score_uniqueness(self, text: str) -> float:
        """Score how unique the text is compared to seen samples."""
        is_duplicate, reason = self.deduplicator.is_duplicate(text)
        
        if is_duplicate:
            if reason == "exact_duplicate":
                return 0.0
            elif reason == "normalized_duplicate":
                return 0.2
            elif reason == "semantic_similarity":
                return 0.5
        
        return 1.0


class QualityFilterService:
    """Main service for quality filtering and validation."""
    
    def __init__(self, config: Optional[QualityFilterConfig] = None):
        self.config = config or QualityFilterConfig()
        self.scorer = QualityScorer()
        self.deduplicator = TextDeduplicator(self.config.similarity_threshold)
        
        # Statistics
        self.stats = {
            "total_processed": 0,
            "passed_filter": 0,
            "failed_length": 0,
            "failed_quality": 0,
            "failed_duplicate": 0
        }
    
    async def filter_samples(self, samples: List[GeneratedSample],
                           context: Optional[Dict[str, Any]] = None) -> Tuple[List[GeneratedSample], List[QualityMetrics]]:
        """
        Filter samples based on quality criteria.
        
        Args:
            samples: List of samples to filter
            context: Additional context for filtering
            
        Returns:
            (filtered_samples, quality_metrics_for_passed_samples)
        """
        filtered_samples = []
        quality_metrics = []
        
        for sample in samples:
            self.stats["total_processed"] += 1
            
            # Check length first (quick filter)
            word_count = len(sample.text.split())
            if word_count < self.config.min_length_words or word_count > self.config.max_length_words:
                self.stats["failed_length"] += 1
                logger.debug(f"Sample failed length check: {word_count} words")
                continue
            
            # Check for duplicates
            if self.config.enable_deduplication:
                is_duplicate, reason = self.deduplicator.is_duplicate(sample.text)
                if is_duplicate:
                    self.stats["failed_duplicate"] += 1
                    logger.debug(f"Sample failed duplicate check: {reason}")
                    continue
            
            # Score quality
            try:
                metrics = await self.scorer.score_sample(sample, context)
                
                # Check if meets minimum quality threshold
                if metrics.overall_score >= self.config.min_overall_score:
                    filtered_samples.append(sample)
                    quality_metrics.append(metrics)
                    self.stats["passed_filter"] += 1
                    
                    # Add to deduplicator for future checks
                    if self.config.enable_deduplication:
                        self.deduplicator.add_text(sample.text)
                else:
                    self.stats["failed_quality"] += 1
                    logger.debug(f"Sample failed quality check: {metrics.overall_score:.3f} < {self.config.min_overall_score}")
                    
            except Exception as e:
                logger.warning(f"Quality scoring failed for sample: {e}")
                self.stats["failed_quality"] += 1
                continue
        
        logger.info(f"Quality filtering complete: {len(filtered_samples)}/{len(samples)} samples passed")
        return filtered_samples, quality_metrics
    
    async def filter_batch(self, samples: List[GeneratedSample],
                          context: Optional[Dict[str, Any]] = None) -> Tuple[List[GeneratedSample], List[QualityMetrics]]:
        """Filter samples in batches for better performance."""
        if len(samples) <= self.config.batch_size:
            return await self.filter_samples(samples, context)
        
        all_filtered = []
        all_metrics = []
        
        # Process in batches
        for i in range(0, len(samples), self.config.batch_size):
            batch = samples[i:i + self.config.batch_size]
            filtered_batch, metrics_batch = await self.filter_samples(batch, context)
            all_filtered.extend(filtered_batch)
            all_metrics.extend(metrics_batch)
        
        return all_filtered, all_metrics
    
    def get_filter_stats(self) -> Dict[str, Any]:
        """Get filtering statistics."""
        total = self.stats["total_processed"]
        if total == 0:
            return self.stats
        
        return {
            **self.stats,
            "pass_rate": self.stats["passed_filter"] / total,
            "length_failure_rate": self.stats["failed_length"] / total,
            "quality_failure_rate": self.stats["failed_quality"] / total,
            "duplicate_failure_rate": self.stats["failed_duplicate"] / total,
            "deduplication_stats": self.deduplicator.get_stats()
        }
    
    def reset_stats(self) -> None:
        """Reset filtering statistics."""
        self.stats = {
            "total_processed": 0,
            "passed_filter": 0,
            "failed_length": 0,
            "failed_quality": 0,
            "failed_duplicate": 0
        }


# Global service instance
_quality_service: Optional[QualityFilterService] = None


def get_quality_service(config: Optional[QualityFilterConfig] = None) -> QualityFilterService:
    """Get or create global quality service instance."""
    global _quality_service
    if _quality_service is None:
        _quality_service = QualityFilterService(config)
    return _quality_service


def reset_quality_service():
    """Reset global quality service (useful for testing)."""
    global _quality_service
    _quality_service = None