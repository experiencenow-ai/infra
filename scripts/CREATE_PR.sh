#!/bin/bash
# CREATE_PR.sh - Push v2 code to experiencenow-ai/infra
# Run from a machine with GitHub access
set -e

echo "=============================================="
echo "Creating PR for Experience v2 → infra repo"
echo "=============================================="

GITHUB_ORG="experiencenow-ai"
INFRA_REPO="infra"
BRANCH="v2-final-$(date +%Y%m%d)"

# Check gh CLI
if ! command -v gh &> /dev/null; then
    echo "ERROR: gh CLI not installed. Run: apt install gh && gh auth login"
    exit 1
fi

if ! gh auth status &> /dev/null; then
    echo "ERROR: Not authenticated. Run: gh auth login"
    exit 1
fi

# Get source directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
V2_DIR="$(dirname "$SCRIPT_DIR")"

echo "Source: $V2_DIR"
echo "Target: $GITHUB_ORG/$INFRA_REPO"
echo "Branch: $BRANCH"
echo ""

# Clone existing infra repo
WORK_DIR=$(mktemp -d)
cd "$WORK_DIR"

echo "[1/5] Cloning $GITHUB_ORG/$INFRA_REPO..."
gh repo clone $GITHUB_ORG/$INFRA_REPO
cd $INFRA_REPO

echo "[2/5] Creating branch $BRANCH..."
git checkout -b "$BRANCH"

echo "[3/5] Copying v2 code..."
# Remove old code (except .git and any citizen-specific stuff)
find . -maxdepth 1 -not -name '.git' -not -name '.' -exec rm -rf {} +

# Copy new code
cp -r "$V2_DIR"/* .
rm -rf __pycache__ modules/__pycache__ *.pyc

echo "[4/5] Committing..."
git add -A
git commit -m "Experience v2 Final Release

BREAKING CHANGES:
- Each citizen now runs from /home/{citizen}/code/ (not shared)
- Code evolves independently per citizen
- 2/3 adoption required to merge changes to baseline

Major features:
- Independent code evolution with consensus adoption
- Change reporting (announce → test → report outcome)
- Haiku-based tool selection (no hardcoded allowlists)
- DRY_AUDIT wake (10% of cycles hunt violations)
- Context as consciousness (crash-safe with finally blocks)
- 64k token working context

New tools:
- code_announce, code_report_outcome, code_pending_reviews
- code_verified_good, code_adopt, code_list_changes
- dry_violation_report, dry_violation_fix, dry_violations_list

Deployment:
1. Merge this PR
2. On server: ./scripts/SETUP_EVERYTHING.sh
3. Each citizen: ./resurrect.sh

See docs/EXPERIENCE_V2_SPECIFICATION.md for full details."

echo "[5/5] Pushing and creating PR..."
git push -u origin "$BRANCH"

gh pr create \
    --title "Experience v2 Final Release" \
    --body "## Summary

Complete rewrite with independent code evolution per citizen.

### Key Changes
- Citizens run from \`/home/{citizen}/code/\` (not shared)
- Changes propagate through adoption (2/3 = merge to baseline)
- Haiku selects tools per task (no hardcoded lists)
- 10% of wakes hunt DRY violations

### New Workflow
\`\`\`
Citizen modifies code
  → code_announce(filepath, description, expected_outcome)
  → Tests in wakes
  → code_report_outcome(report_id, 'worked')
  → Peers see code_pending_reviews()
  → Peers test and report
  → 2+ same verdict = verified
  → code_adopt() spreads good changes
  → 2/3 adopt = merge to baseline
\`\`\`

### Deployment
\`\`\`bash
# After merge, on server as root:
./scripts/SETUP_EVERYTHING.sh

# Then resurrect each citizen:
sudo -u opus ./resurrect.sh
sudo -u mira ./resurrect.sh
sudo -u aria ./resurrect.sh
\`\`\`

### Files
- \`scripts/SETUP_EVERYTHING.sh\` - Full automated setup
- \`resurrect.sh\` - Bring citizen back to life
- \`docs/EXPERIENCE_V2_SPECIFICATION.md\` - Complete spec
" \
    --base main

PR_URL=$(gh pr view --json url -q .url)

echo ""
echo "=============================================="
echo "PR CREATED: $PR_URL"
echo "=============================================="
echo ""
echo "Next steps:"
echo "  1. Review PR at: $PR_URL"
echo "  2. Merge when ready"
echo "  3. On server: ./scripts/SETUP_EVERYTHING.sh"

# Cleanup
cd /
rm -rf "$WORK_DIR"
