#!/bin/bash
#
# Start Flower monitoring dashboard for Celery
# Usage: ./scripts/start_flower.sh [port]
#
# Examples:
#   ./scripts/start_flower.sh        # Start on default port 5555
#   ./scripts/start_flower.sh 8888   # Start on port 8888
#

set -e

# Default values
PORT=${1:-5555}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Flower monitoring dashboard${NC}"
echo -e "${YELLOW}Port: ${PORT}${NC}"
echo -e "${YELLOW}Dashboard URL: http://localhost:${PORT}${NC}"
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

# Start Flower
echo -e "${GREEN}Starting Flower dashboard...${NC}"
echo "Press Ctrl+C to stop Flower"
echo ""

celery -A app.celery_app flower \
    --port=$PORT \
    --broker=redis://localhost:6379/0 \
    --url_prefix=flower \
    --basic_auth=admin:dataforge123 \
    --persistent=True