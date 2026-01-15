#!/bin/bash
# sync_all.sh - Sync code from GitHub as each citizen
# Run as root, executes git pull as each user

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
    
    # Create code dir if needed
    if [ ! -d "$CODE_DIR" ]; then
        log "  Cloning repo for $citizen..."
        sudo -u "$citizen" git clone "$REPO" "$CODE_DIR"
    else
        log "  Pulling latest..."
        sudo -u "$citizen" -H sh -c "cd $CODE_DIR && git pull origin main"
    fi
    
    echo "  ✓ $citizen synced"
done

log "All citizens synced"
echo ""
echo "To start:"
echo "  sudo -u opus /home/opus/code/run.sh wake"
echo "  sudo -u mira /home/mira/code/run.sh wake"
echo "  sudo -u aria /home/aria/code/run.sh wake"
