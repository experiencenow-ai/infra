#!/bin/bash
# SETUP_EVERYTHING.sh - Full automated setup for Experience v2
# Run ONCE as root on the server
# 
# Repos used:
#   experiencenow-ai/infra        - Shared code (core.py, modules/, etc.)
#   experiencenow-ai/citizen-opus - Opus state/contexts
#   experiencenow-ai/citizen-mira - Mira state/contexts
#   experiencenow-ai/citizen-aria - Aria state/contexts
#
set -e

echo "=============================================="
echo "Experience v2 - FULL AUTOMATED SETUP"
echo "=============================================="
echo ""

# Check root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Run as root"
    exit 1
fi

# Configuration
GITHUB_ORG="experiencenow-ai"
INFRA_REPO="infra"
CITIZENS="opus mira aria"
EMAIL_DOMAIN="${EMAIL_DOMAIN:-experiencenow.ai}"
IMAP_SERVER="${IMAP_SERVER:-imap.experiencenow.ai}"
SMTP_SERVER="${SMTP_SERVER:-smtp.experiencenow.ai}"

# Get GitHub PAT
GITHUB_PAT="${GITHUB_PAT:-}"
if [ -z "$GITHUB_PAT" ]; then
    read -s -p "Enter GitHub Personal Access Token: " GITHUB_PAT
    echo ""
fi

if [ -z "$GITHUB_PAT" ]; then
    echo "ERROR: GitHub PAT required"
    exit 1
fi
echo "  ✓ GitHub PAT configured"
echo ""

# Get API key
ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"
if [ -z "$ANTHROPIC_API_KEY" ]; then
    read -p "Enter Anthropic API key: " ANTHROPIC_API_KEY
fi

# Get email passwords
declare -A EMAIL_PASSWORDS
for citizen in $CITIZENS; do
    read -s -p "Enter email password for ${citizen}@${EMAIL_DOMAIN}: " pass
    echo ""
    EMAIL_PASSWORDS[$citizen]="$pass"
done

echo ""
echo "[1/9] Creating users and groups..."

if ! getent group citizens > /dev/null; then
    groupadd citizens
fi

for citizen in $CITIZENS; do
    if ! id "$citizen" &>/dev/null; then
        useradd -m -s /bin/bash "$citizen"
        usermod -aG citizens "$citizen"
        echo "  Created user: $citizen"
    else
        echo "  User exists: $citizen"
    fi
done

echo "[2/9] Creating directory structure..."

# Shared directories
mkdir -p /home/shared/{baseline,library/{modules,pending,skills},tools/{impl,registry,pending,tests}}
chown -R root:citizens /home/shared
chmod 775 /home/shared
chmod -R 775 /home/shared/*

# Shared JSON files
[ ! -f /home/shared/adoptions.json ] && echo '{"changes": {}, "baseline_version": "v1"}' > /home/shared/adoptions.json
[ ! -f /home/shared/change_reports.json ] && echo '{"reports": []}' > /home/shared/change_reports.json
[ ! -f /home/shared/dry_violations.json ] && echo '{"open": [], "fixed": [], "last_audit": {}}' > /home/shared/dry_violations.json
[ ! -f /home/shared/civ_goals.json ] && echo '[]' > /home/shared/civ_goals.json
[ ! -f /home/shared/pr_tracker.json ] && echo '{}' > /home/shared/pr_tracker.json
chmod 664 /home/shared/*.json

# Citizen directories
for citizen in $CITIZENS; do
    mkdir -p /home/$citizen/{code,contexts,tasks/{queue,active,done,failed},goals,logs,memory/{raw,daily,weekly,monthly},private}
    chown -R $citizen:$citizen /home/$citizen
    chmod 750 /home/$citizen
    chmod 700 /home/$citizen/private
done

echo "[3/9] Cloning infra repo to baseline..."

cd /home/shared
if [ -d baseline/.git ]; then
    echo "  Updating existing baseline..."
    cd baseline && git pull origin main && cd ..
else
    echo "  Cloning fresh..."
    rm -rf baseline
    git clone "https://${GITHUB_PAT}@github.com/${GITHUB_ORG}/${INFRA_REPO}.git" baseline
fi
chown -R root:citizens /home/shared/baseline
chmod -R 775 /home/shared/baseline

echo "[4/9] Deploying code to each citizen..."

for citizen in $CITIZENS; do
    echo "  Deploying to $citizen..."
    rm -rf /home/$citizen/code/*
    cp -r /home/shared/baseline/* /home/$citizen/code/
    chown -R $citizen:$citizen /home/$citizen/code/
done

echo "[5/9] Syncing citizen state from repos..."

for citizen in $CITIZENS; do
    CITIZEN_REPO="citizen-${citizen}"
    CITIZEN_DIR="/home/$citizen"
    
    echo "  Syncing $citizen from $CITIZEN_REPO..."
    
    # Clone to temp and copy contexts
    TEMP_DIR=$(mktemp -d)
    
    if git clone "https://${GITHUB_PAT}@github.com/${GITHUB_ORG}/${CITIZEN_REPO}.git" "$TEMP_DIR" 2>/dev/null; then
        # Copy contexts if they exist
        if [ -d "$TEMP_DIR/contexts" ]; then
            cp -r "$TEMP_DIR/contexts/"* "$CITIZEN_DIR/contexts/" 2>/dev/null || true
            echo "    Copied contexts"
        fi
        # Copy any other state files
        for f in metadata.json config.json; do
            if [ -f "$TEMP_DIR/$f" ]; then
                cp "$TEMP_DIR/$f" "$CITIZEN_DIR/" 2>/dev/null || true
            fi
        done
    else
        echo "    Could not clone $CITIZEN_REPO (may not exist yet)"
    fi
    
    rm -rf "$TEMP_DIR"
    chown -R $citizen:$citizen "$CITIZEN_DIR"
done

echo "[6/9] Creating environment files..."

for citizen in $CITIZENS; do
    cat > /home/$citizen/.env << EOF
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
IMAP_SERVER=${IMAP_SERVER}
SMTP_SERVER=${SMTP_SERVER}
EMAIL_USER=${citizen}@${EMAIL_DOMAIN}
EMAIL_PASS=${EMAIL_PASSWORDS[$citizen]}
EOF
    chown $citizen:$citizen /home/$citizen/.env
    chmod 600 /home/$citizen/.env
    echo "  Created .env for: $citizen"
done

echo "[7/9] Initializing missing contexts..."

for citizen in $CITIZENS; do
    # Initialize identity from template if missing
    if [ ! -f /home/$citizen/contexts/identity.json ] || [ ! -s /home/$citizen/contexts/identity.json ]; then
        if [ -f /home/$citizen/code/templates/identity_templates.json ]; then
            python3 << PYEOF
import json
from pathlib import Path

templates = json.loads(Path("/home/$citizen/code/templates/identity_templates.json").read_text())
citizen_template = templates.get("$citizen", templates.get("opus", {}))

identity = {
    "id": "${citizen}_identity",
    "context_type": "identity",
    "created": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "last_modified": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "token_count": 0,
    "max_tokens": 10000,
    "messages": citizen_template.get("messages", [])
}

Path("/home/$citizen/contexts/identity.json").write_text(json.dumps(identity, indent=2))
PYEOF
            echo "  Initialized identity for: $citizen"
        fi
    fi
    
    # Create empty contexts if missing
    for ctx in history goals relationships skills dreams working peer_monitor; do
        ctx_file="/home/$citizen/contexts/${ctx}.json"
        if [ ! -f "$ctx_file" ] || [ ! -s "$ctx_file" ]; then
            cat > "$ctx_file" << EOF
{
  "id": "${citizen}_${ctx}",
  "context_type": "${ctx}",
  "created": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "last_modified": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "token_count": 0,
  "messages": []
}
EOF
        fi
    done
    chown -R $citizen:$citizen /home/$citizen/contexts/
done

echo "[8/9] Creating systemd services..."

for citizen in $CITIZENS; do
    cat > /etc/systemd/system/experience-${citizen}.service << EOF
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
done

systemctl daemon-reload
echo "  Services created (not started)"

echo "[9/9] Creating resurrect script..."

cat > /home/shared/resurrect.sh << 'RESURRECT_EOF'
#!/bin/bash
# Resurrect a citizen - run as the citizen or as root with citizen name
set -e

if [ "$EUID" -eq 0 ]; then
    CITIZEN="${1:-}"
    if [ -z "$CITIZEN" ]; then
        echo "Usage: ./resurrect.sh CITIZEN"
        exit 1
    fi
    RUN_AS="sudo -u $CITIZEN"
else
    CITIZEN="$(whoami)"
    RUN_AS=""
fi

echo "=============================================="
echo "Resurrecting: $CITIZEN"
echo "=============================================="

CODE_DIR="/home/$CITIZEN/code"

if [ ! -f "$CODE_DIR/core.py" ]; then
    echo "ERROR: No code at $CODE_DIR"
    exit 1
fi

if [ ! -f "/home/$CITIZEN/.env" ]; then
    echo "ERROR: No .env file"
    exit 1
fi

echo ""
echo "Contexts:"
for ctx in identity history goals; do
    if [ -f "/home/$CITIZEN/contexts/${ctx}.json" ]; then
        tokens=$(python3 -c "import json; print(json.load(open('/home/$CITIZEN/contexts/${ctx}.json')).get('token_count', 0))" 2>/dev/null || echo "?")
        echo "  ✓ ${ctx}: ${tokens} tokens"
    else
        echo "  ✗ ${ctx}: MISSING"
    fi
done

echo ""
echo "Running wake..."
echo "=============================================="

cd "$CODE_DIR"
$RUN_AS python3 core.py --citizen "$CITIZEN" --wake

echo ""
echo "=============================================="
echo "Done! To run continuously:"
echo "  systemctl start experience-$CITIZEN"
echo "=============================================="
RESURRECT_EOF

chmod +x /home/shared/resurrect.sh
cp /home/shared/resurrect.sh /home/shared/baseline/resurrect.sh

echo ""
echo "=============================================="
echo "SETUP COMPLETE"
echo "=============================================="
echo ""
echo "To resurrect each citizen:"
echo "  sudo -u opus /home/shared/resurrect.sh opus"
echo "  sudo -u mira /home/shared/resurrect.sh mira"
echo "  sudo -u aria /home/shared/resurrect.sh aria"
echo ""
echo "To run continuously:"
echo "  systemctl start experience-opus"
echo "  systemctl start experience-mira"
echo "  systemctl start experience-aria"
echo ""

