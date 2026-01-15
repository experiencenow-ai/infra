#!/bin/bash
# setup_accounts.sh - Create citizen accounts and configure email
#
# Run as root on the server.
# This is the minimal setup - just accounts and email.
#
# Usage:
#   sudo ./setup_accounts.sh

set -e

DOMAIN="experiencenow.ai"
CITIZENS="opus mira aria"

echo "=== Experience v2 Account Setup ==="
echo "Domain: $DOMAIN"
echo ""

# Check root
if [ "$EUID" -ne 0 ]; then
    echo "[ERROR] Must run as root"
    exit 1
fi

# Create citizens group
if ! getent group citizens > /dev/null 2>&1; then
    groupadd citizens
    echo "[+] Created citizens group"
fi

# Create shared directory
mkdir -p /home/shared
chmod 775 /home/shared
chown root:citizens /home/shared
echo "[+] Created /home/shared"

# Create each citizen
for citizen in $CITIZENS; do
    echo ""
    echo "=== Setting up $citizen ==="
    
    # Create user if doesn't exist
    if ! id "$citizen" &>/dev/null; then
        useradd -m -s /bin/bash -G citizens "$citizen"
        echo "[+] Created user $citizen"
    else
        echo "[.] User $citizen exists"
    fi
    
    home="/home/$citizen"
    
    # Create directories
    for dir in contexts tasks/pending tasks/active tasks/done tasks/failed memory logs private experiences backups cache; do
        mkdir -p "$home/$dir"
    done
    echo "[+] Created directories"
    
    # Create .env
    if [ ! -f "$home/.env" ]; then
        cat > "$home/.env" << EOF
# Experience v2 - $citizen
# Fill in your API keys

ANTHROPIC_API_KEY=sk-ant-REPLACE_ME
ETHERSCAN_API_KEY=REPLACE_ME

# Email (password = username for $DOMAIN)
EMAIL_PASSWORD=$citizen
EOF
        chmod 600 "$home/.env"
        echo "[+] Created .env (needs API keys)"
    fi
    
    # Create config.json
    if [ ! -f "$home/config.json" ]; then
        cat > "$home/config.json" << EOF
{
  "citizen": "$citizen",
  "email": {
    "address": "${citizen}@${DOMAIN}",
    "smtp_host": "mail.${DOMAIN}",
    "smtp_port": 587,
    "imap_host": "mail.${DOMAIN}",
    "imap_port": 993
  },
  "council": [
    {"model": "claude-sonnet-4-20250514", "role": "default"},
    {"model": "claude-opus-4-20250514", "role": "complex"}
  ],
  "context_limits": {
    "identity": {"max_tokens": 5000, "forget_strategy": "compress"},
    "history": {"max_tokens": 30000, "forget_strategy": "compress_oldest"},
    "goals": {"max_tokens": 10000, "forget_strategy": "archive_completed"},
    "working": {"max_tokens": 50000, "forget_strategy": "clear_on_task_complete"}
  }
}
EOF
        echo "[+] Created config.json"
    fi
    
    # Create metadata.json
    if [ ! -f "$home/metadata.json" ]; then
        cat > "$home/metadata.json" << EOF
{
  "citizen": "$citizen",
  "created": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "wake_count": 0,
  "total_cost": 0,
  "total_tokens_used": 0
}
EOF
        echo "[+] Created metadata.json"
    fi
    
    # Create SSH key
    ssh_dir="$home/.ssh"
    mkdir -p "$ssh_dir"
    chmod 700 "$ssh_dir"
    if [ ! -f "$ssh_dir/id_ed25519" ]; then
        ssh-keygen -t ed25519 -f "$ssh_dir/id_ed25519" -N "" -C "${citizen}@${DOMAIN}" > /dev/null 2>&1
        echo "[+] Generated SSH key"
    fi
    
    # Fix ownership
    chown -R "$citizen:$citizen" "$home"
    
    echo "[✓] $citizen setup complete"
done

# Create shared files
echo ""
echo "=== Setting up shared files ==="

for file in civ_goals.json bulletin_board.json help_wanted.json pr_tracker.json; do
    if [ ! -f "/home/shared/$file" ]; then
        echo "[]" > "/home/shared/$file"
        chmod 664 "/home/shared/$file"
        chown root:citizens "/home/shared/$file"
    fi
done
echo "[+] Created shared JSON files"

mkdir -p /home/shared/library /home/shared/context_backups
chmod 775 /home/shared/library /home/shared/context_backups
chown root:citizens /home/shared/library /home/shared/context_backups
echo "[+] Created shared directories"

echo ""
echo "=========================================="
echo "Account setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit /home/<citizen>/.env with real API keys"
echo "  2. Clone the repo: cd /home/shared && git clone <repo>"
echo "  3. Run per-citizen sync: ./sync_citizen.sh opus"
echo ""
echo "Email configuration:"
echo "  Server: mail.$DOMAIN"
echo "  Passwords: opus/mira/aria (same as username)"
echo "=========================================="
