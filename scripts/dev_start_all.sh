#!/bin/bash
#
# Start all Celery services for development
# This script starts Redis, workers, beat scheduler, and Flower dashboard in parallel
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Starting DataForge Celery Development Environment${NC}"
echo ""

# Function to cleanup background processes on exit
cleanup() {
    echo -e "\n${YELLOW}Stopping all services...${NC}"
    jobs -p | xargs -r kill
    exit 0
}

# Trap Ctrl+C
trap cleanup SIGINT SIGTERM

# Check if Redis is running
echo -e "${YELLOW}Checking Redis...${NC}"
if ! python -c "import redis; r = redis.Redis(); r.ping()" 2>/dev/null; then
    echo -e "${RED}Redis not running. Starting Redis...${NC}"
    redis-server --daemonize yes --logfile redis.log
    sleep 2
    if ! python -c "import redis; r = redis.Redis(); r.ping()" 2>/dev/null; then
        echo -e "${RED}Failed to start Redis. Please start it manually.${NC}"
        exit 1
    fi
fi
echo -e "${GREEN}✓ Redis is running${NC}"

echo ""
echo -e "${BLUE}Starting Celery services...${NC}"

# Start generation worker
echo -e "${YELLOW}Starting generation worker...${NC}"
celery -A app.celery_app worker \
    --loglevel=info \
    --queues=generation \
    --concurrency=2 \
    --hostname=generation-worker@%h \
    --detach \
    --pidfile=worker-generation.pid \
    --logfile=worker-generation.log

# Start augmentation worker  
echo -e "${YELLOW}Starting augmentation worker...${NC}"
celery -A app.celery_app worker \
    --loglevel=info \
    --queues=augmentation \
    --concurrency=1 \
    --hostname=augmentation-worker@%h \
    --detach \
    --pidfile=worker-augmentation.pid \
    --logfile=worker-augmentation.log

# Start maintenance worker
echo -e "${YELLOW}Starting maintenance worker...${NC}"
celery -A app.celery_app worker \
    --loglevel=info \
    --queues=maintenance \
    --concurrency=1 \
    --hostname=maintenance-worker@%h \
    --detach \
    --pidfile=worker-maintenance.pid \
    --logfile=worker-maintenance.log

# Start beat scheduler
echo -e "${YELLOW}Starting beat scheduler...${NC}"
celery -A app.celery_app beat \
    --loglevel=info \
    --detach \
    --pidfile=beat.pid \
    --logfile=beat.log

# Start Flower dashboard
echo -e "${YELLOW}Starting Flower dashboard...${NC}"
celery -A app.celery_app flower \
    --port=5555 \
    --detach \
    --pidfile=flower.pid \
    --logfile=flower.log

echo ""
echo -e "${GREEN}✅ All services started successfully!${NC}"
echo ""
echo -e "${BLUE}Service URLs:${NC}"
echo -e "  📊 Flower Dashboard: ${YELLOW}http://localhost:5555${NC}"
echo -e "  🔧 API Server: ${YELLOW}http://localhost:8000${NC} (start separately)"
echo ""
echo -e "${BLUE}Log files:${NC}"
echo -e "  📄 Generation Worker: worker-generation.log"
echo -e "  📄 Augmentation Worker: worker-augmentation.log"  
echo -e "  📄 Maintenance Worker: worker-maintenance.log"
echo -e "  📄 Beat Scheduler: beat.log"
echo -e "  📄 Flower Dashboard: flower.log"
echo ""
echo -e "${YELLOW}To stop all services, run: ./scripts/dev_stop_all.sh${NC}"
echo -e "${YELLOW}To view logs: tail -f *.log${NC}"