Design and implement a modern, production-ready Python FastAPI service for synthetic text data generation using LLMs (e.g., OpenAI, Anthropic, OSS LLMs) with the following requirements:

Core Features:
Expose an HTTP API with:

POST /api/generate: Accepts a JSON payload specifying a "product" (string), the number of samples to generate (count), and a prompt version string. Returns a job ID immediately.

GET /api/result/{job_id}: Returns the current status and, when complete, the generated samples with rich metadata.

Async/job-queue orchestration:
Use fast, reliable background task execution (prefer native asyncio for demo; pluggable for real queueing later). Job state and results must persist (use Redis as storage for jobs and results).

Prompt templating:
Generate prompts using Jinja2 templates, e.g., “You are a frustrated customer writing a support request about a problem with {{ product }}…”. Render dynamically per request.

LLM abstraction:
Implement a pluggable, async LLM client interface. Default to OpenAI GPT-4, but architecture should allow easy swap to Anthropic or local LLMs.

Metadata and versioning:
Each generated sample must include: unique ID, input product, prompt version, UTC timestamp, sample text, estimated token count.

Async/batched generation:
Run LLM calls concurrently for performance (e.g., asyncio.gather). Optionally batch LLM API calls for efficiency if supported.

Best Practices & Production Readiness:
Input Validation:

Validate input types, clamp max sample count, and sanitize product string.

Status Tracking:

Track and expose job status: pending, running, completed, error (with error messages).

Persistence:

Store job status and results in Redis (use redis-py/redis.asyncio).

Error Handling:

Propagate and return error state/messages on job failure (e.g., OpenAI errors, input errors).

Modularity:

Modular, readable code with clear directory layout (app/routers/, app/services/, app/utils/, app/models/, app/templates/, app/config.py).

Extensibility:

Easy to plug in more prompt templates and LLM providers.

Type Safety:

Use Pydantic models for request/response schemas.

Usage Example:

Provide code snippets for example requests and a sample response.

Deliverables:
A full codebase structured as above (with FastAPI setup, modular files, and Jinja2 template).

Pip requirements list.

All essential files for running, local development, and testing.

Clear comments and docstrings for each module/class/function.

Tips to extend this system (e.g., swap in Celery/RQ queueing, add rate limiting, security, or dashboard).

Goal:
The final project should be “engineering-lead impressed”—asynchronous, observable, robust, extensible, clearly organized, well-commented, and easy for another Python developer to audit or extend.