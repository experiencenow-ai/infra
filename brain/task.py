#!/usr/bin/env python3
"""
Task Database - Working Memory for Current Task Continuity

This is the 7th database - not tiered like semantic memory, but a simple
persistent store that tracks:
- Current task description
- What's been done
- What remains
- Key context/parameters
- Blockers/issues

This ensures the AI doesn't forget basic things between wakes.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict

class TaskDB:
    """Working memory for current task state."""
    
    def __init__(self, path: Path):
        self.path = path / "task_db.json"
        self.data = self._load()
    
    def _load(self) -> dict:
        if self.path.exists():
            try:
                with open(self.path) as f:
                    return json.load(f)
            except:
                pass
        return {
            "current_task": None,
            "task_history": [],
            "active_context": {},
        }
    
    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, 'w') as f:
            json.dump(self.data, f, indent=2)
    
    def set_task(self, description: str, wake: int, steps: List[str] = None) -> dict:
        """Set a new current task."""
        # Archive previous task if exists
        if self.data["current_task"]:
            self.data["current_task"]["ended_wake"] = wake
            self.data["current_task"]["status"] = "abandoned"
            self.data["task_history"].append(self.data["current_task"])
            # Keep only last 20 tasks in history
            self.data["task_history"] = self.data["task_history"][-20:]
        
        task = {
            "id": f"task_{wake}_{datetime.now().strftime('%H%M%S')}",
            "description": description,
            "created_wake": wake,
            "updated_wake": wake,
            "status": "active",
            "steps": [{"step": s, "done": False, "wake_completed": None} for s in (steps or [])],
            "completed_steps": [],
            "notes": [],
            "blockers": [],
            "context": {},
        }
        self.data["current_task"] = task
        self._save()
        return task
    
    def get_task(self) -> Optional[dict]:
        """Get current task."""
        return self.data.get("current_task")
    
    def update_progress(self, wake: int, completed_step: str = None, note: str = None, 
                       blocker: str = None, context_key: str = None, context_value: str = None) -> dict:
        """Update task progress."""
        task = self.data.get("current_task")
        if not task:
            return None
        
        task["updated_wake"] = wake
        
        if completed_step:
            # Mark step as done
            for step in task["steps"]:
                if step["step"] == completed_step and not step["done"]:
                    step["done"] = True
                    step["wake_completed"] = wake
                    task["completed_steps"].append({
                        "step": completed_step,
                        "wake": wake
                    })
                    break
            else:
                # Step not in list, add it as completed
                task["completed_steps"].append({
                    "step": completed_step,
                    "wake": wake
                })
        
        if note:
            task["notes"].append({
                "note": note,
                "wake": wake
            })
            # Keep only last 20 notes
            task["notes"] = task["notes"][-20:]
        
        if blocker:
            task["blockers"].append({
                "blocker": blocker,
                "wake": wake,
                "resolved": False
            })
        
        if context_key and context_value:
            task["context"][context_key] = {
                "value": context_value,
                "wake": wake
            }
        
        self._save()
        return task
    
    def resolve_blocker(self, blocker_text: str, wake: int) -> bool:
        """Mark a blocker as resolved."""
        task = self.data.get("current_task")
        if not task:
            return False
        
        for b in task["blockers"]:
            if blocker_text in b["blocker"] and not b["resolved"]:
                b["resolved"] = True
                b["resolved_wake"] = wake
                self._save()
                return True
        return False
    
    def add_step(self, step: str, wake: int) -> bool:
        """Add a new step to current task."""
        task = self.data.get("current_task")
        if not task:
            return False
        
        task["steps"].append({
            "step": step,
            "done": False,
            "wake_completed": None,
            "added_wake": wake
        })
        task["updated_wake"] = wake
        self._save()
        return True
    
    def complete_task(self, wake: int, summary: str = None) -> dict:
        """Mark current task as complete."""
        task = self.data.get("current_task")
        if not task:
            return None
        
        task["status"] = "completed"
        task["ended_wake"] = wake
        task["completion_summary"] = summary
        
        self.data["task_history"].append(task)
        self.data["task_history"] = self.data["task_history"][-20:]
        self.data["current_task"] = None
        self._save()
        return task
    
    def set_context(self, key: str, value: str, wake: int):
        """Set active context (persists across tasks)."""
        self.data["active_context"][key] = {
            "value": value,
            "wake": wake
        }
        self._save()
    
    def get_context(self, key: str) -> Optional[str]:
        """Get active context value."""
        ctx = self.data["active_context"].get(key)
        return ctx["value"] if ctx else None
    
    def clear_context(self, key: str = None):
        """Clear context (specific key or all)."""
        if key:
            self.data["active_context"].pop(key, None)
        else:
            self.data["active_context"] = {}
        self._save()
    
    def format_for_prompt(self) -> str:
        """Format task state for injection into prompt."""
        task = self.data.get("current_task")
        ctx = self.data.get("active_context", {})
        
        lines = ["=== WORKING MEMORY (Task State) ==="]
        
        if task:
            lines.append(f"**CURRENT TASK:** {task['description']}")
            lines.append(f"Status: {task['status']} | Started: wake {task['created_wake']} | Updated: wake {task['updated_wake']}")
            
            # Steps
            if task["steps"]:
                lines.append("\n**STEPS:**")
                for i, step in enumerate(task["steps"], 1):
                    status = "✓" if step["done"] else "○"
                    lines.append(f"  {status} {i}. {step['step']}")
            
            # Recent completed (not in original steps)
            recent_completed = [c for c in task["completed_steps"][-5:] 
                               if c["step"] not in [s["step"] for s in task["steps"]]]
            if recent_completed:
                lines.append("\n**RECENTLY COMPLETED:**")
                for c in recent_completed:
                    lines.append(f"  ✓ {c['step']} (wake {c['wake']})")
            
            # Active blockers
            active_blockers = [b for b in task["blockers"] if not b["resolved"]]
            if active_blockers:
                lines.append("\n**BLOCKERS:**")
                for b in active_blockers:
                    lines.append(f"  ⚠ {b['blocker']}")
            
            # Recent notes
            if task["notes"]:
                lines.append("\n**RECENT NOTES:**")
                for n in task["notes"][-3:]:
                    lines.append(f"  - {n['note'][:100]}")
            
            # Task context
            if task["context"]:
                lines.append("\n**TASK CONTEXT:**")
                for k, v in list(task["context"].items())[-5:]:
                    lines.append(f"  {k}: {v['value'][:100]}")
        else:
            lines.append("**NO ACTIVE TASK** - Consider: What should you be working on?")
        
        # Active context (persists across tasks)
        if ctx:
            lines.append("\n**PERSISTENT CONTEXT:**")
            for k, v in list(ctx.items())[-5:]:
                lines.append(f"  {k}: {v['value'][:100]}")
        
        lines.append("===")
        return "\n".join(lines)
    
    def get_summary(self) -> dict:
        """Get summary for tools."""
        task = self.data.get("current_task")
        return {
            "has_active_task": task is not None,
            "task_description": task["description"] if task else None,
            "task_status": task["status"] if task else None,
            "steps_total": len(task["steps"]) if task else 0,
            "steps_done": sum(1 for s in task["steps"] if s["done"]) if task else 0,
            "active_blockers": len([b for b in task["blockers"] if not b["resolved"]]) if task else 0,
            "task_history_count": len(self.data["task_history"]),
            "active_context_keys": list(self.data["active_context"].keys()),
        }


_task_db = None

def get_task_db(base_path: str) -> TaskDB:
    """Get or create global task database."""
    global _task_db
    if _task_db is None:
        _task_db = TaskDB(Path(base_path))
    return _task_db
