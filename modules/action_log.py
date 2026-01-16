"""
Action Log - Idempotency enforcement.

Every significant action gets logged AFTER execution.
If action already logged, skip.

AI cannot modify this log - only Python can.
"""

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable
import functools
from .time_utils import now_iso



def action_id(action_type: str, params: dict) -> str:
    """Generate unique ID for an action."""
    # Deterministic hash of action + params
    content = json.dumps({"type": action_type, "params": params}, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:16]

def get_log_path(citizen: str) -> Path:
    return Path(f"/home/{citizen}/action_log.json")

def load_log(citizen: str) -> dict:
    """Load action log for citizen."""
    path = get_log_path(citizen)
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {"completed": {}}

def save_log(citizen: str, log: dict):
    """Save action log (atomic write)."""
    path = get_log_path(citizen)
    tmp = path.with_suffix('.tmp')
    with open(tmp, 'w') as f:
        json.dump(log, f, indent=2)
    tmp.rename(path)  # Atomic on POSIX

def is_done(citizen: str, action_type: str, params: dict) -> bool:
    """Check if action already completed."""
    aid = action_id(action_type, params)
    log = load_log(citizen)
    return aid in log.get("completed", {})

def get_action(citizen: str, action_type: str, params: dict) -> Optional[dict]:
    """Get details of completed action if exists."""
    aid = action_id(action_type, params)
    log = load_log(citizen)
    return log.get("completed", {}).get(aid)

def mark_done(citizen: str, action_type: str, params: dict, result: str = "success"):
    """Mark action as completed. Called AFTER action succeeds."""
    aid = action_id(action_type, params)
    log = load_log(citizen)
    
    log["completed"][aid] = {
        "type": action_type,
        "params": params,
        "result": result[:500],  # Truncate long results
        "timestamp": now_iso()
    }
    
    save_log(citizen, log)

def get_history(citizen: str, action_type: str = None, hours: int = None) -> list:
    """Get history of completed actions."""
    log = load_log(citizen)
    actions = list(log.get("completed", {}).values())
    
    if action_type:
        actions = [a for a in actions if a["type"] == action_type]
    
    if hours:
        cutoff = datetime.now(timezone.utc).timestamp() - (hours * 3600)
        actions = [a for a in actions 
                   if datetime.fromisoformat(a["timestamp"].replace("Z", "+00:00")).timestamp() > cutoff]
    
    return sorted(actions, key=lambda x: x["timestamp"], reverse=True)

def get_recent_actions_text(citizen: str, hours: int = 24) -> str:
    """Get formatted text of recent actions for context - shows params and results."""
    actions = get_history(citizen, hours=hours)
    
    if not actions:
        return "(no recent actions)"
    
    lines = []
    for a in actions[:30]:  # Max 30 for better context
        params_str = ""
        if a.get("params"):
            # Show key params without full dump
            params = a["params"]
            if isinstance(params, dict):
                key_params = {k: str(v)[:40] for k, v in list(params.items())[:3]}
                params_str = f"({json.dumps(key_params)})"
        result_preview = a.get('result', '')[:80].replace('\n', ' ')
        lines.append(f"- {a['type']}{params_str}: {result_preview}")
    
    return "\n".join(lines)

def idempotent(action_type: str):
    """
    Decorator to make any action idempotent.
    
    Usage:
        @idempotent("create_github_repo")
        def create_repo(citizen: str, repo_name: str, **kwargs):
            # ... actual implementation
    
    The decorated function must have 'citizen' as first arg.
    Other args become the params for idempotency check.
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(citizen: str, *args, **kwargs):
            # Build params dict from args
            params = kwargs.copy()
            
            # Check if already done
            if is_done(citizen, action_type, params):
                prev = get_action(citizen, action_type, params)
                return f"ALREADY DONE ({prev['timestamp']}): {prev['result']}"
            
            # Execute
            try:
                result = func(citizen, *args, **kwargs)
                
                # Mark done
                mark_done(citizen, action_type, params, str(result))
                
                return result
            except Exception as e:
                # Don't mark done on failure
                raise
        
        return wrapper
    return decorator


# Common idempotent actions

@idempotent("send_email")
def send_email_once(citizen: str, to: str, subject: str, body_hash: str, send_func: Callable):
    """Send email only once (by hash)."""
    return send_func(to, subject)

@idempotent("create_github_repo")
def create_repo_once(citizen: str, repo_name: str, create_func: Callable):
    """Create GitHub repo only once."""
    return create_func(repo_name)

@idempotent("set_git_remote")
def set_remote_once(citizen: str, repo_path: str, remote_url: str, set_func: Callable):
    """Set git remote only once per repo+url."""
    return set_func(repo_path, remote_url)

@idempotent("add_ssh_key")
def add_key_once(citizen: str, key_fingerprint: str, add_func: Callable):
    """Add SSH key only once."""
    return add_func(key_fingerprint)

@idempotent("initialize_citizen")
def init_citizen_once(citizen: str, new_citizen: str, init_func: Callable):
    """Initialize new citizen only once."""
    return init_func(new_citizen)
