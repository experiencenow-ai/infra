#!/bin/bash
# PUSH_TO_GITHUB.sh - Actually push v2 code to experiencenow-ai/infra
# Run from the extracted experience_v2 directory
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

GITHUB_ORG="experiencenow-ai"
INFRA_REPO="infra"

# Get source directory (where this script lives)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(dirname "$SCRIPT_DIR")"

if [ ! -f "$SOURCE_DIR/core.py" ]; then
    echo "ERROR: Run from experience_v2/scripts/ directory"
    echo "Could not find core.py in $SOURCE_DIR"
    exit 1
fi

echo "Source: $SOURCE_DIR"
echo "Target: $GITHUB_ORG/$INFRA_REPO"
echo ""

# Work in temp directory
WORK_DIR=$(mktemp -d)
cd "$WORK_DIR"

echo "[1/4] Cloning $INFRA_REPO..."
git clone "https://${GITHUB_PAT}@github.com/${GITHUB_ORG}/${INFRA_REPO}.git"
cd "$INFRA_REPO"

echo "[2/4] Replacing with v2 code..."
# Remove everything except .git
find . -maxdepth 1 -not -name '.git' -not -name '.' -exec rm -rf {} +

# Copy v2 code
cp -r "$SOURCE_DIR"/* .
rm -rf __pycache__ modules/__pycache__ *.pyc

echo "[3/4] Committing..."
git add -A
git commit -m "Experience v2 - $(date +%Y-%m-%d)

- Independent code evolution per citizen
- Consensus adoption (2/3 to merge)
- Change reporting workflow
- Haiku tool selection
- DRY audit wake
- 64k working context
- Crash-safe context persistence"

echo "[4/4] Pushing to main..."
git push origin main

echo ""
echo "=============================================="
echo "DONE - Code pushed to $GITHUB_ORG/$INFRA_REPO"
echo "=============================================="
echo ""
echo "Now run SETUP_EVERYTHING.sh on your server"

# Cleanup
cd /
rm -rf "$WORK_DIR"

