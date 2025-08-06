#!/bin/bash
set -e  # Exit on any error

echo "Starting DataForge application..."

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

# Start Celery worker in background
echo "Starting Celery worker..."
celery -A app.celery_app worker \
    --loglevel=info \
    --concurrency=2 \
    --queues=generation,augmentation,maintenance,default \
    --detach \
    --pidfile=/tmp/celery.pid \
    --logfile=/tmp/celery.log

# Give Celery a moment to start
sleep 3

# Verify Celery worker is running
if [ -f /tmp/celery.pid ]; then
    echo "Celery worker started successfully"
else
    echo "Failed to start Celery worker"
    cat /tmp/celery.log || echo "No Celery log available"
    exit 1
fi

echo "Starting DataForge server..."
uvicorn app.main:app --host 0.0.0.0 --port 8000