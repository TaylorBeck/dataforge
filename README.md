# DataForge API

A modern, production-ready FastAPI service for synthetic text data generation using Large Language Models (LLMs). Built for AI researchers, ML engineers, and developers who need high-quality, structured synthetic datasets.

## 🚀 Features

- **Async Job Processing**: Non-blocking generation with Redis-backed job queue
- **Pluggable LLM Support**: OpenAI GPT-4, Anthropic Claude, and mock providers
- **Jinja2 Templating**: Flexible prompt templates with versioning
- **Rich Metadata**: Every sample includes unique ID, timestamps, and token estimates
- **Batch Generation**: Concurrent processing for optimal performance
- **Production Ready**: Comprehensive error handling, logging, and monitoring
- **Type Safe**: Full Pydantic validation and type hints
- **Extensible**: Modular architecture for easy customization

## 📋 Requirements

- Python 3.8+
- Redis (for job management)
- OpenAI API key (or configure alternative LLM)

## 🛠️ Installation

1. **Clone the repository**:
```bash
git clone <repository-url>
cd dataforge
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

3. **Set up environment variables**:
```bash
# Create .env file
cp .env.example .env

# Edit .env with your configuration
OPENAI_API_KEY=your_openai_api_key_here
REDIS_URL=redis://localhost:6379/0
DEBUG=true
```

4. **Start Redis** (if not already running):
```bash
# Using Docker
docker run -d -p 6379:6379 redis:7-alpine

# Or using local Redis
redis-server
```

5. **Run the application**:
```bash
# Development mode
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or using the main script
python app/main.py
```

## 🔧 Configuration

Configuration is managed through environment variables and a `.env` file:

```bash
# API Configuration
API_TITLE="DataForge API"
API_VERSION="1.0.0"
DEBUG=false

# Redis Configuration
REDIS_URL="redis://localhost:6379/0"
REDIS_JOB_EXPIRE_SECONDS=3600
REDIS_RESULT_EXPIRE_SECONDS=7200

# Job Processing
MAX_SAMPLES_PER_REQUEST=50
MAX_CONCURRENT_JOBS=10
JOB_TIMEOUT_SECONDS=300

# LLM Configuration
OPENAI_API_KEY="your_key_here"
OPENAI_MODEL="gpt-4"
OPENAI_MAX_TOKENS=500
DEFAULT_LLM_PROVIDER="openai"  # openai, anthropic, mock

# Template Configuration
PROMPT_TEMPLATE_DIR="app/templates"
DEFAULT_PROMPT_TEMPLATE="support_request.j2"
```

## 📚 API Usage

### 1. Generate Synthetic Data

**POST** `/api/generate`

```bash
curl -X POST "http://localhost:8000/api/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "product": "mobile banking app",
    "count": 5,
    "version": "v1",
    "temperature": 0.7
  }'
```

**Response**:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z",
  "error_message": null,
  "result": null,
  "progress": null
}
```

### 2. Check Job Status

**GET** `/api/result/{job_id}`

```bash
curl "http://localhost:8000/api/result/550e8400-e29b-41d4-a716-446655440000"
```

**Response** (when completed):
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:31:30Z",
  "error_message": null,
  "result": {
    "samples": [
      {
        "id": "sample-uuid-1",
        "product": "mobile banking app",
        "prompt_version": "v1",
        "generated_at": "2024-01-15T10:31:15Z",
        "text": "I'm experiencing issues with your mobile banking app...",
        "tokens_estimated": 87,
        "temperature": 0.7
      }
    ],
    "total_samples": 5,
    "total_tokens_estimated": 435
  },
  "progress": 100
}
```

### 3. Health Check

**GET** `/api/health`

```bash
curl "http://localhost:8000/api/health"
```

### 4. System Statistics

**GET** `/api/stats`

```bash
curl "http://localhost:8000/api/stats"
```

### 5. Validate Request

**POST** `/api/validate`

```bash
curl -X POST "http://localhost:8000/api/validate" \
  -H "Content-Type: application/json" \
  -d '{
    "product": "e-commerce platform",
    "count": 10
  }'
```

## 🎨 Custom Templates

Create custom Jinja2 templates in `app/templates/`:

```jinja2
<!-- app/templates/custom_prompt.j2 -->
You are a {{ role }} writing about {{ product }}.

Context: {{ context }}
Tone: {{ tone }}

Write your response:
```

Use in requests:
```python
# Update DEFAULT_PROMPT_TEMPLATE in config
DEFAULT_PROMPT_TEMPLATE="custom_prompt.j2"
```

## 🔌 Adding New LLM Providers

1. **Implement the interface**:

```python
# app/utils/llm_client.py
class CustomLLMClient(LLMClientInterface):
    async def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = None) -> str:
        # Your implementation
        pass
    
    async def get_model_info(self) -> Dict[str, Any]:
        return {"provider": "custom", "model": "custom-model"}
    
    async def health_check(self) -> bool:
        # Check service availability
        return True
```

2. **Register in factory**:

```python
def get_llm_client(provider: str = None) -> LLMClientInterface:
    if provider == "custom":
        return CustomLLMClient()
    # ... existing providers
```

## 🧪 Testing

Run the test suite:

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov httpx

# Run tests
pytest

# Run with coverage
pytest --cov=app tests/

# Run specific test file
pytest tests/test_generation.py
```

Example test:

```python
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_generate_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/api/generate", json={
            "product": "test product",
            "count": 1
        })
    assert response.status_code == 200
    assert "job_id" in response.json()
```

## 🚀 Production Deployment

### Using Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Using Gunicorn

```bash
pip install gunicorn
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Environment Variables for Production

```bash
DEBUG=false
REDIS_URL=redis://production-redis:6379/0
OPENAI_API_KEY=prod_key_here
MAX_CONCURRENT_JOBS=20
LOG_LEVEL=info
```

## 🔧 Extensions

### Adding Celery Queue

Replace the built-in job manager with Celery for distributed processing:

```python
# celery_app.py
from celery import Celery

celery_app = Celery(
    "dataforge",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0"
)

@celery_app.task
async def run_generation_task(request_data: dict, job_id: str):
    # Move generation logic here
    pass
```

### Adding Authentication

```python
# app/auth.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def verify_token(token: str = Depends(security)):
    # Implement token verification
    if not valid_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    return token

# Use in routes
@router.post("/generate", dependencies=[Depends(verify_token)])
async def create_generation_job(...):
    pass
```

### Adding Rate Limiting

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@router.post("/generate")
@limiter.limit("10/minute")
async def create_generation_job(request: Request, ...):
    pass
```

## 📊 Monitoring

The API provides several monitoring endpoints:

- `/api/health` - Service health status
- `/api/stats` - System statistics
- `/api/test-llm` - LLM connectivity test

For production monitoring, integrate with:
- **Prometheus** for metrics
- **Grafana** for dashboards  
- **Sentry** for error tracking
- **ELK Stack** for log aggregation

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes with tests
4. Run the test suite: `pytest`
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

- **Documentation**: Check the `/docs` endpoint when running in debug mode
- **Issues**: Report bugs and feature requests via GitHub Issues
- **Discussions**: Join the community discussions for questions and ideas