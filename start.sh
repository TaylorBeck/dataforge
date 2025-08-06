#!/bin/bash
# Start Celery worker in background
celery -A app.celery_app worker --loglevel=info --concurrency=2 --detach

# Start the FastAPI server
uvicorn app.main:app --host 0.0.0.0 --port 8000