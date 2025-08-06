#!/bin/bash
#
# Start Celery worker for DataForge
# Usage: ./scripts/start_worker.sh [queue_name] [concurrency]
#
# Examples:
#   ./scripts/start_worker.sh                    # Start worker for all queues
#   ./scripts/start_worker.sh generation 4      # Start worker for generation queue with 4 processes
#   ./scripts/start_worker.sh augmentation 2    # Start worker for augmentation queue with 2 processes
#

set -e

# Default values
QUEUE=${1:-"generation,augmentation,maintenance"}
CONCURRENCY=${2:-4}
LOGLEVEL=${3:-info}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Celery worker for DataForge${NC}"
echo -e "${YELLOW}Queue(s): ${QUEUE}${NC}"
echo -e "${YELLOW}Concurrency: ${CONCURRENCY}${NC}"
echo -e "${YELLOW}Log level: ${LOGLEVEL}${NC}"
echo ""

# Check if virtual environment is activated
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo -e "${RED}Warning: No virtual environment detected. Consider activating venv first.${NC}"
    echo ""
fi

# Check if Redis is running
echo -e "${YELLOW}Checking Redis connection...${NC}"
if ! python -c "import redis; r = redis.Redis(); r.ping()" 2>/dev/null; then
    echo -e "${RED}Error: Cannot connect to Redis. Please start Redis first.${NC}"
    echo "Start Redis with: redis-server"
    exit 1
fi
echo -e "${GREEN}Redis connection: OK${NC}"
echo ""

# Start the worker
echo -e "${GREEN}Starting Celery worker...${NC}"
echo "Press Ctrl+C to stop the worker"
echo ""

celery -A app.celery_app worker \
    --loglevel=$LOGLEVEL \
    --queues=$QUEUE \
    --concurrency=$CONCURRENCY \
    --hostname=worker-$QUEUE@%h \
    --max-tasks-per-child=100 \
    --prefetch-multiplier=1 \
    --without-gossip \
    --without-mingle