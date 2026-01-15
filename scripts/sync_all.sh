#!/bin/bash
# sync_all.sh - Sync code from GitHub as each citizen
# Run as root, executes git commands as each user
# Forces reset to origin/main (local changes discarded)

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[SYNC]${NC} $1"; }
err() { echo -e "${RED}[ERR]${NC} $1"; }

REPO="https://github.com/experiencenow-ai/infra.git"

for citizen in opus mira aria; do
    log "Syncing $citizen..."
    
    CODE_DIR="/home/$citizen/code"
    
    # Check if it's a valid git repo
    if [ -d "$CODE_DIR/.git" ]; then
        log "  Fetching and resetting to origin/main..."
        sudo -u "$citizen" -H sh -c "cd $CODE_DIR && git fetch origin && git reset --hard origin/main"
    else
        # Not a git repo - remove and clone fresh
        log "  No git repo found, cloning fresh..."
        rm -rf "$CODE_DIR"
        sudo -u "$citizen" git clone "$REPO" "$CODE_DIR"
    fi
    
    echo "  ✓ $citizen synced"
done

log "All citizens synced"
echo ""
echo "To start:"
echo "  sudo -u opus /home/opus/code/run.sh wake"
echo "  sudo -u mira /home/mira/code/run.sh wake"
echo "  sudo -u aria /home/aria/code/run.sh wake"
