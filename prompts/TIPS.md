Absolutely! Here's a modern, robust, and production-ready file structure and code for an async, job-queuing, LLM-powered synthetic data service using FastAPI. This implements the improvements and suggestions discussed, with clear points for extension.

The setup features:

Async FastAPI API with clear job status tracking (pending, running, completed, error)

Pluggable, async LLM client adapter (OpenAI shown, but swappable)

Job status and results stored in Redis (production ready; easily upgrade to Postgres, S3, etc.)

Input/output validation, limits, error handling

Modular prompt templating (Jinja2)

Clean separation of concerns and extensible architecture

📁 File Structure
text
app/
├── main.py
├── routers/
│   └── generator.py
├── models/
│   └── schemas.py
├── services/
│   └── llm_generator.py
│   └── job_manager.py
├── utils/
│   └── llm_client.py
├── templates/
│   └── support_prompt.j2
├── config.py
1️⃣ config.py (settings, environment, constants)
python
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
JOB_EXPIRE_SECONDS = 60 * 60  # 1 hour
MAX_SAMPLES_PER_REQUEST = 20
SUPPORTED_LLM = "openai"  # or "anthropic", "fake"
2️⃣ models/schemas.py (Pydantic models)
python
from pydantic import BaseModel, Field
from typing import List, Optional, Literal

class GenerationRequest(BaseModel):
    product: str = Field(..., min_length=2, max_length=120)
    count: int = Field(5, ge=1, le=20)
    version: str = "v1"

class GeneratedSample(BaseModel):
    id: str
    product: str
    prompt_version: str
    generated_at: str
    text: str
    tokens_estimated: int

class GenerationResponse(BaseModel):
    samples: List[GeneratedSample]

class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal['pending', 'running', 'completed', 'error']
    error_message: Optional[str] = None
    result: Optional[GenerationResponse] = None
3️⃣ templates/support_prompt.j2
text
You are a frustrated customer writing a support request about a problem with {{ product }}.
Use a polite but firm tone. Be specific.

Request:
4️⃣ utils/llm_client.py (pluggable async adapter)
python
import openai
import asyncio

class OpenAIClientAsync:
    async def generate(self, prompt, temperature=0.7):
        loop = asyncio.get_running_loop()
        # openai.ChatCompletion.create is sync, so run in a threadpool
        resp = await loop.run_in_executor(
            None,
            lambda: openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
            ),
        )
        return resp.choices[0].message.content.strip()

def get_llm_client(vendor="openai"):
    if vendor == "openai":
        return OpenAIClientAsync()
    raise NotImplementedError(f"LLM vendor '{vendor}' not supported")
5️⃣ services/llm_generator.py (prompt rendering & async generation)
python
from jinja2 import Template
from pathlib import Path
from uuid import uuid4
from datetime import datetime

from app.utils.llm_client import get_llm_client

PROMPT_TEMPLATE = Path("app/templates/support_prompt.j2").read_text()

def render_prompt(product: str) -> str:
    template = Template(PROMPT_TEMPLATE)
    return template.render(product=product)

async def generate_sample(product: str, version: str, adapter) -> dict:
    prompt = render_prompt(product)
    text = await adapter.generate(prompt)
    return {
        "id": str(uuid4()),
        "product": product,
        "prompt_version": version,
        "generated_at": datetime.utcnow().isoformat(),
        "text": text,
        "tokens_estimated": len(text.split()),
    }
6️⃣ services/job_manager.py (manage job lifecycle & Redis storage)
python
import redis.asyncio as redis
import uuid
import json
from typing import List
from app.config import REDIS_URL, JOB_EXPIRE_SECONDS
from app.models.schemas import GenerationRequest
from app.services.llm_generator import generate_sample
from app.utils.llm_client import get_llm_client

r = redis.from_url(REDIS_URL, decode_responses=True)

async def start_generation_job(req: GenerationRequest) -> str:
    job_id = str(uuid.uuid4())
    await r.hset(job_id, mapping={
        "status": "pending",
        "error_message": "",
    })
    await r.expire(job_id, JOB_EXPIRE_SECONDS)
    asyncio.create_task(run_job(req, job_id))
    return job_id

async def run_job(req: GenerationRequest, job_id: str):
    await r.hset(job_id, mapping={"status": "running"})
    try:
        adapter = get_llm_client()
        # Batch LLM calls in parallel
        samples = await asyncio.gather(
            *[generate_sample(req.product, req.version, adapter) for _ in range(req.count)]
        )
        await r.hset(job_id, mapping={
            "status": "completed",
            "samples": json.dumps(samples),
        })
    except Exception as e:
        await r.hset(job_id, mapping={
            "status": "error",
            "error_message": str(e),
        })

async def get_job_status(job_id: str):
    job = await r.hgetall(job_id)
    if not job:
        return None
    status = job.get("status")
    error_message = job.get("error_message") or None
    samples = job.get("samples")
    result = None
    if status == "completed" and samples:
        result = {"samples": json.loads(samples)}
    return {"job_id": job_id, "status": status, "error_message": error_message, "result": result}
7️⃣ routers/generator.py (expose async API endpoints)
python
from fastapi import APIRouter, HTTPException
from app.models.schemas import GenerationRequest, JobStatusResponse, GenerationResponse
from app.services.job_manager import start_generation_job, get_job_status
from app.config import MAX_SAMPLES_PER_REQUEST

router = APIRouter()

@router.post("/generate", response_model=JobStatusResponse)
async def generate(req: GenerationRequest):
    if req.count > MAX_SAMPLES_PER_REQUEST:
        raise HTTPException(status_code=400, detail=f"count exceeds max of {MAX_SAMPLES_PER_REQUEST}")
    job_id = await start_generation_job(req)
    return JobStatusResponse(job_id=job_id, status="pending")

@router.get("/result/{job_id}", response_model=JobStatusResponse)
async def result(job_id: str):
    status = await get_job_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    return status
8️⃣ main.py (app entrypoint)
python
from fastapi import FastAPI
from app.routers import generator

app = FastAPI(title="Synthetic LLM Data Generator", version="1.0.0")
app.include_router(generator.router, prefix="/api")
✅ Example Usage
Request
text
POST /api/generate
Content-Type: application/json

{
  "product": "calendar sync bug in app",
  "count": 3
}
Returns:

json
{
  "job_id": "2b7c1c42-87dd-4f89-90e3-bbd7819cc2e4",
  "status": "pending",
  "error_message": null,
  "result": null
}
Status Poll
text
GET /api/result/2b7c1c42-87dd-4f89-90e3-bbd7819cc2e4
Returns once done:

json
{
  "job_id": "...",
  "status": "completed",
  "error_message": null,
  "result": {
    "samples": [
      { "id": "...", "product": "calendar sync bug in app", ... }
    ]
  }
}
Or if error:

json
{
  "job_id": "...",
  "status": "error",
  "error_message": "OpenAI API quota exceeded",
  "result": null
}
🚩 Notes
Easy to add: logging, metrics, tracing, multi-template, user auth, or swap in Celery/RQ for distributed queues.

Deployment tip: Use gunicorn/uvicorn workers and robust Redis/Postgres backend for scale.