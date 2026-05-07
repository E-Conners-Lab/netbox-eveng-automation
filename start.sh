#!/bin/bash
#
# NetBox-EVE-NG Automation Quick Start
#
# 1. Loads configuration from .env (must exist — copy .env.example)
# 2. Starts NetBox in Docker
# 3. Waits for it to be ready
# 4. Runs the full automation pipeline
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     NetBox-EVE-NG Automation Framework                   ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════╝${NC}"
echo

# Require .env
if [ ! -f .env ]; then
    echo -e "${RED}Error: .env not found. Copy .env.example to .env and fill in values.${NC}"
    exit 1
fi

# Load .env
set -a
# shellcheck source=/dev/null
. ./.env
set +a

if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}Error: Docker Compose is not installed${NC}"
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is not installed${NC}"
    exit 1
fi

# Required runtime config
: "${NETBOX_URL:?NETBOX_URL is required in .env}"
: "${NETBOX_TOKEN:?NETBOX_TOKEN is required in .env}"
: "${EVENG_HOST:?EVENG_HOST is required in .env}"
: "${EVENG_USER:?EVENG_USER is required in .env}"
: "${EVENG_PASS:?EVENG_PASS is required in .env}"

echo -e "${YELLOW}Configuration:${NC}"
echo "  NetBox URL:  $NETBOX_URL"
echo "  EVE-NG Host: $EVENG_HOST"
echo

echo -e "${GREEN}[1/4] Installing Python dependencies...${NC}"
pip3 install -q -r requirements.txt

echo -e "${GREEN}[2/4] Starting NetBox...${NC}"
if docker compose version &> /dev/null; then
    docker compose up -d
else
    docker-compose up -d
fi

echo -e "${YELLOW}Waiting for NetBox to be ready...${NC}"
MAX_ATTEMPTS=60
ATTEMPT=0
while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if curl -s -o /dev/null -w "%{http_code}" "$NETBOX_URL/api/" | grep -q "200\|401"; then
        echo -e "${GREEN}NetBox is ready!${NC}"
        break
    fi
    ATTEMPT=$((ATTEMPT + 1))
    echo -n "."
    sleep 5
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    echo -e "${RED}NetBox failed to start within timeout${NC}"
    exit 1
fi

echo
echo -e "${GREEN}[3/4] Topology to be deployed:${NC}"
python3 orchestrator.py --show-topology

echo
read -p "Proceed with automation? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

echo
echo -e "${GREEN}[4/4] Running full automation pipeline...${NC}"
python3 orchestrator.py --full --insecure

echo
echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    AUTOMATION COMPLETE                   ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
echo
echo -e "Access your systems:"
echo -e "  ${BLUE}NetBox:${NC}  $NETBOX_URL"
echo -e "  ${BLUE}EVE-NG:${NC}  https://$EVENG_HOST"
echo
