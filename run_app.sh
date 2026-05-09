#!/bin/bash
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

REDIS_CONTAINER_NAME="${REDIS_CONTAINER_NAME:-chirp-alpha-redis}"
REDIS_IMAGE="${REDIS_IMAGE:-redis:7-alpine}"
START_REDIS="${START_REDIS:-true}"
REDIS_STARTED_BY_SCRIPT=false
export CACHE_REDIS_LOG_OPS="${CACHE_REDIS_LOG_OPS:-true}"

echo -e "${BLUE}Starting Chirp Alpha App services from Model directory...${NC}"

cleanup() {
    if [ "$REDIS_STARTED_BY_SCRIPT" = true ]; then
        docker stop "$REDIS_CONTAINER_NAME" >/dev/null 2>&1 || true
    fi
    kill 0
}
trap cleanup SIGINT SIGTERM

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

# Load .env file so all child processes inherit the vars
if [ -f "$ROOT_DIR/.env" ]; then
    set -a
    source "$ROOT_DIR/.env"
    set +a
    echo -e "${CYAN}Loaded .env from $ROOT_DIR${NC}"
else
    echo -e "${NC}Warning: No .env file found at $ROOT_DIR/.env${NC}"
fi

if [ "$START_REDIS" = true ]; then
    if command -v docker >/dev/null 2>&1; then
        if docker ps -a --format '{{.Names}}' | grep -qx "$REDIS_CONTAINER_NAME"; then
            if ! docker ps --format '{{.Names}}' | grep -qx "$REDIS_CONTAINER_NAME"; then
                echo -e "${GREEN}Starting existing Redis container ${REDIS_CONTAINER_NAME}...${NC}"
                docker start "$REDIS_CONTAINER_NAME" >/dev/null
                REDIS_STARTED_BY_SCRIPT=true
            else
                echo -e "${CYAN}Redis container ${REDIS_CONTAINER_NAME} is already running.${NC}"
            fi
        else
            echo -e "${GREEN}Starting local Redis container (${REDIS_IMAGE})...${NC}"
            docker run -d \
                --name "$REDIS_CONTAINER_NAME" \
                -p 6379:6379 \
                "$REDIS_IMAGE" >/dev/null
            REDIS_STARTED_BY_SCRIPT=true
        fi

        echo -e "${CYAN}Waiting for Redis to become ready...${NC}"
        for _ in {1..30}; do
            if docker exec "$REDIS_CONTAINER_NAME" redis-cli ping >/dev/null 2>&1; then
                echo -e "${GREEN}Redis is ready on localhost:6379${NC}"
                break
            fi
            sleep 1
        done
    else
        echo -e "${NC}Warning: docker is not installed, so Redis will not be started automatically.${NC}"
    fi
fi

# 3. Start Frontend
echo -e "${GREEN}[3/3] Starting Frontend (Vite/React)...${NC}"
(cd "$ROOT_DIR/frontend" && npm run dev) &

# 1. Start gRPC Server
echo -e "${GREEN}[1/3] Starting gRPC Server (Python/Poetry)...${NC}"
(cd "$ROOT_DIR/grpc" && poetry run python momentum_server.py) &

# 2. Start Backend
echo -e "${GREEN}[2/3] Starting Backend (Spring Boot)...${NC}"
(cd "$ROOT_DIR/backend" && ./mvnw spring-boot:run) &
echo -e "${BLUE}All services are running. Press Ctrl+C to stop all.${NC}"
wait
