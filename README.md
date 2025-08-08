# DataForge API

A FastAPI service for high-quality synthetic text generation using LLMs. Built for reliability and scalability.

## Highlights

- Async, distributed job processing with Celery + Redis (broker + result backend)
- Pluggable LLM client with OpenAI, Anthropic (stub), and Mock implementations
- Jinja2 prompt templates with versioning and enhanced prompting options
- Quality filtering, rate limiting, and data augmentation services
- Strong typing via Pydantic v2, clear separation of concerns, and test coverage

## Architecture

- API: FastAPI app (`app/main.py`, routes in `app/routers/`)
- Job queue: Celery workers (`app/celery_app.py`, tasks in `app/services/celery_tasks.py`)
- Broker/Backend: Redis (via Docker or local)
- Services: prompt rendering, quality filtering, augmentation, rate limiting (`app/services/`)
- LLM client: pluggable factory (`app/utils/llm_client.py`)
- Job management: `JobStore` abstraction wrapping Celery (`app/services/job_store.py`)

Key endpoints:
- `POST /api/generate` – create a generation job
- `POST /api/generate-enhanced` – few-shot, tone/sentiment controls, quality filtering
- `POST /api/generate-augmented` – apply CDA/ADA/CADA augmentation strategies
- `GET /api/result/{job_id}` – fetch job status/result
- `POST /api/validate` – validate a request and estimate cost
- `GET /api/health` – health of service and workers
- `GET /api/test-llm` – smoke test of configured LLM client

## Prerequisites

- Python 3.11+
- Redis 7+
- OpenAI API key (if not using the default Mock provider)

## Quickstart

### Option A: Docker Compose (recommended)

```bash
# From repository root
docker compose up --build -d

# Services
# - API:            http://localhost:8000
# - Flower (Celery): http://localhost:5555
# - Redis:          localhost:6379
```

To tail logs:
```bash
docker compose logs -f --tail=200
```

### Option B: Local development (virtualenv)

```bash
# 1) Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2) Install dependencies
pip install -r requirements.txt

# 3) Start Redis (Docker or local)
docker run -d -p 6379:6379 redis:7-alpine
# or: redis-server

# 4) Export environment (optional if using defaults)
export DEFAULT_LLM_PROVIDER=mock
export REDIS_URL=redis://localhost:6379/0

# 5) Start the API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Start background workers in separate terminals:
```bash
# Celery workers (example queues and concurrency)
celery -A app.celery_app worker --loglevel=info --queues=generation --concurrency=4 --hostname=generation-worker@%h
celery -A app.celery_app worker --loglevel=info --queues=augmentation --concurrency=2 --hostname=augmentation-worker@%h
celery -A app.celery_app worker --loglevel=info --queues=maintenance --concurrency=1 --hostname=maintenance-worker@%h

# Celery Beat (scheduled tasks)
celery -A app.celery_app beat --loglevel=info

# Flower (monitoring)
celery -A app.celery_app flower --port=5555 --broker=redis://localhost:6379/0
```

Convenience scripts are available under `scripts/` for local development.

## Configuration

Configuration is driven by environment variables (or a `.env` file). Defaults are provided in `app/config.py`.

```bash
# API
API_TITLE="DataForge API"
API_VERSION="1.0.0"
DEBUG=false

# Redis
REDIS_URL="redis://localhost:6379/0"

# Job Processing
MAX_SAMPLES_PER_REQUEST=50

# Celery
CELERY_WORKER_CONCURRENCY=4
CELERY_TASK_TIME_LIMIT=600
CELERY_TASK_SOFT_TIME_LIMIT=300

# LLM
DEFAULT_LLM_PROVIDER=openai   # openai | anthropic | mock
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4o
OPENAI_MAX_TOKENS=500
OPENAI_PROMPT_RATE_PER_1K=0.005
OPENAI_COMPLETION_RATE_PER_1K=0.015
```

## Usage

### 1) Create a job
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

### 2) Check job status
```bash
curl "http://localhost:8000/api/result/<job_id>"
```

### 3) Validate request (with cost estimate)
```bash
curl -X POST "http://localhost:8000/api/validate" \
  -H "Content-Type: application/json" \
  -d '{
    "product": "e-commerce platform",
    "count": 10
  }'
```

### 4) Enhanced and Augmented generation
```bash
# Enhanced (few-shot, tone, sentiment, quality filtering)
curl -X POST "http://localhost:8000/api/generate-enhanced" \
  -H "Content-Type: application/json" \
  -d '{
    "product": "CRM suite",
    "count": 3,
    "version": "v1",
    "temperature": 0.7
  }'

# Augmented (CDA/ADA/CADA)
curl -X POST "http://localhost:8000/api/generate-augmented?augmentation_strategies=CDA&augment_ratio=0.5" \
  -H "Content-Type: application/json" \
  -d '{
    "product": "analytics platform",
    "count": 3,
    "version": "v1",
    "temperature": 0.7
  }'
```

### 5) Health and LLM tests
```bash
curl "http://localhost:8000/api/health"
curl -X POST "http://localhost:8000/api/test-llm"
```

## Project Structure

```
app/
  main.py                 # FastAPI app factory and wiring
  celery_app.py           # Celery app setup (queues, beat, flower)
  routers/
    generation.py         # API endpoints
  services/
    celery_service.py     # Celery job service (wraps task submission/status)
    celery_tasks.py       # Celery tasks (generation, enhanced, augmented)
    job_store.py          # Unified job store abstraction over Celery
    quality_service.py    # Quality filtering and scoring
    data_augmentation_service.py
    rate_limiting_service.py
    prompt_service.py
    generation_service.py
  utils/
    llm_client.py         # LLM client interface + implementations
    token_utils.py        # Token and cost estimation
  templates/              # Jinja2 templates
```

## Testing

```bash
# Install dev dependencies
pip install -r requirements.txt

# Run tests
pytest

# With coverage
pytest --cov=app tests/
```

The suite includes tests for API routes, `JobStore`, token utilities, rate limiting, augmentation, and quality filtering.

## Observability & Operations

- Flower dashboard at `http://localhost:5555` for Celery
- Centralized logging to stdout (container-friendly)
- Health endpoint at `/api/health`

## Design Notes

- `JobStore` abstracts job creation/status/cancel and defers to Celery
- LLM client is pluggable; the Mock client is default-friendly for local dev
- Quality filtering performs length checks, deduplication, and heuristic scoring; can be tuned via `QualityFilterConfig`
- Rate limiter supports header parsing and token/request buckets

## Contributing

1. Create a feature branch: `git checkout -b feature/name`
2. Make changes with tests
3. Run `pytest`
4. Open a PR

## License

MIT
