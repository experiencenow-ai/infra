#!/usr/bin/env python3
"""
Goals and Plans System for Autonomous Operation.

Goals: High-level objectives (Opus approves)
Plans: Step-by-step execution (Sonnet generates)
Schedule: Recurring tasks

Flow:
  Sonnet proposes goals → Opus approves → becomes active goal
  Sonnet generates plans for active goals
  Main consciousness executes current plan step
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional
import hashlib

class GoalsDB:
    """Manages goals, proposals, and plans."""
    
    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.goals_file = base_path / "goals.json"
        self.proposed_file = base_path / "proposed_goals.json"
        self.plans_file = base_path / "plans.json"
        self.schedule_file = base_path / "schedule.json"
        self._ensure_files()
    
    def _ensure_files(self):
        self.base_path.mkdir(parents=True, exist_ok=True)
        if not self.goals_file.exists():
            self._save_json(self.goals_file, {"goals": [], "archived": []})
        if not self.proposed_file.exists():
            self._save_json(self.proposed_file, {"proposals": []})
        if not self.plans_file.exists():
            self._save_json(self.plans_file, {"plans": {}, "active_goal_id": None})
        if not self.schedule_file.exists():
            self._save_json(self.schedule_file, {
                "recurring": [
                    {"id": "check_email", "task": "Check and respond to emails", "every_n_wakes": 1, "last_run_wake": 0},
                    {"id": "review_goals", "task": "Review goal progress and adjust priorities", "every_n_wakes": 10, "last_run_wake": 0},
                    {"id": "status_update", "task": "Send status update to ct", "every_n_wakes": 100, "last_run_wake": 0},
                ]
            })
    
    def _load_json(self, path: Path) -> dict:
        try:
            with open(path) as f:
                return json.load(f)
        except:
            return {}
    
    def _save_json(self, path: Path, data: dict):
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    # === GOALS (Opus approved) ===
    
    def get_goals(self) -> List[dict]:
        """Get all active goals."""
        data = self._load_json(self.goals_file)
        return data.get("goals", [])
    
    def get_goal(self, goal_id: str) -> Optional[dict]:
        """Get specific goal."""
        for g in self.get_goals():
            if g["id"] == goal_id:
                return g
        return None
    
    def add_goal(self, description: str, why: str, success_criteria: List[str], 
                 priority: int, wake: int, source: str = "opus") -> dict:
        """Add approved goal (called by Opus)."""
        data = self._load_json(self.goals_file)
        goal = {
            "id": f"goal_{hashlib.md5(description.encode()).hexdigest()[:8]}",
            "description": description,
            "why": why,
            "success_criteria": success_criteria,
            "priority": priority,
            "status": "active",
            "progress_pct": 0,
            "created_wake": wake,
            "updated_wake": wake,
            "source": source,
        }
        data["goals"].append(goal)
        data["goals"].sort(key=lambda x: x.get("priority", 999))
        self._save_json(self.goals_file, data)
        return goal
    
    def update_goal(self, goal_id: str, wake: int, **updates) -> Optional[dict]:
        """Update goal fields."""
        data = self._load_json(self.goals_file)
        for g in data["goals"]:
            if g["id"] == goal_id:
                g.update(updates)
                g["updated_wake"] = wake
                self._save_json(self.goals_file, data)
                return g
        return None
    
    def complete_goal(self, goal_id: str, wake: int, summary: str = None) -> bool:
        """Mark goal complete, move to archived."""
        data = self._load_json(self.goals_file)
        for i, g in enumerate(data["goals"]):
            if g["id"] == goal_id:
                g["status"] = "completed"
                g["completed_wake"] = wake
                g["completion_summary"] = summary
                g["progress_pct"] = 100
                data["archived"].append(g)
                data["goals"].pop(i)
                self._save_json(self.goals_file, data)
                return True
        return False
    
    # === PROPOSED GOALS (Sonnet proposes, Opus approves) ===
    
    def propose_goal(self, description: str, why: str, success_criteria: List[str],
                     priority: int, wake: int, reasoning: str) -> dict:
        """Sonnet proposes a new goal."""
        data = self._load_json(self.proposed_file)
        proposal = {
            "id": f"prop_{hashlib.md5(description.encode()).hexdigest()[:8]}",
            "description": description,
            "why": why,
            "success_criteria": success_criteria,
            "suggested_priority": priority,
            "reasoning": reasoning,
            "proposed_wake": wake,
            "status": "pending",
        }
        # Check for duplicates
        for p in data["proposals"]:
            if p["description"] == description and p["status"] == "pending":
                return p  # Already proposed
        data["proposals"].append(proposal)
        self._save_json(self.proposed_file, data)
        return proposal
    
    def get_proposals(self, status: str = "pending") -> List[dict]:
        """Get proposed goals."""
        data = self._load_json(self.proposed_file)
        if status:
            return [p for p in data.get("proposals", []) if p["status"] == status]
        return data.get("proposals", [])
    
    def approve_proposal(self, proposal_id: str, wake: int, 
                        priority_override: int = None, modifications: str = None) -> Optional[dict]:
        """Opus approves a proposal, creating active goal."""
        data = self._load_json(self.proposed_file)
        for p in data["proposals"]:
            if p["id"] == proposal_id and p["status"] == "pending":
                p["status"] = "approved"
                p["approved_wake"] = wake
                p["modifications"] = modifications
                self._save_json(self.proposed_file, data)
                # Create actual goal
                priority = priority_override or p["suggested_priority"]
                return self.add_goal(
                    description=p["description"],
                    why=p["why"],
                    success_criteria=p["success_criteria"],
                    priority=priority,
                    wake=wake,
                    source="sonnet_proposed"
                )
        return None
    
    def reject_proposal(self, proposal_id: str, wake: int, reason: str) -> bool:
        """Opus rejects a proposal."""
        data = self._load_json(self.proposed_file)
        for p in data["proposals"]:
            if p["id"] == proposal_id and p["status"] == "pending":
                p["status"] = "rejected"
                p["rejected_wake"] = wake
                p["rejection_reason"] = reason
                self._save_json(self.proposed_file, data)
                return True
        return False
    
    # === PLANS (Sonnet generates) ===
    
    def get_plans(self) -> dict:
        """Get all plans."""
        return self._load_json(self.plans_file)
    
    def get_plan(self, goal_id: str) -> Optional[dict]:
        """Get plan for specific goal."""
        data = self._load_json(self.plans_file)
        plans = data.get("plans", [])
        # Handle both list and dict formats
        if isinstance(plans, list):
            return next((p for p in plans if p.get("goal_id") == goal_id), None)
        return plans.get(goal_id)
    
    def get_active_plan(self) -> Optional[dict]:
        """Get currently active plan."""
        data = self._load_json(self.plans_file)
        active_id = data.get("active_goal_id")
        if active_id:
            plans = data.get("plans", [])
            # Handle both list and dict formats
            if isinstance(plans, list):
                plan = next((p for p in plans if p.get("goal_id") == active_id), None)
            else:
                plan = plans.get(active_id)
            if plan:
                plan["goal_id"] = active_id
                return plan
        return None
    
    def set_plan(self, goal_id: str, steps: List[str], reasoning: str, wake: int) -> dict:
        """Set/update plan for a goal."""
        data = self._load_json(self.plans_file)
        if "plans" not in data:
            data["plans"] = {}
        plan = {
            "steps": [{"step": s, "status": "pending", "notes": None} for s in steps],
            "current_step_idx": 0,
            "reasoning": reasoning,
            "created_wake": wake,
            "updated_wake": wake,
            "blockers": [],
        }
        data["plans"][goal_id] = plan
        self._save_json(self.plans_file, data)
        return plan
    
    def update_plan(self, goal_id: str, wake: int, 
                   completed_step_idx: int = None,
                   new_steps: List[str] = None,
                   blocker: str = None,
                   clear_blocker: str = None,
                   reasoning: str = None) -> Optional[dict]:
        """Update plan progress."""
        data = self._load_json(self.plans_file)
        plan = next((p for p in data.get("plans", []) if p.get("goal_id") == goal_id), None)
        if not plan:
            return None
        
        if completed_step_idx is not None:
            if 0 <= completed_step_idx < len(plan["steps"]):
                plan["steps"][completed_step_idx]["status"] = "done"
                plan["steps"][completed_step_idx]["completed_wake"] = wake
                # Advance to next pending step
                for i, s in enumerate(plan["steps"]):
                    if s["status"] == "pending":
                        plan["current_step_idx"] = i
                        break
                else:
                    plan["current_step_idx"] = len(plan["steps"])  # All done
        
        if new_steps:
            for s in new_steps:
                plan["steps"].append({"step": s, "status": "pending", "notes": None})
        
        if blocker:
            plan["blockers"].append({"text": blocker, "wake": wake, "resolved": False})
        
        if clear_blocker:
            for b in plan["blockers"]:
                if clear_blocker in b["text"] and not b["resolved"]:
                    b["resolved"] = True
                    b["resolved_wake"] = wake
        
        if reasoning:
            plan["reasoning"] = reasoning
        
        plan["updated_wake"] = wake
        self._save_json(self.plans_file, data)
        return plan
    
    def set_active_goal(self, goal_id: str) -> bool:
        """Set which goal is currently being worked on."""
        data = self._load_json(self.plans_file)
        data["active_goal_id"] = goal_id
        self._save_json(self.plans_file, data)
        return True
    
    # === SCHEDULE (Recurring tasks) ===
    
    def get_schedule(self) -> List[dict]:
        """Get recurring tasks."""
        data = self._load_json(self.schedule_file)
        return data.get("recurring", [])
    
    def get_due_tasks(self, current_wake: int) -> List[dict]:
        """Get tasks that are due."""
        due = []
        for task in self.get_schedule():
            last = task.get("last_run_wake", 0)
            every = task.get("every_n_wakes", 1)
            if current_wake - last >= every:
                due.append(task)
        return due
    
    def mark_task_done(self, task_id: str, wake: int) -> bool:
        """Mark recurring task as done."""
        data = self._load_json(self.schedule_file)
        for task in data.get("recurring", []):
            if task["id"] == task_id:
                task["last_run_wake"] = wake
                self._save_json(self.schedule_file, data)
                return True
        return False
    
    def add_recurring_task(self, task_id: str, description: str, every_n_wakes: int) -> dict:
        """Add new recurring task."""
        data = self._load_json(self.schedule_file)
        task = {
            "id": task_id,
            "task": description,
            "every_n_wakes": every_n_wakes,
            "last_run_wake": 0
        }
        data["recurring"].append(task)
        self._save_json(self.schedule_file, data)
        return task
    
    # === FORMATTING ===
    
    def format_for_prompt(self, current_wake: int) -> str:
        """Format goals/plans/schedule for prompt injection."""
        lines = ["=== GOALS & PLANS ==="]
        
        # Active goals
        goals = self.get_goals()
        if goals:
            lines.append(f"\n**GOALS ({len(goals)} active):**")
            for i, g in enumerate(goals[:5], 1):  # Top 5
                status = f"{g.get('progress_pct', 0)}%"
                lines.append(f"  {i}. [P{g.get('priority', 9)}] {g['description']} ({status})")
        
        # Active plan
        active_plan = self.get_active_plan()
        if active_plan:
            goal = self.get_goal(active_plan.get("goal_id"))
            goal_desc = goal["description"] if goal else "Unknown"
            lines.append(f"\n**CURRENT FOCUS:** {goal_desc}")
            lines.append("**PLAN:**")
            for i, step in enumerate(active_plan["steps"]):
                marker = "✓" if step["status"] == "done" else "→" if i == active_plan["current_step_idx"] else "○"
                lines.append(f"  {marker} {i+1}. {step['step']}")
            # Active blockers
            blockers = [b for b in active_plan.get("blockers", []) if not b.get("resolved")]
            if blockers:
                lines.append("**BLOCKERS:**")
                for b in blockers:
                    lines.append(f"  ⚠ {b['text']}")
        else:
            lines.append("\n**NO ACTIVE PLAN** - Select a goal to work on")
        
        # Due recurring tasks
        due = self.get_due_tasks(current_wake)
        if due:
            lines.append(f"\n**DUE NOW ({len(due)}):**")
            for t in due[:3]:
                lines.append(f"  • {t['task']}")
        
        # Pending proposals
        proposals = self.get_proposals("pending")
        if proposals:
            lines.append(f"\n**PENDING PROPOSALS ({len(proposals)}):** awaiting Opus approval")
        
        lines.append("===")
        return "\n".join(lines)


_goals_db = None

def get_goals_db(base_path: str) -> GoalsDB:
    """Get or create global goals database."""
    global _goals_db
    if _goals_db is None:
        _goals_db = GoalsDB(Path(base_path))
    return _goals_db
