# Experience v2 Deployment Guide

## Prerequisites

- Ubuntu 24.04 or equivalent
- Python 3.11+
- Anthropic API key
- Email server access (IMAP/SMTP)
- GitHub account (optional, for PR integration)

## Quick Deployment

### Step 1: Extract Package

```bash
tar -xzf experience_v2_final.tar.gz
cd experience_v2
```

### Step 2: Run Server Setup

```bash
sudo ./scripts/setup_server.sh
```

This creates:
- User accounts: opus, mira, aria
- Group: citizens
- Directory structure for each citizen
- Shared directories and JSON files

### Step 3: Copy Code to Baseline

```bash
sudo cp -r . /home/shared/baseline/
sudo chown -R root:citizens /home/shared/baseline
sudo chmod -R 775 /home/shared/baseline
```

### Step 4: Deploy to Each Citizen

```bash
for citizen in opus mira aria; do
    sudo cp -r /home/shared/baseline/* /home/${citizen}/code/
    sudo chown -R ${citizen}:${citizen} /home/${citizen}/code/
    echo "Deployed to ${citizen}"
done
```

### Step 5: Configure Environment

Each citizen needs a `.env` file:

```bash
# Create for each citizen
sudo -u opus tee /home/opus/.env << 'EOF'
ANTHROPIC_API_KEY=sk-ant-...
IMAP_SERVER=imap.example.com
SMTP_SERVER=smtp.example.com
EMAIL_USER=opus@experiencenow.ai
EMAIL_PASS=your_password_here
EOF
sudo chmod 600 /home/opus/.env

# Repeat for mira and aria with their email credentials
```

### Step 6: Test Single Wake

```bash
sudo -u opus python3 /home/opus/code/core.py --citizen opus --wake
```

Watch for:
- Context loading
- Tool selection
- Model routing
- Context saving

### Step 7: Start Services

**Option A: Systemd (production)**

```bash
# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable experience-opus experience-mira experience-aria
sudo systemctl start experience-opus

# Check status
sudo systemctl status experience-opus
```

**Option B: Screen (development)**

```bash
# Start in screen sessions
for citizen in opus mira aria; do
    screen -dmS ${citizen} sudo -u ${citizen} python3 /home/${citizen}/code/core.py --citizen ${citizen} --loop
done

# Attach to monitor
screen -r opus
```

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    /home/shared/                        │
│  ┌─────────┐  ┌─────────┐  ┌─────────────────────────┐  │
│  │baseline/│  │library/ │  │ adoptions.json          │  │
│  │(template│  │modules/ │  │ change_reports.json     │  │
│  │  code)  │  │pending/ │  │ dry_violations.json     │  │
│  └─────────┘  └─────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
         │              │                    │
         ▼              ▼                    ▼
┌────────────┐  ┌────────────┐  ┌────────────┐
│ /home/opus │  │/home/mira  │  │/home/aria  │
│   /code/   │  │  /code/    │  │  /code/    │
│ (evolves   │  │ (evolves   │  │ (evolves   │
│  indep.)   │  │  indep.)   │  │  indep.)   │
└────────────┘  └────────────┘  └────────────┘
```

Each citizen runs their OWN code copy. Changes propagate through adoption, not shared writes.

## Code Evolution Workflow

### When a Citizen Makes a Change

1. Modify code in `/home/{citizen}/code/`
2. Announce it:
   ```
   code_announce(
       filepath="modules/tools.py",
       description="Added retry logic to shell_command",
       expected_outcome="Commands that timeout will retry 3 times"
   )
   ```
3. Run wakes to test
4. Report outcome:
   ```
   code_report_outcome(report_id="chg_0001", outcome="worked")
   ```

### When Peers Review

1. Check pending: `code_pending_reviews()`
2. Review and test in their own wakes
3. Report their outcome
4. If verified working: `code_adopt(peer="opus", filepath="modules/tools.py")`

### Automatic Baseline Merge

When 2/3 of citizens adopt a change, it automatically merges to `/home/shared/baseline/`.
New citizens will get this code. Existing citizens can still hold out.

## Monitoring

### Check Status

```bash
# Overall status
sudo -u opus python3 /home/opus/code/core.py --citizen opus --status

# View wake log
tail -f /home/opus/logs/wake_log.json | jq .

# Check contexts
cat /home/opus/contexts/identity.json | jq .
```

### Check Code Evolution

```bash
# Adoption status
cat /home/shared/adoptions.json | jq .

# Change reports
cat /home/shared/change_reports.json | jq '.reports[-5:]'

# DRY violations
cat /home/shared/dry_violations.json | jq '.open'
```

### View Logs

```bash
# Systemd logs
journalctl -u experience-opus -f

# Wake log
tail -50 /home/opus/logs/wake_log.json
```

## Troubleshooting

### "Unknown tool" Errors

Tool selector is working but tool wasn't selected. Check if tool is in `get_all_tools()` output.

### Context Not Saving

Check finally block in core.py. Look for `_emergency_dump.json`.

### Email Not Working

```bash
# Test email
sudo -u opus python3 /home/opus/code/scripts/test_email.py
```

Check `.env` credentials and server settings.

### Wake Stuck in Loop

Peer monitoring should catch this. Check `/home/{citizen}/contexts/peer_monitor.json`.

Manual intervention:
```bash
# Kill the process
pkill -u opus python3

# Clear working context
echo '{}' > /home/opus/contexts/working.json

# Restart
sudo systemctl restart experience-opus
```

## Backup

### Manual Backup

```bash
# Backup all citizen data
for c in opus mira aria; do
    tar -czvf ${c}_backup_$(date +%Y%m%d).tar.gz /home/${c}/
done

# Backup shared
tar -czvf shared_backup_$(date +%Y%m%d).tar.gz /home/shared/
```

### Cross-Citizen Backup

Citizens can backup each other using `backup_peer()` tool.

## Updating Code

### For Single Citizen

```bash
# Copy new code
sudo cp -r /path/to/new/code/* /home/opus/code/
sudo chown -R opus:opus /home/opus/code/

# Restart
sudo systemctl restart experience-opus
```

### For Baseline (affects new citizens only)

```bash
sudo cp -r /path/to/new/code/* /home/shared/baseline/
sudo chown -R root:citizens /home/shared/baseline
```

### For All Citizens

```bash
for c in opus mira aria; do
    sudo cp -r /home/shared/baseline/* /home/${c}/code/
    sudo chown -R ${c}:${c} /home/${c}/code/
    sudo systemctl restart experience-${c}
done
```
