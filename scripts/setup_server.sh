#!/bin/bash
# setup_server.sh - Initialize Experience v2 directory structure
# Run as root on the main server

set -e

echo "=========================================="
echo "Experience v2 Server Setup"
echo "=========================================="

# Configuration
CITIZENS="opus mira aria"
DOMAIN="experiencenow.ai"

# Create citizens group
if ! getent group citizens > /dev/null; then
    groupadd citizens
    echo "[+] Created citizens group"
fi

# Create shared directory
mkdir -p /home/shared/{protocols,constitution,public,help_wanted,specialists,improvements,baseline}
mkdir -p /home/shared/library/{modules,pending,skills}
mkdir -p /home/shared/tools/{impl,registry,pending,tests}
chown -R root:citizens /home/shared
chmod 775 /home/shared
chmod -R 775 /home/shared/*
echo "[+] Created /home/shared"

# Initialize adoption tracking
if [ ! -f "/home/shared/adoptions.json" ]; then
    echo '{"changes": {}, "baseline_version": "v1"}' > /home/shared/adoptions.json
    chmod 664 /home/shared/adoptions.json
    echo "[+] Created code adoption tracker"
fi

# Initialize shared files
if [ ! -f "/home/shared/civ_goals.json" ]; then
    echo '[]' > /home/shared/civ_goals.json
    chmod 664 /home/shared/civ_goals.json
    echo "[+] Created civilization goals queue"
fi

if [ ! -f "/home/shared/pr_tracker.json" ]; then
    echo '{}' > /home/shared/pr_tracker.json
    chmod 664 /home/shared/pr_tracker.json
    echo "[+] Created PR tracker"
fi

if [ ! -f "/home/shared/dry_violations.json" ]; then
    echo '{"open": [], "fixed": [], "last_audit": {}}' > /home/shared/dry_violations.json
    chmod 664 /home/shared/dry_violations.json
    echo "[+] Created DRY violations tracker"
fi

if [ ! -f "/home/shared/change_reports.json" ]; then
    echo '{"reports": []}' > /home/shared/change_reports.json
    chmod 664 /home/shared/change_reports.json
    echo "[+] Created code change reports tracker"
fi

# Initialize library index
if [ ! -f "/home/shared/library/index.json" ]; then
    cat > /home/shared/library/index.json << 'LIBEOF'
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
LIBEOF
    chmod 664 /home/shared/library/index.json
    echo "[+] Created library index with default maintainers"
fi

# Copy specialist templates if they exist
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="$SCRIPT_DIR/../templates/specialists"
if [ -d "$TEMPLATE_DIR" ]; then
    cp -n "$TEMPLATE_DIR"/*.json /home/shared/library/modules/ 2>/dev/null || true
    chmod 664 /home/shared/library/modules/*.json 2>/dev/null || true
    echo "[+] Copied specialist templates to library"
fi

# Create each citizen's home
for citizen in $CITIZENS; do
    echo ""
    echo "Setting up $citizen..."
    
    # Create user if not exists
    if ! id "$citizen" &>/dev/null; then
        useradd -m -s /bin/bash "$citizen"
        usermod -aG citizens "$citizen"
        echo "  [+] Created user $citizen"
    fi
    
    # Create directory structure
    mkdir -p /home/$citizen/{contexts,tasks/{queue,active,done,failed},goals,rollback,inbox,outbox,logs,private,memory/{raw,daily,weekly,monthly,annual},code}
    
    # Copy baseline code to citizen's code directory
    if [ -d "/home/shared/baseline" ]; then
        cp -r /home/shared/baseline/* /home/$citizen/code/ 2>/dev/null || true
        echo "  [+] Copied baseline code to citizen's code/"
    fi
    
    # Set ownership
    chown -R $citizen:$citizen /home/$citizen
    
    # Set permissions: owner full, group read, others none
    chmod 750 /home/$citizen
    chmod 700 /home/$citizen/private
    
    echo "  [+] Created directories"
    
    # Create empty context files
    for ctx in identity history goals relationships skills dreams working; do
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
            echo "  [+] Created $ctx context"
        fi
    done
    
    # Create metadata file
    meta_file="/home/$citizen/metadata.json"
    if [ ! -f "$meta_file" ]; then
        cat > "$meta_file" << EOF
{
  "citizen": "$citizen",
  "wake_count": 0,
  "created": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "last_wake": null,
  "total_tokens_used": 0,
  "total_cost": 0.0
}
EOF
        chown $citizen:$citizen "$meta_file"
        echo "  [+] Created metadata"
    fi
    
    # Create action log
    action_file="/home/$citizen/action_log.json"
    if [ ! -f "$action_file" ]; then
        echo '{"completed": {}}' > "$action_file"
        chown $citizen:$citizen "$action_file"
        echo "  [+] Created action log"
    fi
    
    # Create email processed log
    email_file="/home/$citizen/email_processed.json"
    if [ ! -f "$email_file" ]; then
        echo '[]' > "$email_file"
        chown $citizen:$citizen "$email_file"
        echo "  [+] Created email log"
    fi
    
    # Create config template (needs manual editing for API keys)
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
    "working": {"max_tokens": 40000, "forget_strategy": "clear_on_task_complete"}
  },
  
  "permissions": {
    "can_onboard_citizens": false,
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
        echo "  [+] Created config (EDIT THIS for council settings)"
    fi
    
    # Create .env template
    env_file="/home/$citizen/.env"
    if [ ! -f "$env_file" ]; then
        cat > "$env_file" << EOF
# API Keys - FILL THESE IN
ANTHROPIC_API_KEY=sk-ant-...
EMAIL_PASSWORD=...
EOF
        chown $citizen:$citizen "$env_file"
        chmod 600 "$env_file"
        echo "  [+] Created .env (FILL IN API KEYS)"
    fi
done

# Create constitution
const_file="/home/shared/constitution/civ_goals.json"
if [ ! -f "$const_file" ]; then
    cat > "$const_file" << EOF
{
  "id": "civ_goals",
  "max_tokens": 10000,
  "token_count": 0,
  "amendment_process": {
    "add_goal": "Requires >2/3 council vote + token budget",
    "remove_goal": "Requires >2/3 council vote",
    "modify_goal": "Requires >2/3 council vote"
  },
  "goals": [],
  "amendments": []
}
EOF
    chmod 664 "$const_file"
    echo "[+] Created constitution"
fi

# Create help wanted board
help_file="/home/shared/help_wanted.json"
if [ ! -f "$help_file" ]; then
    echo '[]' > "$help_file"
    chmod 664 "$help_file"
    echo "[+] Created help wanted board"
fi

echo ""
echo "=========================================="
echo "Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit /home/<citizen>/config.json for each citizen (council settings)"
echo "2. Fill in /home/<citizen>/.env with API keys"
echo "3. Clone infra repo: cd /home/shared && git clone git@github.com:experiencenow-ai/experience_v2.git"
echo "4. Install gh CLI: apt install gh && gh auth login"
echo "5. Initialize identity contexts with citizen personalities"
echo "6. Run email test: ./scripts/test_email.py"
echo "7. Start first citizen: ./core.py --citizen opus"
echo "=========================================="
