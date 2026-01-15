"""
Intake - Task clarification and creation.

Handles the DRY principle: clarify once, execute many.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def get_next_task_id(citizen_home: Path) -> str:
    """Get next available task ID."""
    tasks_base = citizen_home / "tasks"
    existing = set()
    
    for status in ["pending", "active", "done", "failed"]:
        status_dir = tasks_base / status
        if status_dir.exists():
            for f in status_dir.glob("*.json"):
                if not f.name.endswith("_progress.json"):
                    existing.add(f.stem)
    
    # Find next number
    num = 1
    while f"t_{num:03d}" in existing:
        num += 1
    
    return f"t_{num:03d}"

def create_task(description: str, session: dict, modules: dict) -> Optional[dict]:
    """
    Create a new task through clarification loop.
    
    Returns task dict if created, None if cancelled.
    """
    citizen = session["citizen"]
    citizen_home = session["citizen_home"]
    council_config = session["config"]["council"]
    
    print(f"\n[INTAKE] Processing: {description[:60]}...")
    print("-" * 60)
    
    # Check if this is a simple enough task
    if len(description) > 200 or "?" in description:
        # Needs clarification
        return clarify_task(description, session, modules)
    else:
        # Simple task - create directly
        return create_simple_task(description, session)

def clarify_task(description: str, session: dict, modules: dict) -> Optional[dict]:
    """Run clarification loop until task is clearly specified."""
    citizen = session["citizen"]
    citizen_home = session["citizen_home"]
    
    clarifications = []
    
    # Initial prompt
    prompt = f"""You are a task intake system. Your job is to clarify a request until you can write a precise spec.

REQUEST: {description}

Ask clarifying questions ONE AT A TIME. Be specific and brief.
When you have enough info, output a task spec in this EXACT format:

SPEC:
goal: <one line goal>
inputs: <what you need>
success_criteria: <how to know it's done>

Start by asking your first clarifying question, or output SPEC if the request is already clear."""

    messages = [{"role": "user", "content": prompt}]
    
    while True:
        # Get AI response
        response = modules["council"].simple_query(
            messages[-1]["content"] if len(messages) == 1 else f"Previous: {messages[-2].get('content', '')}\nYour response: {messages[-1].get('content', '')}",
            session,
            model="claude-sonnet-4-5-20250929",
            temperature=0.3
        )
        
        print(f"\nINTAKE: {response}\n")
        
        # Check if we have a spec
        if "SPEC:" in response or "goal:" in response.lower()[:50]:
            spec = parse_spec(response)
            
            print("\n" + "=" * 60)
            print("TASK SPEC:")
            print(f"  Goal: {spec.get('goal', 'unclear')}")
            print(f"  Inputs: {spec.get('inputs', 'unclear')}")
            print(f"  Success: {spec.get('success_criteria', 'unclear')}")
            print("=" * 60)
            
            confirm = input("\nConfirm? (y/n/edit): ").strip().lower()
            
            if confirm == 'y':
                return finalize_task(description, spec, clarifications, session)
            elif confirm == 'edit':
                edit = input("What should change? ").strip()
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": f"Revise the spec: {edit}"})
            else:
                print("[INTAKE] Cancelled")
                return None
        else:
            # Clarifying question - get answer
            answer = input("ct> ").strip()
            
            if answer.lower() in ['quit', 'cancel', 'q', 'n']:
                print("[INTAKE] Cancelled")
                return None
            
            clarifications.append({"q": response, "a": answer})
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content": answer})

def create_simple_task(description: str, session: dict) -> dict:
    """Create a simple task without clarification."""
    citizen_home = session["citizen_home"]
    task_id = get_next_task_id(citizen_home)
    
    task = {
        "id": task_id,
        "created": now_iso(),
        "priority": 1,
        "from": "ct",
        "description": description,
        "spec": {
            "goal": description,
            "inputs": "",
            "success_criteria": "Complete the task as described"
        },
        "status": "pending"
    }
    
    # Save to pending
    task_file = citizen_home / "tasks" / "pending" / f"{task_id}.json"
    task_file.write_text(json.dumps(task, indent=2))
    
    print(f"[INTAKE] Created task {task_id}")
    return task

def finalize_task(description: str, spec: dict, clarifications: list, session: dict) -> dict:
    """Finalize and save a clarified task."""
    citizen_home = session["citizen_home"]
    task_id = get_next_task_id(citizen_home)
    
    task = {
        "id": task_id,
        "created": now_iso(),
        "priority": 1,
        "from": "ct",
        "description": description,
        "clarifications": clarifications,
        "spec": spec,
        "status": "pending"
    }
    
    # Save to pending
    task_file = citizen_home / "tasks" / "pending" / f"{task_id}.json"
    task_file.write_text(json.dumps(task, indent=2))
    
    print(f"[INTAKE] Created task {task_id}")
    return task

def parse_spec(text: str) -> dict:
    """Extract spec fields from AI response."""
    spec = {}
    lines = text.split('\n')
    current_key = None
    current_value = []
    
    for line in lines:
        line_lower = line.lower().strip()
        
        if line_lower.startswith('goal:'):
            if current_key:
                spec[current_key] = ' '.join(current_value).strip()
            current_key = 'goal'
            current_value = [line.split(':', 1)[1].strip()]
        elif line_lower.startswith('inputs:'):
            if current_key:
                spec[current_key] = ' '.join(current_value).strip()
            current_key = 'inputs'
            current_value = [line.split(':', 1)[1].strip()]
        elif line_lower.startswith('success_criteria:') or line_lower.startswith('success:'):
            if current_key:
                spec[current_key] = ' '.join(current_value).strip()
            current_key = 'success_criteria'
            current_value = [line.split(':', 1)[1].strip()]
        elif current_key and line.strip():
            current_value.append(line.strip())
    
    if current_key:
        spec[current_key] = ' '.join(current_value).strip()
    
    return spec

def add_goal(citizen_home: Path, description: str, source: str = "ct") -> dict:
    """Add a new goal to citizen's goals context."""
    goals_file = citizen_home / "contexts" / "goals.json"
    
    if goals_file.exists():
        goals_ctx = json.loads(goals_file.read_text())
    else:
        goals_ctx = {
            "id": "goals",
            "context_type": "goals",
            "created": now_iso(),
            "messages": [],
            "structured": {"active": [], "completed": []}
        }
    
    # Find next goal ID
    active = goals_ctx.get("structured", {}).get("active", [])
    existing_ids = [g.get("id", "") for g in active]
    num = 1
    while f"g_{num:03d}" in existing_ids:
        num += 1
    goal_id = f"g_{num:03d}"
    
    # Create goal
    goal = {
        "id": goal_id,
        "description": description,
        "priority": len(active) + 1,
        # NOTE: No progress_pct stored! Derived from tasks.
        "origin": source,
        "created": now_iso(),
        "tasks": []  # Progress = completed tasks / total tasks
    }
    
    # Add to structured
    if "structured" not in goals_ctx:
        goals_ctx["structured"] = {"active": [], "completed": []}
    goals_ctx["structured"]["active"].append(goal)
    
    # Add to messages
    goals_ctx["messages"].append({
        "role": "system",
        "content": f"[GOAL ADDED] {goal_id}: {description} (from {source})"
    })
    
    goals_ctx["last_modified"] = now_iso()
    goals_file.write_text(json.dumps(goals_ctx, indent=2))
    
    return goal
