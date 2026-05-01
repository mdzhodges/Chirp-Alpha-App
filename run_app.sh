#!/bin/bash
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${BLUE}Starting Chirp Alpha App services from Model directory...${NC}"

cleanup() {
    echo -e "\n${CYAN}Stopping all services...${NC}"
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

# 1. Start gRPC Server
echo -e "${GREEN}[1/3] Starting gRPC Server (Python/Poetry)...${NC}"
(cd "$ROOT_DIR/grpc" && poetry run python momentum_server.py) &

# 2. Start Backend
echo -e "${GREEN}[2/3] Starting Backend (Spring Boot)...${NC}"
(cd "$ROOT_DIR/backend" && ./mvnw spring-boot:run) &

# 3. Start Frontend
echo -e "${GREEN}[3/3] Starting Frontend (Vite/React)...${NC}"
(cd "$ROOT_DIR/frontend" && npm run dev) &

echo -e "${BLUE}All services are running. Press Ctrl+C to stop all.${NC}"
wait