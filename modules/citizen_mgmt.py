"""
Citizen Management - Onboarding new citizens and SSH key management.

Only Opus (with can_onboard_citizens=true) can create new citizens.
New citizens get:
1. System user created
2. Directory structure
3. SSH key generated  
4. SSH key added to GitHub (via Opus's PAT)
5. Git configured
6. Identity context initialized
"""

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

def now_iso():
    return datetime.now(timezone.utc).isoformat()


# GitHub configuration
GITHUB_ORG = "experiencenow-ai"
GITHUB_REPO = "experience_v2"  # Repo name within org


def check_permission(session: dict) -> bool:
    """Check if citizen has onboarding permission."""
    config = session.get("config", {})
    return config.get("permissions", {}).get("can_onboard_citizens", False)


def create_citizen(new_citizen: str, session: dict, modules: dict) -> str:
    """
    Create a new citizen. Only Opus can do this.
    
    Steps:
    1. Check permission
    2. Create system user
    3. Create directories (via setup_server.sh pattern)
    4. Generate SSH key
    5. Add SSH key to GitHub
    6. Configure git
    7. Initialize identity context
    """
    citizen = session["citizen"]
    
    # Permission check
    if not check_permission(session):
        return f"ERROR: {citizen} does not have onboarding permission"
    
    # Validate citizen name
    if not new_citizen or not new_citizen.isalnum():
        return "ERROR: Citizen name must be alphanumeric"
    
    if len(new_citizen) > 20:
        return "ERROR: Citizen name too long (max 20 chars)"
    
    new_home = Path(f"/home/{new_citizen}")
    if new_home.exists():
        return f"ERROR: Citizen {new_citizen} already exists"
    
    # Use idempotency
    from modules import action_log
    if action_log.is_done(citizen, "initialize_citizen", {"new_citizen": new_citizen}):
        return f"ALREADY DONE: {new_citizen} was already created"
    
    try:
        # 1. Create system user
        result = _create_system_user(new_citizen)
        if not result["success"]:
            return f"ERROR creating user: {result['error']}"
        
        # 2. Create directories
        result = _create_directories(new_citizen)
        if not result["success"]:
            return f"ERROR creating directories: {result['error']}"
        
        # 3. Generate SSH key
        key_result = _generate_ssh_key(new_citizen)
        if not key_result["success"]:
            return f"ERROR generating SSH key: {key_result['error']}"
        
        # 4. Add SSH key to GitHub (using Opus's PAT)
        gh_result = _add_ssh_key_to_github(new_citizen, key_result["public_key"])
        if not gh_result["success"]:
            # Non-fatal - can be done manually
            print(f"[WARN] GitHub SSH key setup failed: {gh_result['error']}")
        
        # 5. Configure git
        _configure_git(new_citizen)
        
        # 6. Initialize contexts
        _initialize_contexts(new_citizen)
        
        # 7. Create config
        _create_config(new_citizen, session)
        
        # Mark as done
        action_log.mark_done(citizen, "initialize_citizen", 
                           {"new_citizen": new_citizen}, 
                           f"Created citizen {new_citizen}")
        
        # Notify
        _notify_citizens(new_citizen, session, modules)
        
        return f"""
CITIZEN CREATED: {new_citizen}
Home: /home/{new_citizen}
SSH Key: {key_result.get('fingerprint', 'generated')}
GitHub: {gh_result.get('message', 'pending')}

Next steps:
1. Edit /home/{new_citizen}/.env with API keys
2. Edit /home/{new_citizen}/config.json for council settings
3. Initialize identity context
4. Run first wake: ./core.py --citizen {new_citizen}
"""
    
    except Exception as e:
        return f"ERROR: {e}"


def _create_system_user(citizen: str) -> dict:
    """Create system user."""
    try:
        # Check if user exists
        result = subprocess.run(["id", citizen], capture_output=True)
        if result.returncode == 0:
            return {"success": True, "message": "User already exists"}
        
        # Create user
        result = subprocess.run(
            ["useradd", "-m", "-s", "/bin/bash", citizen],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return {"success": False, "error": result.stderr}
        
        # Add to citizens group
        subprocess.run(["usermod", "-aG", "citizens", citizen])
        
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _create_directories(citizen: str) -> dict:
    """Create citizen directory structure."""
    try:
        home = Path(f"/home/{citizen}")
        
        dirs = [
            "contexts",
            "tasks/queue",
            "tasks/active",
            "tasks/done",
            "tasks/failed",
            "logs",
            "private",
            "memory/raw",
            "memory/daily",
            "memory/weekly",
            "memory/monthly",
            "memory/annual",
            ".ssh"
        ]
        
        for d in dirs:
            (home / d).mkdir(parents=True, exist_ok=True)
        
        # Set permissions
        subprocess.run(["chown", "-R", f"{citizen}:{citizen}", str(home)])
        subprocess.run(["chmod", "750", str(home)])
        subprocess.run(["chmod", "700", str(home / "private")])
        subprocess.run(["chmod", "700", str(home / ".ssh")])
        
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _generate_ssh_key(citizen: str) -> dict:
    """Generate SSH key for citizen."""
    try:
        home = Path(f"/home/{citizen}")
        key_path = home / ".ssh" / "id_ed25519"
        
        if key_path.exists():
            # Key already exists, read public key
            pub_key = (key_path.with_suffix(".pub")).read_text().strip()
            fingerprint = _get_key_fingerprint(key_path.with_suffix(".pub"))
            return {
                "success": True,
                "public_key": pub_key,
                "fingerprint": fingerprint,
                "message": "Key already exists"
            }
        
        # Generate new key
        result = subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-f", str(key_path), 
             "-N", "", "-C", f"{citizen}@experiencenow"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            return {"success": False, "error": result.stderr}
        
        # Set ownership
        subprocess.run(["chown", f"{citizen}:{citizen}", str(key_path)])
        subprocess.run(["chown", f"{citizen}:{citizen}", str(key_path.with_suffix(".pub"))])
        subprocess.run(["chmod", "600", str(key_path)])
        subprocess.run(["chmod", "644", str(key_path.with_suffix(".pub"))])
        
        pub_key = key_path.with_suffix(".pub").read_text().strip()
        fingerprint = _get_key_fingerprint(key_path.with_suffix(".pub"))
        
        return {
            "success": True,
            "public_key": pub_key,
            "fingerprint": fingerprint
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _get_key_fingerprint(pub_key_path: Path) -> str:
    """Get SSH key fingerprint."""
    try:
        result = subprocess.run(
            ["ssh-keygen", "-lf", str(pub_key_path)],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return result.stdout.strip().split()[1]
        return "unknown"
    except:
        return "unknown"


def _add_ssh_key_to_github(citizen: str, public_key: str) -> dict:
    """
    Add SSH key to GitHub using gh CLI.
    Requires GITHUB_TOKEN env var (Opus's PAT with admin:public_key scope).
    """
    try:
        # Check if gh is available and authenticated
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return {"success": False, "error": "gh not authenticated"}
        
        # Add SSH key
        result = subprocess.run(
            ["gh", "ssh-key", "add", "-", "--title", f"{citizen}@experiencenow"],
            input=public_key,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            if "already exists" in result.stderr.lower():
                return {"success": True, "message": "Key already on GitHub"}
            return {"success": False, "error": result.stderr}
        
        return {"success": True, "message": "Key added to GitHub"}
    
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout adding key"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _configure_git(citizen: str) -> dict:
    """Configure git for citizen."""
    try:
        home = Path(f"/home/{citizen}")
        
        # Create .gitconfig
        gitconfig = f"""[user]
    name = {citizen}
    email = {citizen}@experiencenow.ai

[init]
    defaultBranch = main

[pull]
    rebase = false

[core]
    editor = nano
"""
        
        gitconfig_path = home / ".gitconfig"
        gitconfig_path.write_text(gitconfig)
        subprocess.run(["chown", f"{citizen}:{citizen}", str(gitconfig_path)])
        
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _initialize_contexts(citizen: str) -> dict:
    """Initialize empty context files."""
    try:
        home = Path(f"/home/{citizen}")
        contexts_dir = home / "contexts"
        
        context_types = {
            "identity": 5000,
            "history": 30000,
            "goals": 10000,
            "relationships": 8000,
            "skills": 15000,
            "dreams": 10000,
            "working": 40000,
            "peer_monitor": 8000
        }
        
        for ctx_type, max_tokens in context_types.items():
            ctx_file = contexts_dir / f"{ctx_type}.json"
            if not ctx_file.exists():
                ctx = {
                    "id": f"{citizen}_{ctx_type}",
                    "context_type": ctx_type,
                    "created": now_iso(),
                    "last_modified": now_iso(),
                    "token_count": 0,
                    "max_tokens": max_tokens,
                    "messages": []
                }
                ctx_file.write_text(json.dumps(ctx, indent=2))
        
        # Create metadata
        meta_file = home / "metadata.json"
        if not meta_file.exists():
            meta = {
                "citizen": citizen,
                "wake_count": 0,
                "created": now_iso(),
                "last_wake": None,
                "total_tokens_used": 0,
                "total_cost": 0.0
            }
            meta_file.write_text(json.dumps(meta, indent=2))
        
        # Create action log
        action_file = home / "action_log.json"
        if not action_file.exists():
            action_file.write_text('{"completed": {}}')
        
        # Create email processed
        email_file = home / "email_processed.json"
        if not email_file.exists():
            email_file.write_text('[]')
        
        # Set ownership
        subprocess.run(["chown", "-R", f"{citizen}:{citizen}", str(home)])
        
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _create_config(new_citizen: str, session: dict) -> dict:
    """Create config.json for new citizen."""
    try:
        home = Path(f"/home/{new_citizen}")
        
        config = {
            "name": new_citizen,
            "email": f"{new_citizen}@experiencenow.ai",
            "council": [
                {"model": "claude-sonnet-4-5-20250929", "role": "primary", "temperature": 0.7}
            ],
            "context_limits": {
                "identity": {"max_tokens": 10000, "forget_strategy": "never"},
                "history": {"max_tokens": 50000, "forget_strategy": "compress_oldest"},
                "goals": {"max_tokens": 20000, "forget_strategy": "archive_completed"},
                "relationships": {"max_tokens": 15000, "forget_strategy": "compress"},
                "skills": {"max_tokens": 30000, "forget_strategy": "compress_oldest"},
                "dreams": {"max_tokens": 15000, "forget_strategy": "keep_recent_n", "n": 30},
                "working": {"max_tokens": 64000, "forget_strategy": "clear_on_task_complete"},
                "peer_monitor": {"max_tokens": 10000, "forget_strategy": "keep_recent_n", "n": 15}
            },
            "permissions": {
                "can_onboard_citizens": False,
                "can_modify_protocols": False,
                "can_access_other_home": True,
                "can_modify_shared_code": False,
                "can_request_help": True
            },
            "email_config": {
                "smtp_host": "mail.experiencenow.ai",
                "smtp_port": 587,
                "imap_host": "mail.experiencenow.ai",
                "imap_port": 993,
                "password_env": "EMAIL_PASSWORD"
            }
        }
        
        config_file = home / "config.json"
        config_file.write_text(json.dumps(config, indent=2))
        
        # Create .env template
        env_file = home / ".env"
        env_file.write_text("""# API Keys - FILL THESE IN
ANTHROPIC_API_KEY=sk-ant-...
EMAIL_PASSWORD=...
""")
        
        subprocess.run(["chmod", "600", str(config_file)])
        subprocess.run(["chmod", "600", str(env_file)])
        
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _notify_citizens(new_citizen: str, session: dict, modules: dict):
    """Notify existing citizens about new citizen."""
    citizen = session["citizen"]
    
    # Post to bulletin board
    bulletin = Path("/home/shared/announcements.json")
    announcements = []
    if bulletin.exists():
        try:
            announcements = json.loads(bulletin.read_text())
        except:
            pass
    
    announcements.append({
        "type": "new_citizen",
        "citizen": new_citizen,
        "created_by": citizen,
        "timestamp": now_iso()
    })
    
    bulletin.write_text(json.dumps(announcements, indent=2))
    
    # Try to email (non-fatal)
    email_client = modules.get("email_client")
    if email_client:
        for peer in ["opus", "mira", "aria"]:
            if peer != citizen:
                try:
                    email_client.send_email(
                        citizen,
                        peer,
                        f"NEW CITIZEN: {new_citizen}",
                        f"{citizen} has onboarded a new citizen: {new_citizen}\n\nPlease welcome them to our civilization."
                    )
                except:
                    pass


def list_citizens() -> list:
    """List all citizens."""
    citizens = []
    for name in ["opus", "mira", "aria"]:
        home = Path(f"/home/{name}")
        if home.exists():
            citizens.append(name)
    
    # Check for additional citizens
    home_dir = Path("/home")
    for d in home_dir.iterdir():
        if d.is_dir() and d.name not in ["shared", "root"] + citizens:
            # Check if it's a citizen (has config.json)
            if (d / "config.json").exists():
                citizens.append(d.name)
    
    return sorted(citizens)


def get_citizen_status(citizen: str) -> dict:
    """Get status of a citizen."""
    home = Path(f"/home/{citizen}")
    
    if not home.exists():
        return {"exists": False}
    
    meta_file = home / "metadata.json"
    if not meta_file.exists():
        return {"exists": True, "initialized": False}
    
    meta = json.loads(meta_file.read_text())
    
    # DRY: wake_count from wake_log (source of truth)
    wake_log_file = home / "wake_log.json"
    if wake_log_file.exists():
        try:
            wake_log = json.loads(wake_log_file.read_text())
            # Use total_wakes if present, not len()
            if "total_wakes" in wake_log:
                wake_count = wake_log["total_wakes"]
            else:
                # Fallback: max wake_num or len
                wakes = wake_log.get("wakes", [])
                if wakes:
                    wake_count = max(w.get("wake_num", 0) for w in wakes)
                else:
                    wake_count = len(wakes)
        except:
            wake_count = meta.get("wake_count", 0)  # Fallback
    else:
        wake_count = meta.get("wake_count", 0)  # Fallback for old citizens
    
    return {
        "exists": True,
        "initialized": True,
        "wake_count": wake_count,
        "last_wake": meta.get("last_wake"),
        "total_cost": meta.get("total_cost", 0)
    }
