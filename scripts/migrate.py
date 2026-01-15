#!/usr/bin/env python3
"""
Migration Script - Migrate from Experience v1 to v2.

This script:
1. Reads existing state.json files from v1
2. Creates v2 directory structure
3. Migrates identity, history, goals
4. Updates config with new email domain (experiencenow.ai)
5. Preserves wake counts and costs
6. Generates SSH keys if needed
7. Updates git configuration

Usage:
    ./migrate.py --citizen opus --source /root/opus
    ./migrate.py --all
    ./migrate.py --all --dry-run  # Preview what would happen
"""

import argparse
import json
import shutil
import subprocess
import os
from datetime import datetime, timezone
from pathlib import Path

# Configuration
DOMAIN = "experiencenow.ai"
GITHUB_ORG = "experiencenow-ai"

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def run_cmd(cmd, check=False):
    """Run shell command and return output."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0, result.stdout.strip()
    except:
        return False, ""


def migrate_citizen(citizen: str, source_dir: Path, templates_dir: Path, dry_run: bool = False):
    """Migrate a single citizen from v1 to v2."""
    print(f"\n{'='*60}")
    print(f"Migrating {citizen}")
    print(f"  Source: {source_dir}")
    print(f"  Target: /home/{citizen}")
    print(f"  Dry run: {dry_run}")
    print('='*60)
    
    target_dir = Path(f"/home/{citizen}")
    
    # Check source
    old_state_file = source_dir / "state.json"
    old_state = {}
    
    if old_state_file.exists():
        print(f"\n  [+] Found v1 state.json")
        try:
            old_state = json.loads(old_state_file.read_text())
            print(f"      Wake count: {old_state.get('total_wakes', 0)}")
            print(f"      Total cost: ${old_state.get('total_cost', 0):.2f}")
            print(f"      Last wake: {old_state.get('last_wake', 'unknown')}")
        except Exception as e:
            print(f"  [!] Could not parse state.json: {e}")
    else:
        print(f"\n  [!] No v1 state.json found at {source_dir}")
        print(f"      Starting fresh")
    
    # Load templates
    configs = {}
    identities = {}
    
    if (templates_dir / "citizen_configs.json").exists():
        configs = json.loads((templates_dir / "citizen_configs.json").read_text())
    if (templates_dir / "identity_templates.json").exists():
        identities = json.loads((templates_dir / "identity_templates.json").read_text())
    
    if dry_run:
        print(f"\n  [DRY RUN] Would create directories and files")
        print(f"  [DRY RUN] Would migrate {len(old_state.get('recent_thoughts', []))} thoughts")
        print(f"  [DRY RUN] Would preserve {old_state.get('total_wakes', 0)} wake count")
        return
    
    # Create directories
    print(f"\n  [+] Creating directory structure...")
    dirs = [
        "contexts",
        "tasks/queue", "tasks/active", "tasks/done", "tasks/failed", "tasks/quarantine",
        "logs", "private", ".ssh",
        "memory/raw", "memory/daily", "memory/weekly", "memory/monthly", "memory/annual"
    ]
    for d in dirs:
        (target_dir / d).mkdir(parents=True, exist_ok=True)
    
    # Get config template
    config = configs.get(citizen, configs.get("opus", {}))
    
    # Update email domain
    config["email"] = f"{citizen}@{DOMAIN}"
    if "email_config" in config:
        config["email_config"]["smtp_host"] = f"mail.{DOMAIN}"
        config["email_config"]["imap_host"] = f"mail.{DOMAIN}"
    
    # Create config.json
    config_file = target_dir / "config.json"
    if not config_file.exists() or old_state:
        print(f"  [+] Creating config.json")
        config_file.write_text(json.dumps(config, indent=2))
    
    # Create .env with password = username
    env_file = target_dir / ".env"
    if not env_file.exists():
        print(f"  [+] Creating .env (password = {citizen})")
        env_content = f"""# API Keys
ANTHROPIC_API_KEY=sk-ant-REPLACE_WITH_REAL_KEY

# Etherscan API (for blockchain tracking)
ETHERSCAN_API_KEY=YOUR_ETHERSCAN_V2_KEY

# Email password = username for {DOMAIN}
EMAIL_PASSWORD={citizen}
"""
        env_file.write_text(env_content)
        os.chmod(env_file, 0o600)
    
    # Migrate identity
    identity_ctx = identities.get(citizen, {
        "id": f"{citizen}_identity",
        "context_type": "identity",
        "max_tokens": 5000,
        "messages": []
    })
    
    if old_state:
        # Add migration note
        identity_ctx["messages"].append({
            "role": "system",
            "content": f"[MIGRATION] Migrated from v1 on {now_iso()}. Previous wake count: {old_state.get('total_wakes', 0)}. Total cost: ${old_state.get('total_cost', 0):.2f}"
        })
        
        # Preserve key insights
        insights = old_state.get("key_insights", [])
        if insights:
            identity_ctx["messages"].append({
                "role": "assistant",
                "content": "Key insights from v1:\n" + "\n".join(f"- {i}" for i in insights[-10:])
            })
    
    identity_file = target_dir / "contexts" / "identity.json"
    identity_ctx["created"] = now_iso()
    identity_ctx["last_modified"] = now_iso()
    identity_ctx["token_count"] = sum(len(m.get("content", "")) // 4 for m in identity_ctx.get("messages", []))
    identity_file.write_text(json.dumps(identity_ctx, indent=2))
    print(f"  [+] Created identity context")
    
    # Migrate history
    history_ctx = {
        "id": f"{citizen}_history",
        "context_type": "history",
        "created": now_iso(),
        "last_modified": now_iso(),
        "max_tokens": 30000,
        "token_count": 0,
        "messages": []
    }
    
    if old_state:
        history_ctx["messages"].append({
            "role": "system",
            "content": f"[MIGRATED] Started v2 with {old_state.get('total_wakes', 0)} wakes from v1"
        })
        
        # Add recent thoughts
        for t in old_state.get("recent_thoughts", [])[-30:]:
            history_ctx["messages"].append({
                "role": "assistant",
                "content": f"[Wake {t.get('wake', '?')}] {t.get('thought', '')[:500]}"
            })
    
    history_ctx["token_count"] = sum(len(m.get("content", "")) // 4 for m in history_ctx["messages"])
    (target_dir / "contexts" / "history.json").write_text(json.dumps(history_ctx, indent=2))
    print(f"  [+] Created history context ({len(history_ctx['messages'])} entries)")
    
    # Create other contexts
    for ctx_type in ["goals", "relationships", "skills", "dreams", "working", "peer_monitor"]:
        ctx_file = target_dir / "contexts" / f"{ctx_type}.json"
        if not ctx_file.exists():
            ctx = {
                "id": f"{citizen}_{ctx_type}",
                "context_type": ctx_type,
                "created": now_iso(),
                "last_modified": now_iso(),
                "max_tokens": config.get("context_limits", {}).get(ctx_type, {}).get("max_tokens", 10000),
                "token_count": 0,
                "messages": []
            }
            if ctx_type == "goals":
                ctx["structured"] = {"active": [], "completed": []}
            ctx_file.write_text(json.dumps(ctx, indent=2))
    print(f"  [+] Created remaining contexts")
    
    # Create metadata
    metadata = {
        "citizen": citizen,
        "wake_count": old_state.get("total_wakes", 0),
        "created": now_iso(),
        "migrated_from_v1": now_iso(),
        "v1_total_cost": old_state.get("total_cost", 0),
        "last_wake": None,
        "total_tokens_used": 0,
        "total_cost": 0.0  # Reset for v2 tracking
    }
    (target_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
    print(f"  [+] Created metadata")
    
    # Create other required files
    if not (target_dir / "action_log.json").exists():
        (target_dir / "action_log.json").write_text('{"completed": {}}')
    
    if not (target_dir / "email_processed.json").exists():
        (target_dir / "email_processed.json").write_text('[]')
    
    # Generate SSH key if needed
    ssh_key = target_dir / ".ssh" / "id_ed25519"
    if not ssh_key.exists():
        print(f"  [+] Generating SSH key...")
        os.makedirs(target_dir / ".ssh", exist_ok=True)
        subprocess.run([
            "ssh-keygen", "-t", "ed25519", 
            "-f", str(ssh_key), 
            "-N", "", 
            "-C", f"{citizen}@{DOMAIN}"
        ], capture_output=True)
        os.chmod(ssh_key, 0o600)
        os.chmod(ssh_key.with_suffix(".pub"), 0o644)
        
        # Get fingerprint
        ok, fingerprint = run_cmd(["ssh-keygen", "-lf", str(ssh_key.with_suffix(".pub"))])
        if ok:
            print(f"      Fingerprint: {fingerprint.split()[1] if ' ' in fingerprint else fingerprint}")
    
    # Create .gitconfig
    gitconfig = target_dir / ".gitconfig"
    gitconfig.write_text(f"""[user]
    name = {citizen}
    email = {citizen}@{DOMAIN}

[init]
    defaultBranch = main

[pull]
    rebase = false
""")
    print(f"  [+] Created .gitconfig")
    
    # Set ownership (if running as root)
    if os.geteuid() == 0:
        subprocess.run(["chown", "-R", f"{citizen}:{citizen}", str(target_dir)], capture_output=True)
        subprocess.run(["chmod", "750", str(target_dir)], capture_output=True)
        subprocess.run(["chmod", "700", str(target_dir / "private")], capture_output=True)
        subprocess.run(["chmod", "700", str(target_dir / ".ssh")], capture_output=True)
        subprocess.run(["chmod", "600", str(target_dir / "config.json")], capture_output=True)
        subprocess.run(["chmod", "600", str(target_dir / ".env")], capture_output=True)
    
    print(f"\n  ✓ {citizen} migration complete!")
    print(f"    Wake count: {metadata['wake_count']}")
    print(f"    Email: {citizen}@{DOMAIN}")
    print(f"    Password: {citizen}")


def add_ssh_keys_to_github():
    """Add all citizen SSH keys to GitHub."""
    print("\n" + "="*60)
    print("Adding SSH Keys to GitHub")
    print("="*60)
    
    # Check if gh is authenticated
    ok, _ = run_cmd(["gh", "auth", "status"])
    if not ok:
        print("  [!] GitHub CLI not authenticated")
        print("      Run: gh auth login")
        return False
    
    for citizen in ["opus", "mira", "aria"]:
        pub_key_file = Path(f"/home/{citizen}/.ssh/id_ed25519.pub")
        if not pub_key_file.exists():
            print(f"  [!] No SSH key for {citizen}")
            continue
        
        pub_key = pub_key_file.read_text().strip()
        title = f"{citizen}@{DOMAIN}"
        
        # Check if key exists
        ok, existing = run_cmd(["gh", "ssh-key", "list"])
        if ok and title in existing:
            print(f"  [+] Key for {citizen} already on GitHub")
            continue
        
        # Add key
        result = subprocess.run(
            ["gh", "ssh-key", "add", "-", "--title", title],
            input=pub_key,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print(f"  [+] Added SSH key for {citizen}")
        elif "already exists" in result.stderr.lower():
            print(f"  [+] Key for {citizen} already exists")
        else:
            print(f"  [!] Failed to add key for {citizen}: {result.stderr}")
    
    return True


def main():
    parser = argparse.ArgumentParser(description="Migrate to Experience v2")
    parser.add_argument("--citizen", help="Specific citizen to migrate")
    parser.add_argument("--source", help="Source directory for citizen")
    parser.add_argument("--all", action="store_true", help="Migrate all citizens")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")
    parser.add_argument("--templates", default=None, help="Templates directory")
    parser.add_argument("--add-ssh-keys", action="store_true", help="Add SSH keys to GitHub after migration")
    args = parser.parse_args()
    
    # Find templates directory
    script_dir = Path(__file__).parent
    if args.templates:
        templates_dir = Path(args.templates)
    elif (script_dir.parent / "templates").exists():
        templates_dir = script_dir.parent / "templates"
    elif (script_dir / "templates").exists():
        templates_dir = script_dir / "templates"
    else:
        print("[!] Templates directory not found")
        templates_dir = Path(".")
    
    print(f"Using templates from: {templates_dir}")
    
    if args.citizen:
        source = Path(args.source) if args.source else Path(f"/root/{args.citizen}")
        migrate_citizen(args.citizen, source, templates_dir, args.dry_run)
    elif args.all:
        # Default v1 locations
        v1_sources = [
            ("opus", "/root/opus"),
            ("mira", "/root/mira"),
            ("aria", "/root/aria")
        ]
        
        for citizen, source in v1_sources:
            source_path = Path(source)
            migrate_citizen(citizen, source_path, templates_dir, args.dry_run)
        
        if args.add_ssh_keys and not args.dry_run:
            add_ssh_keys_to_github()
    else:
        print("Usage:")
        print("  ./migrate.py --citizen <n> --source <dir>")
        print("  ./migrate.py --all")
        print("  ./migrate.py --all --dry-run")
        print("  ./migrate.py --all --add-ssh-keys")


if __name__ == "__main__":
    main()
