"""
Reporter - Output formatting and display.

Handles displaying results to the console/log.
"""

import json
from datetime import datetime, timezone

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def display(result: dict, session: dict):
    """Display a result from council processing."""
    
    text = result.get("text", "")
    model = result.get("model", "unknown")
    tokens = result.get("tokens", 0)
    cost = result.get("cost", 0)
    
    print()
    print("-" * 60)
    print(text)
    print("-" * 60)
    print(f"[{model} | {tokens:,} tokens | ${cost:.4f}]")
    print()

def display_task_status(session: dict):
    """Display current task status."""
    citizen_home = session["citizen_home"]
    
    print("\n=== TASK STATUS ===")
    
    for status in ["active", "pending"]:
        status_dir = citizen_home / "tasks" / status
        if not status_dir.exists():
            continue
            
        tasks = [f for f in status_dir.glob("*.json") if not f.name.endswith("_progress.json")]
        
        if tasks:
            print(f"\n{status.upper()}:")
            for f in sorted(tasks):
                task = json.loads(f.read_text())
                desc = task.get("description", task.get("spec", {}).get("goal", "?"))
                print(f"  {task['id']}: {desc[:50]}")

def display_goals(session: dict):
    """Display current goals."""
    citizen_home = session["citizen_home"]
    goals_file = citizen_home / "contexts" / "goals.json"
    
    print("\n=== GOALS ===")
    
    if not goals_file.exists():
        print("  (no goals)")
        return
    
    goals = json.loads(goals_file.read_text())
    active = goals.get("structured", {}).get("active", [])
    
    if not active:
        print("  (no active goals)")
        return
    
    for g in sorted(active, key=lambda x: x.get("priority", 999)):
        # DRY: Compute progress from tasks
        tasks = g.get("tasks", [])
        if tasks:
            done = sum(1 for t in tasks if t.get("status") == "completed")
            pct = int(done / len(tasks) * 100)
        else:
            pct = 0
        print(f"  [{g.get('priority', '?')}] {g['id']}: {g['description'][:50]} ({pct}%)")

def display_contexts(session: dict):
    """Display context usage."""
    print("\n=== CONTEXTS ===")
    
    for name, ctx in session.get("contexts", {}).items():
        tokens = ctx.get("token_count", 0)
        max_tokens = ctx.get("max_tokens", 10000)
        pct = (tokens / max_tokens * 100) if max_tokens > 0 else 0
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"  {name:15} [{bar}] {tokens:>6,} / {max_tokens:,} ({pct:.1f}%)")

def display_session_summary(session: dict):
    """Display end-of-session summary."""
    print("\n" + "=" * 60)
    print("SESSION SUMMARY")
    print("=" * 60)
    print(f"  Citizen: {session['citizen']}")
    print(f"  Wake: #{session.get('wake_num', '?')}")
    print(f"  Tokens: {session.get('tokens_used', 0):,}")
    print(f"  Cost: ${session.get('cost', 0):.4f}")
    print(f"  Actions: {len(session.get('actions', []))}")
    
    # Show any completed tasks
    citizen_home = session["citizen_home"]
    done_dir = citizen_home / "tasks" / "done"
    if done_dir.exists():
        recent = []
        for f in done_dir.glob("*.json"):
            if not f.name.endswith("_progress.json"):
                task = json.loads(f.read_text())
                if "completed_at" in task:
                    recent.append(task)
        
        if recent:
            print("\n  Completed this session:")
            for t in recent[-3:]:
                print(f"    ✓ {t['id']}: {t.get('summary', t.get('description', ''))[:40]}")
    
    print("=" * 60)

def format_error(error: str) -> str:
    """Format an error message."""
    return f"\n[ERROR] {error}\n"

def format_warning(warning: str) -> str:
    """Format a warning message."""
    return f"\n[WARN] {warning}\n"

def format_info(info: str) -> str:
    """Format an info message."""
    return f"\n[INFO] {info}\n"
