# DataForge API - Extensions and Customization Guide

This guide covers how to extend and customize the DataForge API for advanced use cases.

## 🧩 Adding New LLM Providers

### 1. Implement the LLM Client Interface

```python
# app/utils/llm_client.py

class CustomLLMClient(LLMClientInterface):
    """Custom LLM provider implementation."""
    
    def __init__(self, api_key: str, model: str = "custom-model"):
        self.api_key = api_key
        self.model = model
        # Initialize your client here
    
    async def generate(
        self, 
        prompt: str, 
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        """Generate text using your custom LLM."""
        try:
            # Your LLM API call here
            response = await your_llm_api_call(
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.text
        except Exception as e:
            raise LLMException(f"Custom LLM generation failed: {e}")
    
    async def get_model_info(self) -> Dict[str, Any]:
        return {
            "provider": "custom",
            "model": self.model,
            "api_version": "1.0"
        }
    
    async def health_check(self) -> bool:
        try:
            # Test API connectivity
            await self.generate("test", temperature=0.1, max_tokens=1)
            return True
        except:
            return False
```

### 2. Register the Provider

```python
# app/utils/llm_client.py - Update get_llm_client function

def get_llm_client(provider: Optional[str] = None) -> LLMClientInterface:
    settings = get_settings()
    provider = provider or settings.default_llm_provider
    
    if provider == "custom":
        if not settings.custom_api_key:  # Add to config.py
            logger.warning("Custom API key not found, falling back to mock")
            return MockLLMClient()
        return CustomLLMClient(
            api_key=settings.custom_api_key,
            model=settings.custom_model
        )
    # ... existing providers
```

### 3. Add Configuration

```python
# app/config.py - Add to Settings class

# Custom LLM Configuration
custom_api_key: Optional[str] = Field(None, description="Custom LLM API key")
custom_model: str = Field("custom-model", description="Custom model name")
custom_base_url: Optional[str] = Field(None, description="Custom API base URL")
```

## 🎨 Custom Prompt Templates

### 1. Create Template Files

```jinja2
<!-- app/templates/chatbot_conversation.j2 -->
You are a helpful {{ role }} chatbot for {{ company }}.

Customer context:
- Product: {{ product }}
- Issue type: {{ issue_type }}
- Customer sentiment: {{ sentiment }}

Previous conversation:
{% for message in conversation_history %}
{{ message.role }}: {{ message.content }}
{% endfor %}

Generate a natural, helpful response:
```

```jinja2
<!-- app/templates/product_review.j2 -->
Write a {{ star_rating }}-star review for {{ product }}.

Review criteria:
- Product category: {{ category }}
- Price range: {{ price_range }}
- Key features mentioned: {{ features | join(", ") }}
- Reviewer profile: {{ reviewer_type }}
- Review length: {{ length }} words

Review:
```

### 2. Create Template Service Extensions

```python
# app/services/prompt_service.py - Add template helpers

def get_template_variations(base_template: str) -> List[str]:
    """Get all variations of a template."""
    template_dir = get_template_service().template_dir
    variations = []
    
    base_name = base_template.replace('.j2', '')
    for template_file in template_dir.glob(f"{base_name}*.j2"):
        variations.append(template_file.name)
    
    return variations

def render_with_context_validation(
    template_name: str,
    context: Dict[str, Any]
) -> Tuple[str, List[str]]:
    """Render template with context validation."""
    service = get_template_service()
    validation = service.validate_template(template_name)
    
    missing_vars = []
    for var in validation.get('variables', []):
        if var not in context:
            missing_vars.append(var)
    
    if missing_vars:
        # Provide defaults or raise error
        logger.warning(f"Missing template variables: {missing_vars}")
    
    rendered = service.render_template(template_name, context)
    return rendered, missing_vars
```

## 🔄 Queue System Extensions

### 1. Replace with Celery

```python
# celery_app.py
from celery import Celery
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "dataforge",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "app.tasks.run_generation_task": {"queue": "generation"},
        "app.tasks.cleanup_task": {"queue": "maintenance"},
    }
)
```

```python
# app/tasks.py
from celery import current_task
from celery_app import celery_app
from app.services.generation_service import get_generation_service

@celery_app.task(bind=True)
def run_generation_task(self, request_data: dict, job_id: str):
    """Celery task for generation."""
    try:
        # Update progress
        def update_progress(progress: int):
            current_task.update_state(
                state="PROGRESS",
                meta={"progress": progress, "job_id": job_id}
            )
        
        # Run generation
        service = get_generation_service()
        # Implementation here...
        
    except Exception as exc:
        current_task.update_state(
            state="FAILURE",
            meta={"error": str(exc), "job_id": job_id}
        )
        raise
```

### 2. Add Priority Queues

```python
# app/models/schemas.py - Add to GenerationRequest

priority: int = Field(
    1, 
    ge=1, 
    le=5, 
    description="Job priority (1=low, 5=high)"
)
```

```python
# app/services/job_manager.py - Update create_job

async def create_job(self, request: GenerationRequest) -> str:
    # ... existing code ...
    
    # Add to priority queue
    priority_score = request.priority * 1000 + int(time.time())
    await self.redis_client.zadd(
        "dataforge:priority_queue",
        {job_id: priority_score}
    )
```

## 🔐 Authentication & Authorization

### 1. API Key Authentication

```python
# app/auth.py
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import hashlib
import hmac

security = HTTPBearer()

class APIKeyManager:
    def __init__(self):
        self.api_keys = {
            "user_123": {
                "key_hash": "hashed_api_key",
                "rate_limit": 100,
                "permissions": ["generate", "read"]
            }
        }
    
    def verify_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        """Verify API key and return user info."""
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        for user_id, user_data in self.api_keys.items():
            if hmac.compare_digest(user_data["key_hash"], key_hash):
                return {"user_id": user_id, **user_data}
        
        return None

api_key_manager = APIKeyManager()

async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> Dict[str, Any]:
    """Verify API key from Authorization header."""
    user_info = api_key_manager.verify_api_key(credentials.credentials)
    
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    
    return user_info
```

### 2. Rate Limiting

```python
# app/middleware/rate_limit.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)

# In app/main.py
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# In routes
@router.post("/generate")
@limiter.limit("10/minute")
async def create_generation_job(
    request: Request,
    generation_request: GenerationRequest,
    user: dict = Depends(verify_api_key)
):
    # Custom rate limit based on user tier
    user_limit = f"{user.get('rate_limit', 10)}/minute"
    limiter.limit(user_limit)(create_generation_job)
    # ... rest of implementation
```

## 📊 Advanced Monitoring

### 1. Prometheus Metrics

```python
# app/monitoring.py
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry
import time

# Create registry
registry = CollectorRegistry()

# Metrics
REQUEST_COUNT = Counter(
    'dataforge_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status'],
    registry=registry
)

REQUEST_DURATION = Histogram(
    'dataforge_request_duration_seconds',
    'HTTP request duration',
    ['method', 'endpoint'],
    registry=registry
)

ACTIVE_JOBS = Gauge(
    'dataforge_active_jobs',
    'Number of active generation jobs',
    registry=registry
)

LLM_REQUESTS = Counter(
    'dataforge_llm_requests_total',
    'Total LLM API requests',
    ['provider', 'model', 'status'],
    registry=registry
)

LLM_TOKENS = Counter(
    'dataforge_llm_tokens_total',
    'Total LLM tokens generated',
    ['provider', 'model'],
    registry=registry
)

# Middleware
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = time.time()
    
    response = await call_next(request)
    
    duration = time.time() - start_time
    REQUEST_DURATION.labels(
        method=request.method,
        endpoint=request.url.path
    ).observe(duration)
    
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()
    
    return response

# Metrics endpoint
from prometheus_client import generate_latest

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(registry), media_type="text/plain")
```

### 2. Structured Logging

```python
# app/logging_config.py
import structlog
import logging
from pythonjsonlogger import jsonlogger

def configure_logging():
    """Configure structured logging."""
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Configure standard library logging
    formatter = jsonlogger.JsonFormatter()
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

# Usage in services
logger = structlog.get_logger()

async def generate_with_job_tracking(self, request, job_id):
    logger.info(
        "Generation started",
        job_id=job_id,
        product=request.product,
        count=request.count,
        temperature=request.temperature
    )
    # ... implementation
```

## 🎯 Custom Data Processing

### 1. Post-Processing Filters

```python
# app/services/processing_service.py
from typing import List, Dict, Any
import re
from textblob import TextBlob

class DataProcessor:
    """Post-processing service for generated data."""
    
    async def apply_filters(
        self, 
        samples: List[GeneratedSample], 
        filters: Dict[str, Any]
    ) -> List[GeneratedSample]:
        """Apply filters to generated samples."""
        
        filtered_samples = samples
        
        # Length filter
        if "min_length" in filters:
            filtered_samples = [
                s for s in filtered_samples 
                if len(s.text.split()) >= filters["min_length"]
            ]
        
        if "max_length" in filters:
            filtered_samples = [
                s for s in filtered_samples 
                if len(s.text.split()) <= filters["max_length"]
            ]
        
        # Sentiment filter
        if "sentiment" in filters:
            target_sentiment = filters["sentiment"]
            filtered_samples = [
                s for s in filtered_samples
                if self._check_sentiment(s.text, target_sentiment)
            ]
        
        # Content filter
        if "required_keywords" in filters:
            keywords = filters["required_keywords"]
            filtered_samples = [
                s for s in filtered_samples
                if any(keyword.lower() in s.text.lower() for keyword in keywords)
            ]
        
        # Deduplication
        if filters.get("deduplicate", False):
            filtered_samples = self._deduplicate(filtered_samples)
        
        return filtered_samples
    
    def _check_sentiment(self, text: str, target: str) -> bool:
        """Check if text matches target sentiment."""
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity
        
        if target == "positive" and polarity > 0.1:
            return True
        elif target == "negative" and polarity < -0.1:
            return True
        elif target == "neutral" and abs(polarity) <= 0.1:
            return True
        
        return False
    
    def _deduplicate(self, samples: List[GeneratedSample]) -> List[GeneratedSample]:
        """Remove duplicate samples."""
        seen_texts = set()
        unique_samples = []
        
        for sample in samples:
            text_normalized = re.sub(r'\s+', ' ', sample.text.lower().strip())
            if text_normalized not in seen_texts:
                seen_texts.add(text_normalized)
                unique_samples.append(sample)
        
        return unique_samples
```

### 2. Quality Scoring

```python
# app/services/quality_service.py
class QualityScorer:
    """Service for scoring generated text quality."""
    
    def score_sample(self, sample: GeneratedSample) -> Dict[str, float]:
        """Calculate quality scores for a sample."""
        text = sample.text
        
        scores = {
            "length_score": self._score_length(text),
            "coherence_score": self._score_coherence(text),
            "relevance_score": self._score_relevance(text, sample.product),
            "grammar_score": self._score_grammar(text),
            "diversity_score": self._score_diversity(text)
        }
        
        # Overall score (weighted average)
        weights = {
            "length_score": 0.1,
            "coherence_score": 0.3,
            "relevance_score": 0.3,
            "grammar_score": 0.2,
            "diversity_score": 0.1
        }
        
        overall_score = sum(
            scores[metric] * weight 
            for metric, weight in weights.items()
        )
        
        scores["overall_score"] = overall_score
        return scores
    
    def _score_length(self, text: str) -> float:
        """Score based on text length."""
        word_count = len(text.split())
        # Optimal range: 50-150 words
        if 50 <= word_count <= 150:
            return 1.0
        elif word_count < 50:
            return word_count / 50
        else:
            return max(0.5, 150 / word_count)
    
    def _score_coherence(self, text: str) -> float:
        """Score text coherence."""
        sentences = text.split('.')
        if len(sentences) < 2:
            return 0.5
        
        # Simple coherence: check for transition words
        transition_words = ['however', 'therefore', 'moreover', 'furthermore', 'additionally']
        transition_count = sum(
            1 for word in transition_words 
            if word in text.lower()
        )
        
        return min(1.0, 0.5 + (transition_count * 0.2))
    
    # ... implement other scoring methods
```

## 🔧 Database Extensions

### 1. PostgreSQL Integration

```python
# app/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, String, DateTime, Text, Integer, Float
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class GenerationJob(Base):
    """Database model for generation jobs."""
    __tablename__ = "generation_jobs"
    
    id = Column(String, primary_key=True)
    status = Column(String, nullable=False)
    product = Column(String, nullable=False)
    count = Column(Integer, nullable=False)
    temperature = Column(Float, nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    error_message = Column(Text)

class GeneratedSample(Base):
    """Database model for generated samples."""
    __tablename__ = "generated_samples"
    
    id = Column(String, primary_key=True)
    job_id = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    tokens_estimated = Column(Integer, nullable=False)
    quality_score = Column(Float)
    created_at = Column(DateTime, nullable=False)

# Database setup
engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/dataforge")
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

## 🚀 Performance Optimizations

### 1. Caching Layer

```python
# app/cache.py
import json
from typing import Optional, Any
import redis.asyncio as redis
from app.config import get_settings

class CacheService:
    """Redis-based caching service."""
    
    def __init__(self):
        settings = get_settings()
        self.redis = redis.from_url(
            settings.redis_url.replace('/0', '/1'),  # Use different DB
            decode_responses=True
        )
        self.default_ttl = 3600  # 1 hour
    
    async def get(self, key: str) -> Optional[Any]:
        """Get cached value."""
        try:
            value = await self.redis.get(f"cache:{key}")
            return json.loads(value) if value else None
        except Exception:
            return None
    
    async def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """Set cached value."""
        try:
            await self.redis.setex(
                f"cache:{key}",
                ttl or self.default_ttl,
                json.dumps(value)
            )
            return True
        except Exception:
            return False
    
    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate keys matching pattern."""
        keys = await self.redis.keys(f"cache:{pattern}")
        if keys:
            return await self.redis.delete(*keys)
        return 0

# Usage in services
cache = CacheService()

async def get_cached_generation(prompt_hash: str) -> Optional[str]:
    """Get cached generation result."""
    return await cache.get(f"generation:{prompt_hash}")

async def cache_generation(prompt_hash: str, result: str):
    """Cache generation result."""
    await cache.set(f"generation:{prompt_hash}", result, ttl=7200)
```

This comprehensive extension guide provides the foundation for customizing DataForge API for specific needs, from adding new LLM providers to implementing advanced monitoring and caching systems.