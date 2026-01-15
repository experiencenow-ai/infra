#!/bin/bash
# deploy_v2.sh - Deploy Experience v2 and create PR directly
#
# Usage:
#   ./deploy_v2.sh              # Create PR
#   ./deploy_v2.sh --merge      # Create and auto-merge

set -e

GITHUB_ORG="experiencenow-ai"
GITHUB_REPO="experience"
BRANCH="v2-upgrade-$(date +%Y%m%d)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

log() { echo -e "\033[0;32m[+]\033[0m $1"; }
warn() { echo -e "\033[1;33m[!]\033[0m $1"; }
error() { echo -e "\033[0;31m[ERROR]\033[0m $1"; exit 1; }

DO_MERGE=false
[ "$1" = "--merge" ] && DO_MERGE=true

echo "=========================================="
echo "  Experience v2 - Deploy to GitHub"
echo "=========================================="

cd "$REPO_DIR"

# Check gh CLI
command -v gh &>/dev/null || error "Install GitHub CLI: apt install gh"
gh auth status &>/dev/null || error "Run: gh auth login"

# Init git if needed
if [ ! -d ".git" ]; then
    log "Initializing git..."
    git init
    git remote add origin "git@github.com:$GITHUB_ORG/$GITHUB_REPO.git"
fi

git config user.email "deploy@experiencenow.ai" 2>/dev/null || true
git config user.name "Experience Deploy" 2>/dev/null || true

# Stage and commit
git add -A
log "Changes:"
git status --short

git checkout -B "$BRANCH"

if ! git diff --cached --quiet; then
    git commit -m "Experience v2 Complete Framework

Safety:
- Cost circuit breaker (\$0.50/wake max)
- Tool call deduplication
- Auto-fail on max iterations
- Atomic JSON writes
- Context backup before truncate

Features:
- Background task scheduler (replaces cron)
- Blockchain tools (Etherscan API)
- Personal experiences (searchable)
- Cross-backup system
- Email-triggered wakes
- Experience integration in tasks

Run:
  sudo ./scripts/setup_accounts.sh
  ./scripts/sync_citizen.py --all
  ./run.sh --all --interval 300"
fi

# Push
log "Pushing $BRANCH..."
git push -u origin "$BRANCH" --force

# Create PR
log "Creating PR..."

PR_BODY="## v2 Complete Framework

### Safety Features
- Cost circuit breaker: \$0.50/wake max
- Tool deduplication: warn after 3 identical calls
- Auto-fail: max iterations → task_stuck
- Atomic JSON writes: crash-safe
- Context backup: save before hard truncate

### New Features
- Background tasks (no cron)
- Blockchain tracking (Etherscan)
- Personal experiences (searchable)
- Cross-backup (peers backup each other)
- Email triggers (ct@ = immediate wake)
- Experience integration in task prompts

### Setup
\`\`\`bash
sudo ./scripts/setup_accounts.sh
./scripts/sync_citizen.py --all
./run.sh --all --interval 300
\`\`\`"

EXISTING=$(gh pr list --head "$BRANCH" --json number --jq '.[0].number' 2>/dev/null || echo "")

if [ -n "$EXISTING" ]; then
    PR_URL="https://github.com/$GITHUB_ORG/$GITHUB_REPO/pull/$EXISTING"
    warn "PR #$EXISTING exists"
else
    PR_URL=$(gh pr create --title "🚀 Experience v2" --body "$PR_BODY" --base main --head "$BRANCH")
    log "PR created"
fi

[ "$DO_MERGE" = true ] && gh pr merge "$BRANCH" --auto --squash

echo ""
echo "=========================================="
log "Done: $PR_URL"
echo "=========================================="
