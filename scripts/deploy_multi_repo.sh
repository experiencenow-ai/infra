#!/bin/bash
# deploy_multi_repo.sh - Deploy to EXISTING Experience Now repositories
#
# Existing repos at https://github.com/experiencenow-ai:
#   infra          - Core v2 codebase
#   protocols      - Governance, templates, library
#   citizen-opus   - Opus state
#   citizen-mira   - Mira state
#   citizen-aria   - Aria state
#
# Usage:
#   ./deploy_multi_repo.sh                 # Create PRs in all repos
#   ./deploy_multi_repo.sh --repo infra    # Only infra repo
#   ./deploy_multi_repo.sh --merge         # Create and merge all

set -e

GITHUB_ORG="experiencenow-ai"
BRANCH="v2-$(date +%Y%m%d)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

log() { echo -e "\033[0;32m[+]\033[0m $1"; }
warn() { echo -e "\033[1;33m[!]\033[0m $1"; }
error() { echo -e "\033[0;31m[ERROR]\033[0m $1"; exit 1; }

DO_MERGE=false
TARGET_REPO=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --merge) DO_MERGE=true; shift ;;
        --repo) TARGET_REPO="$2"; shift 2 ;;
        --help) echo "Usage: $0 [--repo NAME] [--merge]"; echo "Repos: infra, protocols, opus, mira, aria"; exit 0 ;;
        *) error "Unknown: $1" ;;
    esac
done

command -v gh &>/dev/null || error "Install GitHub CLI: apt install gh"
gh auth status &>/dev/null || error "Authenticate: gh auth login"

echo "=========================================="
echo "  Deploy to EXISTING repos at"
echo "  github.com/$GITHUB_ORG"
echo "=========================================="

# Clone existing repo, update content, push PR
deploy_repo() {
    local repo="$1"
    local src_dir="$2"
    local msg="$3"
    local title="$4"
    
    log "Deploying to $GITHUB_ORG/$repo..."
    local tmp="/tmp/deploy-$repo-$$"
    rm -rf "$tmp"
    
    # Clone existing repo (preserves history)
    git clone --depth=1 "https://github.com/$GITHUB_ORG/$repo.git" "$tmp" 2>/dev/null || \
    git clone --depth=1 "git@github.com:$GITHUB_ORG/$repo.git" "$tmp" || \
    error "Failed to clone $repo - does it exist?"
    
    cd "$tmp"
    git config user.email "deploy@experiencenow.ai"
    git config user.name "Experience Deploy"
    
    # Feature branch from main
    git fetch origin main 2>/dev/null || true
    git checkout -B "$BRANCH" origin/main 2>/dev/null || git checkout -B "$BRANCH"
    
    # Update content (keep .git)
    find . -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} +
    if [ -d "$src_dir" ]; then
        cp -a "$src_dir"/. . 2>/dev/null || true
    fi
    
    git add -A
    git diff --cached --quiet || git commit -m "$msg"
    git push -u origin "$BRANCH" --force
    
    # Create/update PR
    if ! gh pr list --head "$BRANCH" --json number | grep -q number; then
        gh pr create --title "$title" --body "v2 upgrade" --base main --head "$BRANCH" 2>/dev/null || true
    fi
    [ "$DO_MERGE" = true ] && gh pr merge "$BRANCH" --squash --auto 2>/dev/null || true
    
    rm -rf "$tmp"
    log "Done: $repo"
}

# INFRA = core v2 codebase
deploy_infra() {
    deploy_repo "infra" "$REPO_DIR" \
        "Experience v2 - complete rewrite" "🚀 v2"
}

# PROTOCOLS = governance, templates, library
deploy_protocols() {
    local tmp="/tmp/src-protocols-$$"
    mkdir -p "$tmp/library" "$tmp/templates"
    
    [ -d "$REPO_DIR/templates" ] && cp -r "$REPO_DIR/templates"/* "$tmp/templates/"
    [ -d "$REPO_DIR/docs" ] && cp -r "$REPO_DIR/docs"/* "$tmp/"
    [ -d "/home/shared/library" ] && cp -r /home/shared/library/* "$tmp/library/" 2>/dev/null
    
    deploy_repo "protocols" "$tmp" "v2 protocols and library" "📚 v2 protocols"
    rm -rf "$tmp"
}

# CITIZEN repos = individual state
deploy_citizen() {
    local c="$1"
    local tmp="/tmp/src-citizen-$c-$$"
    mkdir -p "$tmp/contexts"
    
    [ -d "/home/$c/contexts" ] && cp -r "/home/$c/contexts"/* "$tmp/contexts/" 2>/dev/null
    [ -f "/home/$c/config.json" ] && cp "/home/$c/config.json" "$tmp/"
    [ -f "/home/$c/metadata.json" ] && cp "/home/$c/metadata.json" "$tmp/"
    
    echo "# citizen-$c" > "$tmp/README.md"
    echo "Persistent state for $c." >> "$tmp/README.md"
    
    deploy_repo "citizen-$c" "$tmp" "$c v2 sync" "🔄 $c v2"
    rm -rf "$tmp"
}

case "$TARGET_REPO" in
    infra) deploy_infra ;;
    protocols) deploy_protocols ;;
    opus) deploy_citizen opus ;;
    mira) deploy_citizen mira ;;
    aria) deploy_citizen aria ;;
    "")
        deploy_infra
        deploy_protocols
        deploy_citizen opus
        deploy_citizen mira
        deploy_citizen aria
        ;;
    *) error "Unknown: $TARGET_REPO (use: infra, protocols, opus, mira, aria)" ;;
esac

echo ""
log "Complete! Review PRs at https://github.com/$GITHUB_ORG"
