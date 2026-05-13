#!/bin/bash
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# --- Configuration ---
REDIS_CONTAINER_NAME="${REDIS_CONTAINER_NAME:-chirp-alpha-redis}"
REDIS_IMAGE="${REDIS_IMAGE:-redis:7-alpine}"
START_REDIS="${START_REDIS:-true}"
FLUSH_CACHE=false
if [ "$1" == "--flush-cache" ]; then
    FLUSH_CACHE=true
fi

# --- State & Cleanup ---
REDIS_STARTED_BY_SCRIPT=false
pids=() # Array to store PIDs of background processes
export CACHE_REDIS_LOG_OPS="${CACHE_REDIS_LOG_OPS:-true}"

cleanup() {
    echo -e "${CYAN}
Shutting down services...${NC}"

    # Kill background jobs started by this script
    if [ ${#pids[@]} -gt 0 ]; then
        echo "Stopping background processes: ${pids[*]}"
        for pid in "${pids[@]}"; do
            # Use process group kill (-$pid) to also get children (like servers spawned by npm)
            # The '--' ensures a negative PID isn't treated as an option to `kill`
            if ps -p "$pid" > /dev/null; then
               kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
            fi
        done
    fi

    # Stop Redis if it was started by this script
    if [ "$REDIS_STARTED_BY_SCRIPT" = true ]; then
        echo "Stopping Redis container..."
        docker stop "$REDIS_CONTAINER_NAME" >/dev/null 2>&1
    fi
    
    # Final cleanup of any orphaned processes as a fallback
    kill 0 2>/dev/null
    echo -e "${GREEN}Cleanup complete.${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# --- Script Body ---
echo -e "${BLUE}Starting Chirp Alpha App services...${NC}"

# Find project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -d "$SCRIPT_DIR/backend" ] && [ -d "$SCRIPT_DIR/frontend" ]; then
    ROOT_DIR="$SCRIPT_DIR"
elif [ -d "$SCRIPT_DIR/../backend" ] && [ -d "$SCRIPT_DIR/../frontend" ]; then
    ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
else
    echo -e "${NC}Error: Could not find backend/frontend directories from $SCRIPT_DIR${NC}"
    exit 1
fi
echo -e "${BLUE}Project root detected at: $ROOT_DIR${NC}"

# Load .env file
if [ -f "$ROOT_DIR/.env" ]; then
    set -a
    source "$ROOT_DIR/.env"
    set +a
    echo -e "${CYAN}Loaded .env from $ROOT_DIR${NC}"
fi

# Start/manage Redis
if [ "$START_REDIS" = true ]; then
    if ! command -v docker >/dev/null 2>&1; then
        echo -e "${NC}Warning: docker is not installed. Redis will not be started.${NC}"
    else
        if docker ps -a --format '{{.Names}}' | grep -qx "$REDIS_CONTAINER_NAME"; then
            if ! docker ps --format '{{.Names}}' | grep -qx "$REDIS_CONTAINER_NAME"; then
                echo -e "${GREEN}Starting existing Redis container ${REDIS_CONTAINER_NAME}...${NC}"
                docker start "$REDIS_CONTAINER_NAME" >/dev/null
                REDIS_STARTED_BY_SCRIPT=true
            fi
        else
            echo -e "${GREEN}Starting new local Redis container (${REDIS_IMAGE})...${NC}"
            docker run -d --rm --name "$REDIS_CONTAINER_NAME" -p 6379:6379 "$REDIS_IMAGE" >/dev/null
            REDIS_STARTED_BY_SCRIPT=true
        fi

        echo -e "${CYAN}Waiting for Redis...${NC}"
        for _ in {1..30}; do
            if docker exec "$REDIS_CONTAINER_NAME" redis-cli ping >/dev/null 2>&1; then
                echo -e "${GREEN}Redis is ready.${NC}"
                break
            fi; sleep 0.2
        done
        
        if [ "$FLUSH_CACHE" = true ]; then
            echo -e "${CYAN}Flushing Redis cache...${NC}"
            if docker exec "$REDIS_CONTAINER_NAME" redis-cli FLUSHALL | grep -q "OK"; then
                echo -e "${GREEN}Redis cache flushed successfully.${NC}"
            else
                echo -e "${NC}Error: Failed to flush Redis cache.${NC}"
            fi
        fi
    fi
fi

# Start App Services
echo -e "${GREEN}[1/3] Starting gRPC Server (Python/Poetry)...${NC}"
(cd "$ROOT_DIR/grpc" && poetry run python momentum_server.py) &
pids+=($!)

echo -e "${GREEN}[2/3] Starting Backend (Spring Boot)...${NC}"
(cd "$ROOT_DIR/backend" && ./mvnw spring-boot:run) &
pids+=($!)

echo -e "${GREEN}[3/3] Starting Frontend (Vite/React)...${NC}"
(cd "$ROOT_DIR/frontend" && npm run dev) &
pids+=($!)

echo -e "
${BLUE}All services are starting. Press Ctrl+C to stop all.${NC}"
echo -e "${CYAN}Run with --with-cache to enable Redis cache.${NC}"
echo -e "${CYAN}Run with --flush-cache to clear Redis on start.${NC}"
wait

echo -e "
${BLUE}All services are starting. Press Ctrl+C to stop all.${NC}"
echo -e "${CYAN}Run with --flush-cache to clear Redis on start.${NC}"
wait
