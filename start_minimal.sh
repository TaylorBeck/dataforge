#!/bin/bash
set -e  # Exit on any error

echo "Starting DataForge application (minimal mode)..."

# Print environment info for debugging
echo "REDIS_URL: ${REDIS_URL:-not set}"
echo "DEBUG: ${DEBUG:-not set}"
echo "DEFAULT_LLM_PROVIDER: ${DEFAULT_LLM_PROVIDER:-not set}"
echo "OPENAI_API_KEY: ${OPENAI_API_KEY:+[SET]}"

# Validate critical environment variables
if [ -z "$REDIS_URL" ]; then
    echo "ERROR: REDIS_URL environment variable is not set"
    exit 1
fi

if [ -z "$OPENAI_API_KEY" ] && [ "${DEFAULT_LLM_PROVIDER:-openai}" = "openai" ]; then
    echo "ERROR: OPENAI_API_KEY environment variable is not set"
    exit 1
fi

# Wait for Redis to be available
echo "Waiting for Redis to be available..."
python3 -c "
import redis
import time
import os
url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
print(f'Testing Redis connection to: {url}')
for i in range(30):
    try:
        r = redis.from_url(url)
        r.ping()
        print('Redis is ready!')
        break
    except Exception as e:
        print(f'Redis not ready (attempt {i+1}/30): {e}')
        time.sleep(2)
else:
    print('Redis failed to become ready')
    exit(1)
"

# Skip Celery for now and start the FastAPI server directly
echo "Starting DataForge server (without Celery workers)..."
echo "⚠️  Background job processing will be disabled until Celery workers are running"
uvicorn app.main:app --host 0.0.0.0 --port 8000