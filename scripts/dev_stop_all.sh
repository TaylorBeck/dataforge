#!/bin/bash
#
# Stop all Celery services for development
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}🛑 Stopping DataForge Celery Development Environment${NC}"
echo ""

# Function to stop service if pid file exists
stop_service() {
    local service_name=$1
    local pid_file=$2
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "${YELLOW}Stopping $service_name (PID: $pid)...${NC}"
            kill "$pid"
            rm -f "$pid_file"
            echo -e "${GREEN}✓ $service_name stopped${NC}"
        else
            echo -e "${RED}$service_name PID file exists but process not running${NC}"
            rm -f "$pid_file"
        fi
    else
        echo -e "${YELLOW}$service_name is not running (no PID file)${NC}"
    fi
}

# Stop all services
stop_service "Generation Worker" "worker-generation.pid"
stop_service "Augmentation Worker" "worker-augmentation.pid"
stop_service "Maintenance Worker" "worker-maintenance.pid"
stop_service "Beat Scheduler" "beat.pid"
stop_service "Flower Dashboard" "flower.pid"

# Also try to stop any remaining celery processes
echo ""
echo -e "${YELLOW}Checking for remaining Celery processes...${NC}"
celery_pids=$(pgrep -f "celery.*app.celery_app" || true)
if [ -n "$celery_pids" ]; then
    echo -e "${YELLOW}Found remaining Celery processes: $celery_pids${NC}"
    echo "$celery_pids" | xargs kill
    echo -e "${GREEN}✓ Remaining processes stopped${NC}"
else
    echo -e "${GREEN}✓ No remaining Celery processes found${NC}"
fi

# Clean up beat schedule file
if [ -f "celerybeat-schedule" ]; then
    echo -e "${YELLOW}Removing beat schedule file...${NC}"
    rm -f celerybeat-schedule
fi

echo ""
echo -e "${GREEN}✅ All services stopped successfully!${NC}"
echo ""
echo -e "${BLUE}Log files preserved:${NC}"
echo -e "  📄 Generation Worker: worker-generation.log"
echo -e "  📄 Augmentation Worker: worker-augmentation.log"
echo -e "  📄 Maintenance Worker: worker-maintenance.log" 
echo -e "  📄 Beat Scheduler: beat.log"
echo -e "  📄 Flower Dashboard: flower.log"
echo ""
echo -e "${YELLOW}To view recent logs: tail -20 *.log${NC}"
echo -e "${YELLOW}To clean up logs: rm *.log${NC}"