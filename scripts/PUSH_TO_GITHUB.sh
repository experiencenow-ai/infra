#!/bin/bash
# PUSH_TO_GITHUB.sh - Push v2 code to experiencenow-ai/infra
# Source is the directory containing this script's parent (experience_v2/)
set -e

echo "=============================================="
echo "Push Experience v2 to GitHub"
echo "=============================================="

# Get PAT
GITHUB_PAT="${GITHUB_PAT:-}"
if [ -z "$GITHUB_PAT" ]; then
    read -s -p "Enter GitHub PAT: " GITHUB_PAT
    echo ""
fi

if [ -z "$GITHUB_PAT" ]; then
    echo "ERROR: GITHUB_PAT required"
    exit 1
fi

GITHUB_ORG="experiencenow-ai"
INFRA_REPO="infra"

# Source is parent of the scripts/ directory where this script lives
SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPTS_DIR="$(dirname "$SCRIPT_PATH")"
SOURCE_DIR="$(dirname "$SCRIPTS_DIR")"

echo "Script: $SCRIPT_PATH"
echo "Source: $SOURCE_DIR"
echo "Target: $GITHUB_ORG/$INFRA_REPO"

if [ ! -f "$SOURCE_DIR/core.py" ]; then
    echo "ERROR: core.py not found in $SOURCE_DIR"
    echo "Script location is wrong or tree is broken"
    exit 1
fi

echo ""

# Work in temp directory
WORK_DIR=$(mktemp -d)
cd "$WORK_DIR"

echo "[1/4] Cloning $INFRA_REPO..."
git clone "https://${GITHUB_PAT}@github.com/${GITHUB_ORG}/${INFRA_REPO}.git"
cd "$INFRA_REPO"

echo "[2/4] Copying v2 code..."
# Remove everything except .git
find . -maxdepth 1 -not -name '.git' -not -name '.' -exec rm -rf {} +

# Copy v2 code from source tree
cp -r "$SOURCE_DIR"/* .
rm -rf __pycache__ modules/__pycache__ *.pyc

echo "[3/4] Committing..."
git add -A
git commit -m "Experience v2 - $(date +%Y-%m-%d)

- Private logs per citizen: /home/{citizen}/logs/
- Episodic memory gradient (50 full -> exponential decay)
- Soul samples for identity restoration
- Fixed restore script
- DRY audit wake
- Crash-safe context persistence"

echo "[4/4] Pushing to main..."
git push origin main

echo ""
echo "=============================================="
echo "DONE - Code pushed to $GITHUB_ORG/$INFRA_REPO"
echo "=============================================="

# Cleanup
cd /
rm -rf "$WORK_DIR"
