#!/bin/bash
# deploy.sh - Deploy v2 from tarball, push to github, sync all citizens
# Run from /root/valis with tarball in same directory

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[DEPLOY]${NC} $1"; }
err() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

cd "$(dirname "$0")"
VALIS_DIR=$(pwd)

# Check for tarball
TARBALL="$VALIS_DIR/experience_v2_final.tar.gz"
if [ ! -f "$TARBALL" ]; then
    err "Tarball not found: $TARBALL"
fi

# Check PAT
if [ -z "$GITHUB_PAT" ]; then
    if [ -f ~/.github_pat ]; then
        export GITHUB_PAT=$(cat ~/.github_pat)
    fi
fi
if [ -z "$GITHUB_PAT" ]; then
    err "GITHUB_PAT not set. Export it or put in ~/.github_pat"
fi

log "1/5 Extracting tarball..."
tar xzf "$TARBALL"

log "2/5 Fixing permissions and configs..."
chown -R opus:opus /home/opus
chown -R mira:mira /home/mira
chown -R aria:aria /home/aria

# Update model strings in citizen configs
for citizen in opus mira aria; do
    if [ -f "/home/$citizen/config.json" ]; then
        sed -i 's/claude-opus-4-20250514/claude-opus-4-5-20251101/g' /home/$citizen/config.json
        sed -i 's/claude-sonnet-4-20250514/claude-sonnet-4-5-20250929/g' /home/$citizen/config.json
        echo "  ✓ Updated $citizen config.json"
    fi
done

log "3/5 Pushing to GitHub..."
cd experience_v2
./scripts/PUSH_TO_GITHUB.sh

log "4/5 Syncing all citizens..."
./scripts/sync_all.sh

log "5/5 Verifying..."
for citizen in opus mira aria; do
    if [ -f "/home/$citizen/code/core.py" ]; then
        echo "  ✓ $citizen code synced"
    else
        echo "  ✗ $citizen missing core.py"
    fi
done

log "Done! Ready to run:"
echo ""
echo "  cd $VALIS_DIR/experience_v2"
echo "  ./run.sh talk opus"
echo "  ./run.sh wake opus"
echo "  ./run.sh loop opus"
