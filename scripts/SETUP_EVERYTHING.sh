#!/bin/bash
# SETUP_EVERYTHING.sh - Setup Experience v2 on server
# Prerequisites: PUSH_TO_GITHUB.sh has been run (code is in infra repo)
set -e

echo "=============================================="
echo "Experience v2 - Server Setup"
echo "=============================================="

if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Run as root"
    exit 1
fi

# Config
GITHUB_ORG="experiencenow-ai"
CITIZENS="opus mira aria"
EMAIL_DOMAIN="${EMAIL_DOMAIN:-experiencenow.ai}"
IMAP_SERVER="${IMAP_SERVER:-imap.experiencenow.ai}"
SMTP_SERVER="${SMTP_SERVER:-smtp.experiencenow.ai}"

# Get credentials
GITHUB_PAT="${GITHUB_PAT:-}"
if [ -z "$GITHUB_PAT" ]; then
    read -s -p "GitHub PAT: " GITHUB_PAT
    echo ""
fi

ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"
if [ -z "$ANTHROPIC_API_KEY" ]; then
    read -s -p "Anthropic API Key: " ANTHROPIC_API_KEY
    echo ""
fi

declare -A EMAIL_PASS
for c in $CITIZENS; do
    read -s -p "Email password for ${c}@${EMAIL_DOMAIN}: " EMAIL_PASS[$c]
    echo ""
done

echo ""
echo "[1/7] Creating users..."
getent group citizens >/dev/null || groupadd citizens
for c in $CITIZENS; do
    id "$c" &>/dev/null || { useradd -m -s /bin/bash "$c"; usermod -aG citizens "$c"; }
    echo "  $c: OK"
done

echo "[2/7] Creating directories..."
mkdir -p /home/shared/{baseline,library/{modules,pending},tools/{impl,registry}}
for c in $CITIZENS; do
    mkdir -p /home/$c/{code,contexts,tasks/{queue,active,done,failed},logs,memory/{raw,daily,weekly,monthly}}
done
chown -R root:citizens /home/shared
chmod 775 /home/shared

echo "[3/7] Initializing shared files..."
[ -f /home/shared/adoptions.json ] || echo '{"changes":{}}' > /home/shared/adoptions.json
[ -f /home/shared/change_reports.json ] || echo '{"reports":[]}' > /home/shared/change_reports.json
[ -f /home/shared/dry_violations.json ] || echo '{"open":[],"fixed":[]}' > /home/shared/dry_violations.json
[ -f /home/shared/civ_goals.json ] || echo '[]' > /home/shared/civ_goals.json
chmod 664 /home/shared/*.json

echo "[4/7] Cloning infra repo..."
cd /home/shared
rm -rf baseline
git clone "https://${GITHUB_PAT}@github.com/${GITHUB_ORG}/infra.git" baseline
if [ ! -f baseline/core.py ]; then
    echo "ERROR: infra repo has no code. Run PUSH_TO_GITHUB.sh first!"
    exit 1
fi
chown -R root:citizens baseline
chmod -R 775 baseline
echo "  ✓ Cloned infra"

echo "[5/7] Deploying code to citizens..."
for c in $CITIZENS; do
    cp -r /home/shared/baseline/* /home/$c/code/
    chown -R $c:$c /home/$c/
    chmod 750 /home/$c
    echo "  $c: $([ -f /home/$c/code/core.py ] && echo '✓' || echo 'FAILED')"
done

echo "[6/7] Syncing citizen state from repos..."
for c in $CITIZENS; do
    TEMP=$(mktemp -d)
    if git clone "https://${GITHUB_PAT}@github.com/${GITHUB_ORG}/citizen-${c}.git" "$TEMP" 2>/dev/null; then
        [ -d "$TEMP/contexts" ] && cp -r "$TEMP/contexts/"* /home/$c/contexts/ 2>/dev/null
        [ -f "$TEMP/metadata.json" ] && cp "$TEMP/metadata.json" /home/$c/
        echo "  $c: synced from GitHub"
    else
        echo "  $c: no GitHub state (fresh start)"
    fi
    rm -rf "$TEMP"
    chown -R $c:$c /home/$c/
done

echo "[7/7] Creating .env files..."
for c in $CITIZENS; do
    cat > /home/$c/.env << EOF
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
IMAP_SERVER=${IMAP_SERVER}
SMTP_SERVER=${SMTP_SERVER}
EMAIL_USER=${c}@${EMAIL_DOMAIN}
EMAIL_PASS=${EMAIL_PASS[$c]}
GITHUB_PAT=${GITHUB_PAT}
EOF
    chown $c:$c /home/$c/.env
    chmod 600 /home/$c/.env
    echo "  $c: .env created"
done

# Initialize empty contexts if needed
for c in $CITIZENS; do
    for ctx in identity history goals relationships skills dreams working; do
        F="/home/$c/contexts/${ctx}.json"
        if [ ! -f "$F" ] || [ ! -s "$F" ]; then
            echo "{\"id\":\"${c}_${ctx}\",\"context_type\":\"${ctx}\",\"messages\":[]}" > "$F"
        fi
    done
    chown -R $c:$c /home/$c/contexts/
done

# Create systemd services
for c in $CITIZENS; do
    cat > /etc/systemd/system/experience-${c}.service << EOF
[Unit]
Description=Experience v2 - ${c}
After=network.target

[Service]
Type=simple
User=${c}
WorkingDirectory=/home/${c}/code
EnvironmentFile=/home/${c}/.env
ExecStart=/usr/bin/python3 core.py --citizen ${c} --loop
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF
done
systemctl daemon-reload

echo ""
echo "=============================================="
echo "SETUP COMPLETE"
echo "=============================================="
echo ""
echo "Resurrect each citizen:"
echo "  sudo -u opus python3 /home/opus/code/core.py --citizen opus --wake"
echo "  sudo -u mira python3 /home/mira/code/core.py --citizen mira --wake"
echo "  sudo -u aria python3 /home/aria/code/core.py --citizen aria --wake"
echo ""
echo "Run continuously:"
echo "  systemctl start experience-opus"
echo ""
