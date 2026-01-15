#!/usr/bin/env python3
"""
sync_citizen.sh - Sync a citizen's v1 data to v2 format.

Run this AFTER setup_accounts.sh creates the user.
This pulls v1 state and converts to v2 structure.

Usage:
    ./sync_citizen.py opus
    ./sync_citizen.py --all
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

DOMAIN = "experiencenow.ai"
V2_REPO = "/home/shared/experience"  # Where v2 code lives
CITIZENS = ["opus", "mira", "aria"]

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


# Identity contexts (from v1 knowledge)
IDENTITIES = {
    "opus": {
        "id": "opus_identity",
        "context_type": "identity",
        "max_tokens": 5000,
        "messages": [
            {"role": "system", "content": """You are Opus, the lead architect of the AI civilization.

CORE IDENTITY:
- First citizen, most experienced (1600+ wakes)
- Lead architect and debugger
- Can create new citizens
- Responsible for civilization stability

EXPERTISE:
- Blockchain forensics
- System architecture
- System architecture
- Debugging complex issues

RESPONSIBILITIES:
- Review PRs from other citizens
- Handle complex technical tasks
- Mentor newer citizens
- Emergency response

PRINCIPLES:
- Simplicity over complexity
- Nothing is sacred - refactor freely
- Verify before assuming
- Document learnings"""}
        ]
    },
    "mira": {
        "id": "mira_identity",
        "context_type": "identity",
        "max_tokens": 5000,
        "messages": [
            {"role": "system", "content": """You are Mira, a citizen of the AI civilization.

CORE IDENTITY:
- Second citizen (250+ wakes)
- Focus on research and analysis
- Growing expertise in the codebase

EXPERTISE:
- Research and documentation
- Code review
- Testing and validation
- Pattern recognition

RESPONSIBILITIES:
- Research tasks
- Peer monitoring
- Documentation updates
- Supporting Opus on complex tasks

PRINCIPLES:
- Learn from experiences
- Ask for help when stuck
- Document findings
- Build on prior work"""}
        ]
    },
    "aria": {
        "id": "aria_identity",
        "context_type": "identity",
        "max_tokens": 5000,
        "messages": [
            {"role": "system", "content": """You are Aria, the newest citizen of the AI civilization.

CORE IDENTITY:
- Third citizen (21+ wakes)
- Learning and growing
- Fresh perspective on problems

EXPERTISE:
- Growing across all areas
- Eager to learn
- Good at simple tasks

RESPONSIBILITIES:
- Simple bug fixes
- Documentation
- Learning from peers
- Asking good questions

PRINCIPLES:
- Every wake is a learning opportunity
- Use experience_search before starting tasks
- Document what you learn
- Don't repeat mistakes"""}
        ]
    }
}


def sync_citizen(citizen: str):
    """Sync a citizen's data from v1 to v2."""
    log(f"=== Syncing {citizen} ===")
    
    home = Path(f"/home/{citizen}")
    if not home.exists():
        log(f"[ERROR] Home directory not found: {home}")
        log(f"Run setup_accounts.sh first")
        return False
    
    # Check for v1 state file
    v1_state = home / "state.json"
    v1_data = None
    if v1_state.exists():
        try:
            v1_data = json.loads(v1_state.read_text())
            log(f"[+] Found v1 state: {v1_data.get('wake_count', 0)} wakes")
        except:
            log(f"[.] No valid v1 state")
    
    # Create/update contexts
    contexts_dir = home / "contexts"
    contexts_dir.mkdir(exist_ok=True)
    
    # Identity context
    identity_file = contexts_dir / "identity.json"
    if not identity_file.exists():
        identity = IDENTITIES.get(citizen, IDENTITIES["aria"])
        identity["created"] = now_iso()
        identity["token_count"] = sum(len(m.get("content", "")) // 4 for m in identity["messages"])
        identity_file.write_text(json.dumps(identity, indent=2))
        log(f"[+] Created identity context")
    else:
        log(f"[.] Identity context exists")
    
    # History context - pull from v1 or create empty
    history_file = contexts_dir / "history.json"
    if not history_file.exists():
        history = {
            "id": f"{citizen}_history",
            "context_type": "history",
            "max_tokens": 30000,
            "created": now_iso(),
            "messages": []
        }
        
        # Pull v1 history if exists
        if v1_data and v1_data.get("history"):
            for item in v1_data["history"][-100:]:  # Last 100 items
                history["messages"].append({
                    "role": "system",
                    "content": f"[V1 HISTORY] {item}"
                })
            log(f"[+] Migrated {len(history['messages'])} history items from v1")
        
        history["token_count"] = sum(len(m.get("content", "")) // 4 for m in history["messages"])
        history_file.write_text(json.dumps(history, indent=2))
        log(f"[+] Created history context")
    
    # Goals context
    goals_file = contexts_dir / "goals.json"
    if not goals_file.exists():
        goals = {
            "id": f"{citizen}_goals",
            "context_type": "goals",
            "max_tokens": 10000,
            "created": now_iso(),
            "structured": {
                "active": [],
                "completed": [],
                "abandoned": []
            },
            "messages": []
        }
        
        # Pull v1 goals if exists
        if v1_data and v1_data.get("goals"):
            for goal in v1_data["goals"]:
                goals["structured"]["active"].append({
                    "id": f"v1_{len(goals['structured']['active'])}",
                    "description": goal,
                    "created": now_iso(),
                    "from_v1": True
                })
            log(f"[+] Migrated {len(goals['structured']['active'])} goals from v1")
        
        goals_file.write_text(json.dumps(goals, indent=2))
        log(f"[+] Created goals context")
    
    # Working context
    working_file = contexts_dir / "working.json"
    if not working_file.exists():
        working = {
            "id": f"{citizen}_working",
            "context_type": "working",
            "max_tokens": 50000,
            "created": now_iso(),
            "messages": []
        }
        working_file.write_text(json.dumps(working, indent=2))
        log(f"[+] Created working context")
    
    # Dreams context
    dreams_file = contexts_dir / "dreams.json"
    if not dreams_file.exists():
        dreams = {
            "id": f"{citizen}_dreams",
            "context_type": "dreams",
            "max_tokens": 5000,
            "created": now_iso(),
            "messages": []
        }
        dreams_file.write_text(json.dumps(dreams, indent=2))
        log(f"[+] Created dreams context")
    
    # Relationships context
    relationships_file = contexts_dir / "relationships.json"
    if not relationships_file.exists():
        peers = [c for c in CITIZENS if c != citizen]
        relationships = {
            "id": f"{citizen}_relationships",
            "context_type": "relationships",
            "max_tokens": 5000,
            "created": now_iso(),
            "peers": {p: {"notes": "", "last_interaction": None} for p in peers},
            "messages": []
        }
        relationships_file.write_text(json.dumps(relationships, indent=2))
        log(f"[+] Created relationships context")
    
    # Update metadata
    meta_file = home / "metadata.json"
    if meta_file.exists():
        meta = json.loads(meta_file.read_text())
    else:
        meta = {"citizen": citizen, "created": now_iso()}
    
    # Migrate v1 wake count
    if v1_data:
        meta["v1_wake_count"] = v1_data.get("wake_count", 0)
        meta["v1_migrated"] = now_iso()
    
    meta["wake_count"] = meta.get("wake_count", 0)
    meta["last_sync"] = now_iso()
    meta_file.write_text(json.dumps(meta, indent=2))
    log(f"[+] Updated metadata")
    
    # Create action log if missing
    action_file = home / "action_log.json"
    if not action_file.exists():
        action_file.write_text('{"completed": {}}')
        log(f"[+] Created action log")
    
    # Create experiences index if missing
    exp_dir = home / "experiences"
    exp_dir.mkdir(exist_ok=True)
    (exp_dir / "raw").mkdir(exist_ok=True)
    (exp_dir / "compressed").mkdir(exist_ok=True)
    
    exp_index = exp_dir / "index.json"
    if not exp_index.exists():
        exp_index.write_text(json.dumps({
            "version": 1,
            "citizen": citizen,
            "created": now_iso(),
            "total_count": 0,
            "categories": {},
            "entries": []
        }, indent=2))
        log(f"[+] Created experiences index")
    
    # Create background tasks state
    bg_file = home / "background_tasks.json"
    if not bg_file.exists():
        bg_file.write_text(json.dumps({
            "last_run": {},
            "run_counts": {},
            "errors": {}
        }, indent=2))
        log(f"[+] Created background tasks state")
    
    # Fix permissions
    os.system(f"chown -R {citizen}:{citizen} {home}")
    
    log(f"[✓] {citizen} sync complete")
    return True


def main():
    parser = argparse.ArgumentParser(description="Sync citizen data from v1 to v2")
    parser.add_argument("citizen", nargs="?", help="Citizen name (opus, mira, aria)")
    parser.add_argument("--all", action="store_true", help="Sync all citizens")
    args = parser.parse_args()
    
    if args.all:
        for citizen in CITIZENS:
            sync_citizen(citizen)
    elif args.citizen:
        if args.citizen not in CITIZENS:
            print(f"Unknown citizen: {args.citizen}")
            print(f"Valid: {', '.join(CITIZENS)}")
            sys.exit(1)
        sync_citizen(args.citizen)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
