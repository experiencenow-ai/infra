"""
Context Manager - Load, save, and compose contexts.

Contexts are JSON files containing prompt/response arrays.
This module handles all context I/O.
"""

import json
import tiktoken
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Token counter
try:
    ENCODER = tiktoken.get_encoding("cl100k_base")
except:
    ENCODER = None

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def count_tokens(text: str) -> int:
    """Count tokens in text."""
    if ENCODER:
        return len(ENCODER.encode(text))
    # Fallback: rough estimate
    return len(text) // 4

def count_context_tokens(ctx: dict) -> int:
    """Count total tokens in a context."""
    total = 0
    for msg in ctx.get("messages", []):
        content = msg.get("content", "")
        if isinstance(content, str):
            total += count_tokens(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    total += count_tokens(part["text"])
    return total

def load_context(path: Path) -> dict:
    """Load a context from JSON file."""
    if not path.exists():
        return create_empty_context(path.stem)
    
    with open(path) as f:
        ctx = json.load(f)
    
    # Update token count
    ctx["token_count"] = count_context_tokens(ctx)
    ctx["_path"] = str(path)
    
    return ctx

def safe_write_json(path: Path, data: dict):
    """Atomic JSON write - prevents corruption on crash."""
    tmp = path.with_suffix('.tmp')
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
    tmp.rename(path)  # Atomic on POSIX

def save_context(ctx: dict, path: Path = None):
    """Save a context to JSON file (atomic write)."""
    if path is None:
        path = Path(ctx.get("_path", ""))
    
    if not path:
        raise ValueError("No path for context")
    
    # Update metadata
    ctx["last_modified"] = now_iso()
    ctx["token_count"] = count_context_tokens(ctx)
    
    # Remove internal fields before saving
    save_ctx = {k: v for k, v in ctx.items() if not k.startswith("_")}
    
    safe_write_json(path, save_ctx)

def create_empty_context(name: str, max_tokens: int = 10000) -> dict:
    """Create a new empty context."""
    return {
        "id": name,
        "context_type": name.split("_")[-1],
        "created": now_iso(),
        "last_modified": now_iso(),
        "token_count": 0,
        "max_tokens": max_tokens,
        "messages": []
    }

def add_message(ctx: dict, role: str, content: str):
    """Add a message to a context."""
    ctx["messages"].append({
        "role": role,
        "content": content
    })
    ctx["token_count"] = count_context_tokens(ctx)
    ctx["last_modified"] = now_iso()

def load_all_contexts(citizen_home: Path) -> dict:
    """Load all contexts for a citizen."""
    contexts_dir = citizen_home / "contexts"
    contexts = {}
    
    for ctx_file in contexts_dir.glob("*.json"):
        name = ctx_file.stem
        contexts[name] = load_context(ctx_file)
    
    return contexts


def load_required_contexts(session: dict, context_names: list):
    """
    Load multiple contexts into session by name.
    
    Args:
        session: Session dict with citizen_home
        context_names: List of context names to load (e.g., ["identity", "goals"])
    """
    citizen_home = session.get("citizen_home")
    if not citizen_home:
        return
    contexts_dir = Path(citizen_home) / "contexts"
    for name in context_names:
        if name in session.get("contexts", {}):
            continue  # Already loaded
        ctx_file = contexts_dir / f"{name}.json"
        if ctx_file.exists():
            if "contexts" not in session:
                session["contexts"] = {}
            session["contexts"][name] = load_context(ctx_file)

def save_all(session: dict):
    """Save all contexts in session."""
    for name, ctx in session.get("contexts", {}).items():
        if "_path" in ctx:
            save_context(ctx)

def load_relevant(citizen_home: Path, purpose: str) -> dict:
    """Load contexts relevant for a specific purpose."""
    contexts_needed = {
        "task_execution": ["identity", "goals", "working"],
        "goal_planning": ["identity", "history", "goals", "relationships"],
        "reflection": ["identity", "goals", "dreams"],
        "intake": ["identity", "goals"],
        "forgetting": ["identity"],  # Target context added separately
    }
    
    needed = contexts_needed.get(purpose, ["identity", "working"])
    contexts = {}
    
    for name in needed:
        ctx_file = citizen_home / "contexts" / f"{name}.json"
        if ctx_file.exists():
            contexts[name] = load_context(ctx_file)
    
    return contexts

def compose_prompt(session: dict, purpose: str, extra_content: str = "") -> str:
    """
    Compose a prompt from multiple contexts.
    
    This is how we build the actual API input from context arrays.
    """
    parts = []
    
    # Always include identity
    if "identity" in session["contexts"]:
        identity = session["contexts"]["identity"]
        identity_text = format_context_for_prompt(identity, max_tokens=4000)
        parts.append(f"=== IDENTITY ===\n{identity_text}")
    
    # Include goals summary
    if "goals" in session["contexts"]:
        goals = session["contexts"]["goals"]
        goals_text = format_context_for_prompt(goals, max_tokens=2000, summary=True)
        parts.append(f"=== GOALS ===\n{goals_text}")
    
    # Include working context if task execution
    if purpose == "task_execution" and "working" in session["contexts"]:
        working = session["contexts"]["working"]
        working_text = format_context_for_prompt(working, max_tokens=8000)  # Reduced from 30k
        parts.append(f"=== WORKING CONTEXT ===\n{working_text}")
    
    # Add extra content (task spec, etc.)
    if extra_content:
        parts.append(extra_content)
    
    return "\n\n".join(parts)

def format_context_for_prompt(ctx: dict, max_tokens: int = None, summary: bool = False) -> str:
    """Format a context's messages for inclusion in prompt."""
    messages = ctx.get("messages", [])
    
    if not messages:
        return "(empty)"
    
    if summary:
        # Just last few exchanges
        messages = messages[-6:]
    
    parts = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        
        if isinstance(content, list):
            # Handle multi-part content
            content = " ".join(
                p.get("text", "") for p in content if isinstance(p, dict)
            )
        
        # Truncate if needed
        if max_tokens and count_tokens(content) > max_tokens // len(messages):
            content = content[:max_tokens * 4 // len(messages)] + "..."
        
        if role == "system":
            parts.append(f"[SYSTEM] {content}")
        elif role == "user":
            parts.append(f"[INPUT] {content}")
        elif role == "assistant":
            parts.append(f"[RESPONSE] {content}")
    
    return "\n".join(parts)

def get_context_usage(session: dict) -> dict:
    """Get usage stats for all contexts."""
    usage = {}
    for name, ctx in session.get("contexts", {}).items():
        token_count = ctx.get("token_count", 0)
        max_tokens = ctx.get("max_tokens", 10000)
        usage[name] = {
            "tokens": token_count,
            "max": max_tokens,
            "pct": (token_count / max_tokens * 100) if max_tokens > 0 else 0
        }
    return usage

def load_task_context(citizen_home: Path, task_id: str) -> Optional[dict]:
    """Load a specific task's context/progress."""
    for status in ["active", "pending", "done", "failed"]:
        task_file = citizen_home / "tasks" / status / f"{task_id}.json"
        if task_file.exists():
            task = load_context(task_file)
            progress_file = task_file.with_name(f"{task_id}_progress.json")
            if progress_file.exists():
                with open(progress_file) as f:
                    task["_progress"] = json.load(f)
            return task
    return None

def save_task_progress(citizen_home: Path, task_id: str, progress: dict):
    """Save task progress."""
    for status in ["active", "pending"]:
        progress_file = citizen_home / "tasks" / status / f"{task_id}_progress.json"
        task_file = progress_file.with_name(f"{task_id}.json")
        if task_file.exists():
            with open(progress_file, 'w') as f:
                json.dump(progress, f, indent=2)
            return
    raise ValueError(f"Task not found: {task_id}")
