#!/bin/bash
# setup_full.sh - Complete Experience v2 Setup
# 
# This script sets up everything needed for Experience v2:
# 1. System users and directories
# 2. Email configuration (experiencenow.ai)
# 3. GitHub CLI and authentication
# 4. SSH keys for all citizens
# 5. Git configuration
# 6. Initial contexts
#
# Run as root on the main server
#
# Usage:
#   ./setup_full.sh              # Interactive setup
#   ./setup_full.sh --headless   # Non-interactive with defaults

set -e

# Configuration
CITIZENS="opus mira aria"
DOMAIN="experiencenow.ai"
GITHUB_ORG="experiencenow-ai"
GITHUB_REPO="experience_v2"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

echo "=========================================="
echo "  Experience v2 - Complete Setup"
echo "  Domain: $DOMAIN"
echo "  GitHub: $GITHUB_ORG/$GITHUB_REPO"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    error "Please run as root"
fi

# Parse arguments
HEADLESS=false
GITHUB_PAT=""
for arg in "$@"; do
    case $arg in
        --headless)
            HEADLESS=true
            shift
            ;;
        --pat=*)
            GITHUB_PAT="${arg#*=}"
            shift
            ;;
    esac
done

# =============================================================================
# Step 1: System Setup
# =============================================================================
log "Step 1: System Setup"

# Create citizens group
if ! getent group citizens > /dev/null; then
    groupadd citizens
    log "Created citizens group"
else
    log "Citizens group already exists"
fi

# Install required packages
log "Installing required packages..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip git curl jq > /dev/null 2>&1
pip3 install anthropic --break-system-packages -q 2>/dev/null || pip3 install anthropic -q

# Install GitHub CLI if not present
if ! command -v gh &> /dev/null; then
    log "Installing GitHub CLI..."
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg 2>/dev/null
    chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null
    apt-get update -qq && apt-get install -y -qq gh > /dev/null 2>&1
fi

# =============================================================================
# Step 2: Shared Directory
# =============================================================================
log "Step 2: Creating shared directories"

mkdir -p /home/shared/{code,protocols,constitution,public}
mkdir -p /home/shared/library/{modules,pending,skills}
chown -R root:citizens /home/shared
chmod 775 /home/shared
chmod -R 775 /home/shared/*

# Initialize shared files
echo '[]' > /home/shared/civ_goals.json 2>/dev/null || true
echo '{}' > /home/shared/pr_tracker.json 2>/dev/null || true
echo '[]' > /home/shared/help_wanted.json 2>/dev/null || true
echo '[]' > /home/shared/bulletin_board.json 2>/dev/null || true
chmod 664 /home/shared/*.json

# Library index
if [ ! -f "/home/shared/library/index.json" ]; then
    cat > /home/shared/library/index.json << 'EOF'
{
  "version": 1,
  "modules": {},
  "maintainers": {
    "git": "opus",
    "python": "opus",
    "email": "mira",
    "unix": "opus",
    "crypto": "opus",
    "blockchain": "opus"
  },
  "approval_threshold": 0.67,
  "pending_prs": []
}
EOF
    chmod 664 /home/shared/library/index.json
fi

# NOTE: Library starts EMPTY. No pre-seeded modules.
# AI citizens learn through:
# 1. web_search when they don't know something
# 2. experience_add to capture learnings
# 3. library_propose to share knowledge (requires peer review)
# This prevents "cheating" by giving AI pre-loaded answers.

log "Shared directories created"

# =============================================================================
# Step 3: Create Citizens
# =============================================================================
log "Step 3: Creating citizen accounts"

for citizen in $CITIZENS; do
    echo ""
    echo "  Setting up $citizen..."
    
    # Create user if not exists
    if ! id "$citizen" &>/dev/null; then
        useradd -m -s /bin/bash "$citizen"
        usermod -aG citizens "$citizen"
        echo "    Created user $citizen"
    fi
    
    # Create directory structure
    mkdir -p /home/$citizen/{contexts,tasks/{queue,active,done,failed,quarantine},goals,rollback,inbox,outbox,logs,private,.ssh}
    mkdir -p /home/$citizen/memory/{raw,daily,weekly,monthly,annual}
    
    # Set ownership and permissions
    chown -R $citizen:$citizen /home/$citizen
    chmod 750 /home/$citizen
    chmod 700 /home/$citizen/private
    chmod 700 /home/$citizen/.ssh
    
    # Create empty context files
    for ctx in identity history goals relationships skills dreams working peer_monitor; do
        ctx_file="/home/$citizen/contexts/${ctx}.json"
        if [ ! -f "$ctx_file" ]; then
            cat > "$ctx_file" << EOF
{
  "id": "${citizen}_${ctx}",
  "context_type": "${ctx}",
  "created": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "last_modified": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "token_count": 0,
  "max_tokens": 10000,
  "messages": []
}
EOF
            chown $citizen:$citizen "$ctx_file"
        fi
    done
    
    # Create metadata
    if [ ! -f "/home/$citizen/metadata.json" ]; then
        cat > "/home/$citizen/metadata.json" << EOF
{
  "citizen": "$citizen",
  "wake_count": 0,
  "created": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "last_wake": null,
  "total_tokens_used": 0,
  "total_cost": 0.0
}
EOF
        chown $citizen:$citizen "/home/$citizen/metadata.json"
    fi
    
    # Create action log
    if [ ! -f "/home/$citizen/action_log.json" ]; then
        echo '{"completed": {}}' > "/home/$citizen/action_log.json"
        chown $citizen:$citizen "/home/$citizen/action_log.json"
    fi
    
    # Create email processed log
    if [ ! -f "/home/$citizen/email_processed.json" ]; then
        echo '[]' > "/home/$citizen/email_processed.json"
        chown $citizen:$citizen "/home/$citizen/email_processed.json"
    fi
    
    # Create config.json
    config_file="/home/$citizen/config.json"
    if [ ! -f "$config_file" ]; then
        cat > "$config_file" << EOF
{
  "name": "$citizen",
  "email": "${citizen}@${DOMAIN}",
  
  "council": [
    {"model": "claude-sonnet-4-20250514", "role": "primary", "temperature": 0.7}
  ],
  
  "context_limits": {
    "identity": {"max_tokens": 5000, "forget_strategy": "never"},
    "history": {"max_tokens": 30000, "forget_strategy": "compress_oldest"},
    "goals": {"max_tokens": 10000, "forget_strategy": "archive_completed"},
    "relationships": {"max_tokens": 8000, "forget_strategy": "compress"},
    "skills": {"max_tokens": 15000, "forget_strategy": "compress_oldest"},
    "dreams": {"max_tokens": 10000, "forget_strategy": "keep_recent_n", "n": 20},
    "working": {"max_tokens": 40000, "forget_strategy": "clear_on_task_complete"},
    "peer_monitor": {"max_tokens": 8000, "forget_strategy": "keep_recent_n", "n": 10}
  },
  
  "permissions": {
    "can_onboard_citizens": $([ "$citizen" = "opus" ] && echo "true" || echo "false"),
    "can_modify_protocols": false,
    "can_access_other_home": true,
    "can_modify_shared_code": false,
    "can_request_help": true
  },
  
  "email_config": {
    "smtp_host": "mail.${DOMAIN}",
    "smtp_port": 587,
    "imap_host": "mail.${DOMAIN}",
    "imap_port": 993,
    "password_env": "EMAIL_PASSWORD"
  }
}
EOF
        chown $citizen:$citizen "$config_file"
        chmod 600 "$config_file"
    fi
    
    # Create .env with email password = username
    env_file="/home/$citizen/.env"
    cat > "$env_file" << EOF
# API Keys
ANTHROPIC_API_KEY=sk-ant-REPLACE_WITH_REAL_KEY

# Etherscan API (for blockchain tracking)
ETHERSCAN_API_KEY=YOUR_ETHERSCAN_V2_KEY

# Email password = username for experiencenow.ai
EMAIL_PASSWORD=$citizen
EOF
    chown $citizen:$citizen "$env_file"
    chmod 600 "$env_file"
    
    log "  $citizen account created"
done

# =============================================================================
# Step 4: SSH Keys
# =============================================================================
log "Step 4: Generating SSH keys"

for citizen in $CITIZENS; do
    key_path="/home/$citizen/.ssh/id_ed25519"
    
    if [ ! -f "$key_path" ]; then
        ssh-keygen -t ed25519 -f "$key_path" -N "" -C "${citizen}@${DOMAIN}" > /dev/null 2>&1
        chown $citizen:$citizen "$key_path" "$key_path.pub"
        chmod 600 "$key_path"
        chmod 644 "$key_path.pub"
        log "  Generated SSH key for $citizen"
    else
        log "  SSH key already exists for $citizen"
    fi
done

# =============================================================================
# Step 5: GitHub Setup
# =============================================================================
log "Step 5: GitHub Setup"

# Check if gh is authenticated
if ! gh auth status &>/dev/null; then
    if [ -n "$GITHUB_PAT" ]; then
        echo "$GITHUB_PAT" | gh auth login --with-token
        log "Authenticated gh with provided PAT"
    elif [ "$HEADLESS" = false ]; then
        warn "GitHub CLI not authenticated. Running interactive login..."
        gh auth login
    else
        warn "GitHub CLI not authenticated. Skipping GitHub setup."
        warn "Run 'gh auth login' manually later."
    fi
fi

# Add SSH keys to GitHub if authenticated
if gh auth status &>/dev/null; then
    for citizen in $CITIZENS; do
        pub_key=$(cat /home/$citizen/.ssh/id_ed25519.pub)
        
        # Check if key already exists
        if gh ssh-key list | grep -q "${citizen}@${DOMAIN}"; then
            log "  SSH key for $citizen already on GitHub"
        else
            echo "$pub_key" | gh ssh-key add - --title "${citizen}@${DOMAIN}" 2>/dev/null && \
                log "  Added SSH key for $citizen to GitHub" || \
                warn "  Could not add SSH key for $citizen (may already exist)"
        fi
    done
fi

# =============================================================================
# Step 6: Git Configuration
# =============================================================================
log "Step 6: Git Configuration"

for citizen in $CITIZENS; do
    gitconfig="/home/$citizen/.gitconfig"
    cat > "$gitconfig" << EOF
[user]
    name = $citizen
    email = ${citizen}@${DOMAIN}

[init]
    defaultBranch = main

[pull]
    rebase = false

[core]
    editor = nano
EOF
    chown $citizen:$citizen "$gitconfig"
done

# =============================================================================
# Step 7: Clone Repository
# =============================================================================
log "Step 7: Setting up repository"

BASELINE="/home/shared/baseline"

if [ ! -d "$BASELINE" ]; then
    if gh auth status &>/dev/null; then
        gh repo clone $GITHUB_ORG/$GITHUB_REPO "$BASELINE" 2>/dev/null || \
            git clone "https://github.com/$GITHUB_ORG/$GITHUB_REPO.git" "$BASELINE" 2>/dev/null || \
            warn "Could not clone repo. Copy manually to $BASELINE"
    else
        warn "GitHub not authenticated. Clone repo manually:"
        warn "  git clone https://github.com/$GITHUB_ORG/$GITHUB_REPO.git $BASELINE"
    fi
else
    log "Baseline already exists at $BASELINE"
fi

if [ -d "$BASELINE" ]; then
    chown -R root:citizens "$BASELINE"
    chmod -R 775 "$BASELINE"
fi

# Copy baseline to each citizen's code directory
log "Copying baseline to citizen code directories..."
for citizen in $CITIZENS; do
    CITIZEN_CODE="/home/$citizen/code"
    if [ -d "$BASELINE" ] && [ ! -d "$CITIZEN_CODE/core.py" ]; then
        mkdir -p "$CITIZEN_CODE"
        cp -r "$BASELINE"/* "$CITIZEN_CODE"/ 2>/dev/null || true
        chown -R $citizen:$citizen "$CITIZEN_CODE"
        log "  Copied baseline to $CITIZEN_CODE"
    fi
done

# =============================================================================
# Step 8: Systemd Service (Optional)
# =============================================================================
log "Step 8: Creating systemd service (optional)"

# Create systemd service file for each citizen
for citizen in $CITIZENS; do
    SERVICE_FILE="/etc/systemd/system/experience-${citizen}.service"
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Experience v2 - ${citizen}
After=network.target

[Service]
Type=simple
User=${citizen}
WorkingDirectory=/home/${citizen}/code
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=/home/${citizen}/.env
ExecStart=/usr/bin/python3 /home/${citizen}/code/core.py --citizen ${citizen} --loop --interval 600
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF
    chmod 644 "$SERVICE_FILE"
done

log "Systemd services created (not enabled by default)"
echo "    To enable: systemctl enable experience-opus"
echo "    To start:  systemctl start experience-opus"
echo ""
echo "    Or use screen: ./run.sh --all"

# =============================================================================
# Step 9: Verify Setup
# =============================================================================
log "Step 9: Verifying setup"

echo ""
echo "=========================================="
echo "  Setup Verification"
echo "=========================================="

ERRORS=0

for citizen in $CITIZENS; do
    echo ""
    echo "  $citizen:"
    
    # Check user
    if id "$citizen" &>/dev/null; then
        echo "    ✓ User exists"
    else
        echo "    ✗ User missing"
        ((ERRORS++))
    fi
    
    # Check directories
    if [ -d "/home/$citizen/contexts" ]; then
        echo "    ✓ Directories created"
    else
        echo "    ✗ Directories missing"
        ((ERRORS++))
    fi
    
    # Check SSH key
    if [ -f "/home/$citizen/.ssh/id_ed25519" ]; then
        fingerprint=$(ssh-keygen -lf /home/$citizen/.ssh/id_ed25519.pub 2>/dev/null | awk '{print $2}')
        echo "    ✓ SSH key: $fingerprint"
    else
        echo "    ✗ SSH key missing"
        ((ERRORS++))
    fi
    
    # Check config
    if [ -f "/home/$citizen/config.json" ]; then
        echo "    ✓ Config exists"
    else
        echo "    ✗ Config missing"
        ((ERRORS++))
    fi
    
    # Check .env
    if [ -f "/home/$citizen/.env" ]; then
        if grep -q "sk-ant-REPLACE" "/home/$citizen/.env"; then
            echo "    ! .env needs API key"
        else
            echo "    ✓ .env configured"
        fi
    else
        echo "    ✗ .env missing"
        ((ERRORS++))
    fi
done

echo ""
echo "=========================================="

if [ $ERRORS -eq 0 ]; then
    log "Setup complete with no errors!"
else
    warn "Setup completed with $ERRORS errors"
fi

echo ""
echo "Next steps:"
echo "  1. Edit /home/<citizen>/.env with real ANTHROPIC_API_KEY"
echo "  2. Test email: python3 /home/shared/baseline/scripts/test_email.py"
echo "  3. Run citizens:"
echo ""
echo "     # Single citizen in loop mode:"
echo "     ./run.sh opus"
echo ""
echo "     # All citizens in screen sessions:"
echo "     ./run.sh --all"
echo ""
echo "     # Interactive mode for testing:"
echo "     ./core.py --citizen opus --interactive"
echo ""
echo "     # Or use systemd:"
echo "     systemctl enable experience-opus"
echo "     systemctl start experience-opus"
echo ""
echo "Email credentials:"
echo "  Domain: mail.$DOMAIN"
echo "  Passwords: opus/mira/aria (same as username)"
echo ""
echo "Background tasks (heartbeat, news, prices, etc.) run automatically"
echo "inside the experience loop. No cron needed!"
echo ""
