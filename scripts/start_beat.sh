#!/bin/bash
#
# Start Celery Beat scheduler for periodic tasks
# Usage: ./scripts/start_beat.sh
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Celery Beat scheduler for periodic tasks${NC}"
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

# Remove old beat schedule file if it exists
if [ -f "celerybeat-schedule" ]; then
    echo -e "${YELLOW}Removing old beat schedule file...${NC}"
    rm celerybeat-schedule
fi

# Start Beat scheduler
echo -e "${GREEN}Starting Celery Beat scheduler...${NC}"
echo "Press Ctrl+C to stop the scheduler"
echo ""

celery -A app.celery_app beat \
    --loglevel=info \
    --scheduler=celery.beat:PersistentScheduler