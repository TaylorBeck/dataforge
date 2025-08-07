#!/bin/bash
set -e

echo "Starting DataForge application..."

# Validate required environment variables
if [ -z "$REDIS_URL" ]; then
    echo "ERROR: REDIS_URL environment variable is not set"
    exit 1
fi

if [ -z "$OPENAI_API_KEY" ] && [ "${DEFAULT_LLM_PROVIDER:-openai}" = "openai" ]; then
    echo "ERROR: OPENAI_API_KEY environment variable is not set"
    exit 1
fi

# Wait for Redis
python3 -c "
import redis
import time
import os
url = os.getenv('REDIS_URL')
for i in range(30):
    try:
        redis.from_url(url).ping()
        break
    except:
        time.sleep(2)
else:
    exit(1)
"

# Start Celery worker
celery -A app.celery_app worker \
    --loglevel=info \
    --concurrency=2 \
    --queues=generation,augmentation,maintenance,default \
    --detach \
    --pidfile=/tmp/celery.pid \
    --logfile=/tmp/celery.log

sleep 3

# Start FastAPI server
uvicorn app.main:app --host 0.0.0.0 --port 8000