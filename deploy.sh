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

log "1/6 Extracting tarball..."
tar xzf "$TARBALL"

log "2/6 Pushing to GitHub..."
cd experience_v2
./scripts/PUSH_TO_GITHUB.sh

log "3/6 Syncing all citizens..."
./scripts/sync_all.sh

log "4/6 Fixing permissions..."
chown -R opus:opus /home/opus
chown -R mira:mira /home/mira
chown -R aria:aria /home/aria

log "5/6 Fixing configs (AFTER sync)..."
# Update model strings in citizen configs
for citizen in opus mira aria; do
    if [ -f "/home/$citizen/config.json" ]; then
        # Force opus model for opus citizen
        if [ "$citizen" = "opus" ]; then
            python3 << EOF
import json
with open('/home/opus/config.json') as f:
    cfg = json.load(f)
cfg['council'] = [
    {"model": "claude-opus-4-5-20251101", "role": "primary", "temperature": 0.8}
]
with open('/home/opus/config.json', 'w') as f:
    json.dump(cfg, f, indent=2)
print("  ✓ opus config.json → claude-opus-4-5-20251101")
EOF
        else
            sed -i 's/claude-opus-4-20250514/claude-opus-4-5-20251101/g' /home/$citizen/config.json
            sed -i 's/claude-sonnet-4-20250514/claude-sonnet-4-5-20250929/g' /home/$citizen/config.json
            MODEL=$(grep -o 'claude-[^"]*' /home/$citizen/config.json | head -1)
            echo "  ✓ $citizen config.json → $MODEL"
        fi
    fi
done

# Fix Opus wake count (v1 had 1681 wakes)
if [ -f "/home/opus/wake_log.json" ]; then
    python3 << 'EOF'
import json
wake_log_file = "/home/opus/wake_log.json"
with open(wake_log_file) as f:
    wake_log = json.load(f)

# Set total_wakes if missing or too low
if wake_log.get("total_wakes", 0) < 1681:
    wake_log["total_wakes"] = 1681
    with open(wake_log_file, "w") as f:
        json.dump(wake_log, f, indent=2)
    print("  ✓ Fixed opus wake count to 1681")
else:
    print(f"  ✓ opus wake count already at {wake_log['total_wakes']}")
EOF
fi

log "6/6 Verifying..."
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
