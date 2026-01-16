#!/usr/bin/env python3
"""
Experience v2 - Core Loop

The stable main loop that maintains session state and hot-reloads modules.
This file should rarely change.

Usage:
    ./core.py --citizen opus
    ./core.py --citizen mira --wake  # Single wake then exit
"""

import argparse
import importlib
import json
import os
import re
import shutil
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

# Add modules to path
SCRIPT_DIR = Path(__file__).parent
MODULES_DIR = SCRIPT_DIR / "modules"
sys.path.insert(0, str(MODULES_DIR))

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def load_json(path):
    with open(path) as f:
        return json.load(f)

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def get_wake_count(citizen_home: Path) -> int:
    """
    Get wake count from wake_log.json (source of truth).
    
    DRY: Count is derived from log, not stored separately.
    This prevents drift where stored count != actual wakes.
    """
    wake_log_file = citizen_home / "wake_log.json"
    if wake_log_file.exists():
        try:
            wake_log = load_json(wake_log_file)
            return len(wake_log.get("wakes", []))
        except:
            pass
    return 0

def load_env(citizen_home: Path):
    """Load environment variables from .env file."""
    env_file = citizen_home / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip().strip('"\'')

def reload_modules() -> dict:
    """Reload all modules to pick up code changes."""
    module_names = [
        "context_mgr",
        "forgetter",
        "memory",
        "executor",
        "intake",
        "tools",
        "email_client",
        "action_log",
        "council",
        "reporter"
    ]
    modules = {}
    for name in module_names:
        try:
            if name in sys.modules:
                modules[name] = importlib.reload(sys.modules[name])
            else:
                modules[name] = importlib.import_module(name)
        except Exception as e:
            print(f"[ERROR] Failed to load module {name}: {e}")
            raise
    return modules

def load_wake_allocation(citizen: str) -> dict:
    """Load wake allocation config for citizen with validation."""
    alloc_file = SCRIPT_DIR / "templates" / "wake_allocations.json"
    if not alloc_file.exists():
        return None
    try:
        alloc = load_json(alloc_file)
    except Exception as e:
        print(f"[ERROR] Corrupt wake_allocations.json: {e}")
        return None
    citizen_alloc = alloc.get("citizen_allocations", {}).get(citizen)
    if not citizen_alloc:
        return None
    # Validate structure
    schedule = citizen_alloc.get("wake_schedule")
    if not isinstance(schedule, list):
        print(f"[ERROR] wake_schedule for {citizen} is not a list")
        return None
    if not schedule:
        print(f"[WARN] Empty wake_schedule for {citizen}, using legacy")
        return None
    return citizen_alloc

def load_wake_prompt(wake_type: str, context: dict) -> str:
    """Load and format wake prompt template."""
    prompts_file = SCRIPT_DIR / "templates" / "wake_prompts.json"
    if not prompts_file.exists():
        return ""
    try:
        prompts = load_json(prompts_file)
    except Exception as e:
        print(f"[WARN] Corrupt wake_prompts.json: {e}")
        return ""
    template = prompts.get("templates", {}).get(wake_type.lower(), {}).get("prompt", "")
    if not template:
        return ""
    # Substitute variables
    if "{domains}" in template:
        domains = context.get("domains", [])
        template = template.replace("{domains}", ", ".join(domains) if domains else "all")
    if "{focus}" in template:
        template = template.replace("{focus}", context.get("focus", "general"))
    return template

def sanitize_task_id(task_id: str) -> str:
    """Remove path separators and dangerous characters from task ID."""
    import re
    if not task_id:
        return "unknown"
    # Remove path separators, dots, and other dangerous chars
    sanitized = re.sub(r'[/\\\.]+', '_', str(task_id))
    # Limit length
    return sanitized[:64]

def safe_load_json(path: Path) -> tuple[dict, str]:
    """Load JSON with error handling. Returns (data, error_msg)."""
    try:
        return (load_json(path), "")
    except json.JSONDecodeError as e:
        return (None, f"JSON decode error: {e}")
    except Exception as e:
        return (None, f"Load error: {e}")

def safe_move_task(src: Path, dst: Path) -> bool:
    """Atomically move task file, handling races."""
    if dst.exists():
        print(f"[WARN] Destination already exists: {dst.name}")
        return False
    try:
        shutil.move(src, dst)
        return True
    except FileNotFoundError:
        print(f"[WARN] Task claimed by another wake: {src.name}")
        return False
    except Exception as e:
        print(f"[ERROR] Failed to move task: {e}")
        return False

def get_wake_action(citizen: str, wake_num: int, m: dict) -> tuple[str, dict]:
    """
    Determine what to do on wake using allocation schedule.
    Returns: (action_type, context)
    
    Priority:
    1. Resume active task (always - task continuity is paramount)
    2. High priority pending tasks override scheduled wake
    3. Scheduled wake type from allocation (wake_num % 10)
    4. Fallback to legacy behavior if no allocation
    5. Normal priority pending tasks
    6. Peer help / email / reflection
    """
    citizen_home = Path(f"/home/{citizen}")
    # 1. Check for active task - SIMPLE FILE CHECK (always first)
    active_dir = citizen_home / "tasks" / "active"
    active_dir.mkdir(parents=True, exist_ok=True)
    active_files = sorted(active_dir.glob("*.json"), key=lambda f: f.stat().st_mtime)
    active_files = [f for f in active_files if not f.name.endswith("_progress.json")]
    if active_files:
        task, err = safe_load_json(active_files[0])
        if err:
            print(f"[WARN] Corrupt active task {active_files[0].name}: {err}")
            quarantine = active_dir / "quarantine"
            quarantine.mkdir(exist_ok=True)
            shutil.move(active_files[0], quarantine / active_files[0].name)
        elif task:
            task_id = sanitize_task_id(task.get("id", "unknown"))
            progress_file = active_files[0].with_name(f"{task_id}_progress.json")
            progress = None
            if progress_file.exists():
                progress, _ = safe_load_json(progress_file)
            return ("resume_task", {"task": task, "progress": progress})
    # 2. Load all queued tasks ONCE (cache for efficiency)
    queue_dir = citizen_home / "tasks" / "queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    queued_tasks = []  # List of (file_path, task_dict)
    for f in sorted(queue_dir.glob("*.json"), key=lambda x: x.stat().st_mtime):
        task, err = safe_load_json(f)
        if err:
            print(f"[WARN] Corrupt queued task {f.name}: {err}")
            quarantine = queue_dir / "quarantine"
            quarantine.mkdir(exist_ok=True)
            shutil.move(f, quarantine / f.name)
            continue
        if task:
            queued_tasks.append((f, task))
    # 3. Check for high priority tasks (override scheduled wake)
    high_priority = [(f, t) for f, t in queued_tasks if t.get("priority") == "high"]
    if high_priority:
        task_file, task = high_priority[0]
        task_id = sanitize_task_id(task.get("id", "unknown"))
        active_file = active_dir / f"{task_id}.json"
        if safe_move_task(task_file, active_file):
            return ("start_task", {"task": task})
        # If move failed (race), remove from our list and continue
        queued_tasks = [(f, t) for f, t in queued_tasks if f != task_file]
    # 4. Use wake allocation schedule
    allocation = load_wake_allocation(citizen)
    if allocation:
        slot = wake_num % 10
        schedule = allocation.get("wake_schedule", [])
        # Find the slot entry (O(n) but n=10, acceptable)
        slot_entry = None
        for entry in schedule:
            if entry.get("slot") == slot:
                slot_entry = entry
                break
        if slot_entry:
            wake_type = slot_entry.get("type", "REFLECT").lower()
            prompt = load_wake_prompt(wake_type, slot_entry)
            context = {
                "wake_type": wake_type,
                "domains": slot_entry.get("domains", []),
                "focus": slot_entry.get("focus", "general"),
                "note": slot_entry.get("note", ""),
                "prompt": prompt if prompt else None
            }
            # Map wake type to action
            action_map = {
                "reflect": "reflection",
                "peer_monitor": "peer_monitor",
                "library": "library",
                "dry_audit": "dry_audit",  # MANDATORY: Hunt DRY violations
                "audit": "audit",
                "debug": "debug",
                "code": "code",
                "design": "design",
                "research": "research",
                "self_improve": "self_improve"
            }
            action = action_map.get(wake_type)
            if not action:
                print(f"[WARN] Unknown wake type '{wake_type}', using reflection")
                action = "reflection"
            return (action, context)
    # 5. Fallback: Legacy scheduled wakes (if no allocation config)
    if wake_num % 10 == 7:
        return ("peer_monitor", {})
    if wake_num % 10 == 3:
        ctx = {"mode": "self_improve"}
        pr_file = Path("/home/shared/pr_tracker.json")
        if pr_file.exists():
            prs, _ = safe_load_json(pr_file)
            if prs:
                for pr_num, pr in prs.items():
                    if pr.get("merged"):
                        continue
                    if pr.get("author") != citizen and citizen not in pr.get("reviews", {}):
                        ctx.setdefault("pending_review", []).append(pr_num)
                    if citizen not in pr.get("applied_by", []):
                        my_review = pr.get("reviews", {}).get(citizen, {})
                        if my_review.get("decision") == "approve":
                            ctx.setdefault("pending_apply", []).append(pr_num)
        return ("self_improve", ctx)
    if wake_num % 10 == 1:
        return ("library", {"mode": "library"})
    # 6. Check for pending tasks (normal priority) - use cached list
    normal_priority = [(f, t) for f, t in queued_tasks if t.get("priority") != "high"]
    if normal_priority:
        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        normal_priority.sort(key=lambda x: priority_order.get(x[1].get("priority", "medium"), 1))
        task_file, task = normal_priority[0]
        task_id = sanitize_task_id(task.get("id", "unknown"))
        active_file = active_dir / f"{task_id}.json"
        if safe_move_task(task_file, active_file):
            return ("start_task", {"task": task})
    # 7. Check for peer help requests
    help_file = Path("/home/shared/help_wanted.json")
    if help_file.exists():
        requests, _ = safe_load_json(help_file)
        if requests:
            for req in requests:
                if req.get("from") != citizen and not req.get("claimed"):
                    return ("help_peer", {"request": req})
    # 8. Check email
    try:
        emails = m["email_client"].check_email(citizen)
        important = [e for e in emails if "HELP" in e.get("subject", "").upper()]
        if important:
            return ("process_email", {"emails": important})
    except Exception as e:
        print(f"[WARN] Email check failed: {e}")
    # 9. Default to reflection
    return ("reflection", {})

def main():
    parser = argparse.ArgumentParser(description="Experience v2")
    parser.add_argument("--citizen", required=True, help="Citizen name (opus, mira, aria)")
    parser.add_argument("--wake", action="store_true", help="Single wake then exit")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode (human input)")
    parser.add_argument("--loop", action="store_true", help="Loop mode: run wakes continuously")
    parser.add_argument("--interval", type=int, default=600, help="Seconds between wakes in loop mode (default: 600)")
    parser.add_argument("--no-background", action="store_true", help="Skip background tasks")
    parser.add_argument("--background-only", action="store_true", help="Run only background tasks, no wake")
    parser.add_argument("--status", action="store_true", help="Show status and exit")
    parser.add_argument("--message", "-m", type=str, help="Send a message/prompt to citizen")
    args = parser.parse_args()
    
    citizen = args.citizen
    citizen_home = Path(f"/home/{citizen}")
    
    if not citizen_home.exists():
        print(f"[ERROR] Citizen home not found: {citizen_home}")
        print("Run setup_server.sh first")
        sys.exit(1)
    
    # Load environment
    load_env(citizen_home)
    
    # Load config
    config_file = citizen_home / "config.json"
    if not config_file.exists():
        print(f"[ERROR] Config not found: {config_file}")
        sys.exit(1)
    config = load_json(config_file)
    
    # Status mode - show status and exit
    if args.status:
        show_status(citizen, citizen_home)
        sys.exit(0)
    
    # Loop mode or single run
    if args.loop:
        run_loop(citizen, citizen_home, config, args)
    else:
        run_single_wake(citizen, citizen_home, config, args)


def run_background_tasks(citizen: str, max_tasks: int = 3) -> list:
    """Run due background tasks. Returns list of (task_name, result)."""
    try:
        # Import here to allow hot-reload
        sys.path.insert(0, str(SCRIPT_DIR / "modules"))
        from background import get_scheduler
        scheduler = get_scheduler(citizen)
        return scheduler.run_due_tasks(max_tasks=max_tasks)
    except Exception as e:
        print(f"[WARN] Background task error: {e}")
        return []


def show_status(citizen: str, citizen_home: Path):
    """Show citizen status."""
    print("=" * 65)
    print(f"  {citizen.upper()} - STATUS")
    print("=" * 65)
    
    # DRY: Wake count from wake_log (source of truth)
    wake_count = get_wake_count(citizen_home)
    print(f"\n[METADATA]")
    print(f"  Wake count: {wake_count}")
    
    # Other metadata
    metadata_file = citizen_home / "metadata.json"
    if metadata_file.exists():
        meta = load_json(metadata_file)
        print(f"  Total cost: ${meta.get('total_cost', 0):.4f}")
        print(f"  Last wake: {meta.get('last_wake', 'never')}")
    # Background tasks
    try:
        sys.path.insert(0, str(SCRIPT_DIR / "modules"))
        from background import get_scheduler
        scheduler = get_scheduler(citizen)
        print(f"\n{scheduler.get_status()}")
    except Exception as e:
        print(f"\n[BACKGROUND] Error loading: {e}")
    # Queued tasks
    queue_dir = citizen_home / "tasks" / "queue"
    if queue_dir.exists():
        queued = list(queue_dir.glob("*.json"))
        print(f"\n[TASKS]")
        print(f"  Queued: {len(queued)}")
    # Active tasks
    active_dir = citizen_home / "tasks" / "active"
    if active_dir.exists():
        active = list(active_dir.glob("*.json"))
        if active:
            print(f"  Active: {len(active)}")
            for f in active[:3]:
                try:
                    t = load_json(f)
                    print(f"    - {t.get('description', f.name)[:50]}")
                except:
                    pass


def run_loop(citizen: str, citizen_home: Path, config: dict, args):
    """Run wakes in a loop with background tasks."""
    print("=" * 65)
    print(f"  {citizen.upper()} - LOOP MODE")
    print(f"  Interval: {args.interval}s | Ctrl+C to stop")
    print(f"  Email from ct@ triggers immediate wake")
    print("=" * 65)
    wake_count = 0
    
    # Import email check function
    try:
        sys.path.insert(0, str(SCRIPT_DIR / "modules"))
        from background import check_urgent_email
        has_email_check = True
    except:
        has_email_check = False
    
    try:
        while True:
            wake_count += 1
            print(f"\n{'='*65}")
            print(f"  Loop iteration #{wake_count}")
            print(f"{'='*65}")
            # Run background tasks first
            if not args.no_background:
                results = run_background_tasks(citizen)
                if results:
                    print(f"[BACKGROUND] Ran {len(results)} tasks")
                    # Check if any background task returned URGENT
                    for task_name, result in results:
                        if result.get("output", "").startswith("URGENT:"):
                            print(f"[URGENT] {result['output']}")
            # Run wake (unless background-only)
            if not args.background_only:
                run_single_wake(citizen, citizen_home, config, args)
            # Sleep until next iteration, checking for urgent email
            print(f"\n[LOOP] Sleeping {args.interval}s (checking email every 30s)...")
            import time
            check_interval = 30  # Check email every 30 seconds
            elapsed = 0
            while elapsed < args.interval:
                sleep_time = min(check_interval, args.interval - elapsed)
                time.sleep(sleep_time)
                elapsed += sleep_time
                # Check for urgent email from ct@
                if has_email_check and elapsed < args.interval:
                    if check_urgent_email(citizen):
                        print(f"\n[URGENT] Email from ct@ detected! Waking immediately...")
                        break
    except KeyboardInterrupt:
        print(f"\n[LOOP] Stopped after {wake_count} iterations")


def run_single_wake(citizen: str, citizen_home: Path, config: dict, args):
    """Run a single wake cycle."""
    # Run background tasks first (unless disabled)
    if not args.no_background and not hasattr(args, '_bg_done'):
        results = run_background_tasks(citizen)
        if results:
            print(f"[BACKGROUND] Ran {len(results)} tasks")
        args._bg_done = True  # Don't run again in loop mode
    
    # DRY: Wake count derived from wake_log, not stored separately
    # Add 1 because current wake will be logged at end
    wake_num = get_wake_count(citizen_home) + 1
    
    # Update metadata (still keep last_wake for quick access)
    metadata_file = citizen_home / "metadata.json"
    metadata = load_json(metadata_file)
    metadata["last_wake"] = now_iso()
    # NOTE: wake_count in metadata kept for backward compat but is NOT authoritative
    # Source of truth is wake_log.json (written in finally block)
    metadata["wake_count"] = wake_num  # Sync for readers that haven't updated
    save_json(metadata_file, metadata)
    
    print("=" * 65)
    print(f"  {citizen.upper()} - Wake #{wake_num}")
    print(f"  {now_iso()}")
    print("=" * 65)
    
    # Initialize session state
    session = {
        "citizen": citizen,
        "citizen_home": citizen_home,
        "config": config,
        "wake_num": wake_num,
        "contexts": {},
        "messages": [],
        "tokens_used": 0,
        "cost": 0.0,
        "actions": []
    }
    
    # Track whether modules loaded successfully
    m = None
    
    try:
        # Load modules (hot-reload)
        m = reload_modules()
        
        # CHECK FOR BOOTSTRAP: First wake should document capabilities
        bootstrap_task = None
        try:
            from modules.bootstrap import check_bootstrap_needed, get_bootstrap_task, mark_bootstrap_complete
            if check_bootstrap_needed():
                bootstrap_task = get_bootstrap_task()
                if bootstrap_task:
                    print(f"\n[BOOTSTRAP] Documenting capability: {bootstrap_task['area']}")
        except Exception as e:
            print(f"[BOOTSTRAP] Check failed: {e}")
        
        if args.message:
            # User sent a direct message/prompt - HIGHEST PRIORITY
            action = "prompt"
            context = {"message": args.message, "wake_type": "prompt"}
            print(f"[WAKE ACTION] prompt from ct")
        elif bootstrap_task:
            # Override normal wake - do bootstrap instead
            action = "bootstrap"
            context = bootstrap_task
            print(f"[WAKE ACTION] {action} - {context['area']}")
        else:
            # Determine normal wake action
            action, context = get_wake_action(citizen, wake_num, m)
            print(f"\n[WAKE ACTION] {action}")
        
        if args.interactive:
            # Interactive mode - human drives
            interactive_loop(session, m, config, initial_message=args.message)
        else:
            # Autonomous mode
            # Show structured prompt status
            if context.get("prompt"):
                print(f"[PROMPT] Using pre-structured {context.get('wake_type', action)} template")
            elif context.get("wake_type"):
                print(f"[PROMPT] No template for {context.get('wake_type')}, using fallback")
            
            if action == "bootstrap":
                # Document a capability area
                m["executor"].bootstrap_wake(session, context, m)
            elif action == "resume_task":
                task_desc = context.get('task', {}).get('description', '')[:50]
                task_id = context.get('task', {}).get('id', 'unknown')
                print(f"[RESUMING] {task_id}: {task_desc}")
                m["executor"].resume_task(session, context["task"], context["progress"], m)
            elif action == "start_task":
                task = context["task"]
                print(f"[STARTING] {task.get('id', 'unknown')}: {task.get('description', '')[:50]}")
                m["executor"].start_task(session, task, m)
            elif action == "peer_monitor":
                print("[PEER MONITORING] Checking on a peer...")
                m["executor"].peer_monitor_wake(session, m)
            elif action == "self_improve":
                print("[SELF-IMPROVEMENT] Review improvements, propose ideas")
                m["executor"].self_improve_wake(session, context, m)
            elif action == "library":
                domains = context.get("domains", [])
                print(f"[LIBRARY] Curate domains: {', '.join(domains) if domains else 'all'}")
                m["executor"].library_wake(session, context, m)
            elif action == "dry_audit":
                print("[DRY_AUDIT] Hunting duplication and complexity")
                m["executor"].dry_audit_wake(session, context, m)
            elif action == "audit":
                focus = context.get("focus", "general")
                print(f"[AUDIT] Verification pass - focus: {focus}")
                m["executor"].structured_wake(session, context, m)
            elif action == "debug":
                focus = context.get("focus", "general")
                print(f"[DEBUG] Investigation mode - focus: {focus}")
                m["executor"].structured_wake(session, context, m)
            elif action == "code":
                focus = context.get("focus", "general")
                print(f"[CODE] Implementation mode - focus: {focus}")
                m["executor"].structured_wake(session, context, m)
            elif action == "design":
                focus = context.get("focus", "general")
                print(f"[DESIGN] Architecture mode - focus: {focus}")
                m["executor"].structured_wake(session, context, m)
            elif action == "research":
                focus = context.get("focus", "general")
                print(f"[RESEARCH] Investigation mode - focus: {focus}")
                m["executor"].structured_wake(session, context, m)
            elif action == "help_peer":
                req = context.get("request", {})
                print(f"[HELPING] {req.get('from', '?')}: {req.get('description', '')[:50]}")
                m["executor"].help_peer(session, req, m)
            elif action == "process_email":
                print(f"[EMAIL] Processing {len(context.get('emails', []))} messages")
                m["executor"].process_emails(session, context.get("emails", []), m)
            elif action == "reflection":
                print("[REFLECTION] No tasks - scanning peer goals")
                m["executor"].reflection_wake(session, m)
            elif action == "prompt":
                msg = context.get("message", "")
                print(f"[PROMPT] {msg[:80]}...")
                m["executor"].prompt_wake(session, msg, m)
            else:
                print(f"[WARN] Unknown action: {action}, falling back to reflection")
                m["executor"].reflection_wake(session, m)
            
            # Run forgetter on all contexts (compress working memory)
            for ctx_name, ctx in session["contexts"].items():
                m["forgetter"].maybe_forget(ctx, config, session)
            
            # Save all contexts
            m["context_mgr"].save_all(session)
            
            # Record wake to hierarchical memory (permanent storage)
            if "memory" in m:
                m["memory"].record_event(citizen, {
                    "timestamp": now_iso(),
                    "type": "wake_complete",
                    "details": {
                        "wake_num": wake_num,
                        "action": action,
                        "tokens_used": session.get("tokens_used", 0),
                        "cost": session.get("cost", 0),
                        "actions_count": len(session.get("actions", []))
                    }
                })
        
        # Update metadata with session stats
        metadata["total_tokens_used"] = metadata.get("total_tokens_used", 0) + session["tokens_used"]
        metadata["total_cost"] = metadata.get("total_cost", 0) + session["cost"]
        save_json(metadata_file, metadata)
        
        if not args.wake:
            print(f"\n[COMPLETE] Wake #{wake_num} | {session['tokens_used']:,} tokens | ${session['cost']:.4f}")
        
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Saving state...")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        traceback.print_exc()
        # Don't exit yet - let finally run first
        session["_error"] = True
    finally:
        # CRITICAL: Always save contexts - this IS the consciousness
        # A crash should never lose context changes
        if m and "context_mgr" in m:
            try:
                m["context_mgr"].save_all(session)
                print("[CONTEXTS SAVED]")
            except Exception as e:
                print(f"[WARN] Failed to save contexts: {e}")
                # Last resort: dump to emergency file
                try:
                    emergency_file = citizen_home / "contexts" / "_emergency_dump.json"
                    save_json(emergency_file, {
                        "timestamp": now_iso(),
                        "wake_num": wake_num,
                        "contexts": {k: v for k, v in session.get("contexts", {}).items()}
                    })
                    print(f"[EMERGENCY] Dumped to {emergency_file}")
                except:
                    pass
        
        # Record wake to log (source of truth for wake_count)
        _record_wake_to_log(citizen_home, session)
        
        # Exit if there was an error
        if session.get("_error"):
            sys.exit(1)


def _record_wake_to_log(citizen_home: Path, session: dict):
    """
    Record wake to wake_log.json - the source of truth for wake history.
    
    DRY: wake_count is derived from len(wake_log), not stored separately.
    """
    wake_log_file = citizen_home / "wake_log.json"
    
    try:
        if wake_log_file.exists():
            wake_log = load_json(wake_log_file)
        else:
            wake_log = {"wakes": []}
        
        # Add this wake
        wake_log["wakes"].append({
            "timestamp": now_iso(),
            "wake_num": session.get("wake_num", 0),
            "tokens": session.get("tokens_used", 0),
            "cost": session.get("cost", 0),
            "actions": len(session.get("actions", []))
        })
        
        # Keep only last 1000 wakes to prevent unbounded growth
        if len(wake_log["wakes"]) > 1000:
            wake_log["wakes"] = wake_log["wakes"][-1000:]
        
        save_json(wake_log_file, wake_log)
    except Exception as e:
        print(f"[WARN] Failed to record wake: {e}")

def interactive_loop(session: dict, m: dict, config: dict, initial_message: str = None):
    """Interactive mode - human provides input."""
    citizen = session["citizen"]
    
    # Load identity context
    session["contexts"]["identity"] = m["context_mgr"].load_context(
        session["citizen_home"] / "contexts" / "identity.json"
    )
    session["contexts"]["working"] = m["context_mgr"].load_context(
        session["citizen_home"] / "contexts" / "working.json"
    )
    
    print("\n[INTERACTIVE MODE]")
    print("Commands: /file, /opus, /task, /goals, /status, /help, /quit")
    print()
    
    # Process initial message if provided
    if initial_message:
        print(f"[{citizen}]> {initial_message}")
        result = m["council"].process(
            initial_message,
            session,
            config["council"],
            m
        )
        m["reporter"].display(result, session)
        m["context_mgr"].save_all(session)
    
    while True:
        try:
            # Reload modules each iteration (hot-reload)
            m = reload_modules()
            
            user_input = input(f"[{citizen}]> ").strip()
            
            if not user_input:
                continue
            
            # Commands
            if user_input.startswith("/"):
                handle_command(user_input, session, m, config)
                continue
            
            # Regular input - process with council
            result = m["council"].process(
                user_input,
                session,
                config["council"],
                m
            )
            
            # Clear force flags after use
            session.pop("force_complex", None)
            
            # Display result
            m["reporter"].display(result, session)
            
            # Check forgetting
            for ctx_name, ctx in session["contexts"].items():
                m["forgetter"].maybe_forget(ctx, config, session)
            
            # Save contexts
            m["context_mgr"].save_all(session)
            
        except KeyboardInterrupt:
            print("\n[Use /quit to exit]")
        except Exception as e:
            print(f"[ERROR] {e}")
            traceback.print_exc()

def handle_command(cmd: str, session: dict, m: dict, config: dict):
    """Handle slash commands."""
    citizen = session["citizen"]
    citizen_home = session["citizen_home"]
    
    if cmd == "/help":
        print("""
Commands:
  /task <desc>   - Create new task (enters intake)
  /file <path>   - Send file with optional message
  /opus          - Force next prompt to use Opus model
  /goals         - Show active goals
  /tasks         - Show task queue
  /status        - Session status
  /email         - Check email
  /contexts      - List contexts and sizes
  /forget        - Manually trigger forgetting
  /reload        - Force module reload
  /save          - Save session state
  /quit          - Save and exit
""")
    
    elif cmd == "/status":
        print(f"\nCitizen: {citizen}")
        print(f"Wake: #{session['wake_num']}")
        print(f"Tokens: {session['tokens_used']:,}")
        print(f"Cost: ${session['cost']:.4f}")
        print(f"Contexts: {list(session['contexts'].keys())}")
        print(f"Actions: {len(session['actions'])}")
    
    elif cmd == "/goals":
        goals_file = citizen_home / "contexts" / "goals.json"
        if goals_file.exists():
            goals = load_json(goals_file)
            print("\nActive Goals:")
            for g in goals.get("structured", {}).get("active", []):
                print(f"  [{g.get('priority', '?')}] {g['id']}: {g['description'][:50]}")
        else:
            print("\nNo goals context found")
    
    elif cmd == "/tasks":
        print("\nTasks:")
        for status in ["active", "pending"]:
            tasks_dir = citizen_home / "tasks" / status
            tasks = [f for f in tasks_dir.glob("*.json") if not f.name.endswith("_progress.json")]
            if tasks:
                print(f"  {status.upper()}:")
                for f in tasks:
                    t = load_json(f)
                    print(f"    {t['id']}: {t.get('description', '')[:40]}")
    
    elif cmd == "/email":
        try:
            emails = m["email_client"].check_email(citizen)
            print(f"\n{len(emails)} new emails:")
            for e in emails[:5]:
                print(f"  From: {e['from']}")
                print(f"  Subject: {e['subject']}")
                print()
        except Exception as e:
            print(f"[ERROR] {e}")
    
    elif cmd == "/contexts":
        print("\nContexts:")
        for name, ctx in session["contexts"].items():
            pct = (ctx.get("token_count", 0) / ctx.get("max_tokens", 1)) * 100
            print(f"  {name}: {ctx.get('token_count', 0):,} / {ctx.get('max_tokens', 0):,} ({pct:.1f}%)")
    
    elif cmd == "/forget":
        print("\nRunning forgetter on all contexts...")
        for ctx_name, ctx in session["contexts"].items():
            before = ctx.get("token_count", 0)
            m["forgetter"].force_forget(ctx, config, session)
            after = ctx.get("token_count", 0)
            if before != after:
                print(f"  {ctx_name}: {before:,} → {after:,}")
    
    elif cmd == "/reload":
        m = reload_modules()
        print("[Modules reloaded]")
    
    elif cmd == "/opus":
        session["force_complex"] = True
        print("[Next prompt will use Opus]")
    
    elif cmd == "/save":
        m["context_mgr"].save_all(session)
        print("[Session saved]")
    
    elif cmd == "/quit":
        m["context_mgr"].save_all(session)
        print("[Goodbye]")
        sys.exit(0)
    
    elif cmd.startswith("/task "):
        desc = cmd[6:].strip()
        if desc:
            task = m["intake"].create_task(desc, session, m)
            if task:
                print(f"[Created task: {task['id']}]")
        else:
            print("Usage: /task <description>")
    
    elif cmd.startswith("/file "):
        # /file <path> [message] - send file content with optional message
        parts = cmd[6:].strip().split(" ", 1)
        filepath = parts[0]
        message = parts[1] if len(parts) > 1 else "Please review this file:"
        
        try:
            path = Path(filepath).expanduser()
            if not path.exists():
                print(f"[ERROR] File not found: {filepath}")
                return
            
            content = path.read_text()
            filename = path.name
            
            # Build prompt with file content
            file_prompt = f"{message}\n\n--- {filename} ---\n{content}\n--- end {filename} ---"
            
            print(f"[Sending {filename} ({len(content):,} chars)]")
            
            # Process with council
            result = m["council"].process(
                file_prompt,
                session,
                config["council"],
                m
            )
            m["reporter"].display(result, session)
            m["context_mgr"].save_all(session)
            
        except Exception as e:
            print(f"[ERROR] {e}")
    
    else:
        print(f"Unknown command: {cmd}")
        print("Type /help for commands")

def save_session(session: dict, m: dict):
    """Emergency save of session state."""
    if m and "context_mgr" in m:
        try:
            m["context_mgr"].save_all(session)
            print("[Session saved]")
        except:
            pass

if __name__ == "__main__":
    main()
