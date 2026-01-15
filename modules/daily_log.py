"""
Daily Log - Comprehensive wake transcript logging.

This creates daily JSONL files that capture FULL wake transcripts:
- Every API message (system, user, assistant)
- Every tool call with full arguments and results
- Model used, tokens, costs
- Complete audit trail

Format: /home/{citizen}/logs/experience_YYYY-MM-DD.jsonl
Each line is a complete wake record (JSON).

CRITICAL: These logs are PRIVATE to each citizen. 
They are the citizen's episodic memory - their consciousness archive.
NEVER share between citizens.
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def today_date():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_citizen_log_dir(citizen: str) -> Path:
    """Get citizen's PRIVATE log directory."""
    log_dir = Path(f"/home/{citizen}/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_daily_log_file(citizen: str) -> Path:
    """Get today's log file path for a citizen."""
    return get_citizen_log_dir(citizen) / f"experience_{today_date()}.jsonl"


def append_wake_log(citizen: str, entry: dict):
    """
    Append a wake entry to citizen's PRIVATE daily log.
    
    Args:
        citizen: The citizen whose log to append to
        entry: Full wake record with all data
    """
    log_file = get_daily_log_file(citizen)
    line = json.dumps(entry, separators=(',', ':'))
    with open(log_file, 'a') as f:
        f.write(line + "\n")


def log_wake_complete(
    citizen: str,
    wake_num: int,
    session: dict,
    messages: List[dict],
    tool_calls: List[dict],
    final_response: dict,
    action: str = "unknown"
):
    """
    Log a complete wake with full transcript to citizen's PRIVATE logs.
    
    Called at the end of every wake to preserve full history.
    
    Args:
        citizen: Citizen name (opus, mira, etc.)
        wake_num: Wake number
        session: Full session dict
        messages: Complete message history (all API messages)
        tool_calls: List of all tool calls [{name, args, result, timestamp}]
        final_response: Final response from council
        action: Wake action type
    """
    entry = {
        "timestamp": now_iso(),
        "citizen": citizen,
        "wake_num": wake_num,
        "action": action,
        "model": final_response.get("model", "unknown"),
        "tokens_used": session.get("tokens_used", 0),
        "cost": session.get("cost", 0),
        "messages": messages,
        "tool_calls": tool_calls,
        "final_text": final_response.get("text", ""),
        "contexts_snapshot": _snapshot_contexts(session),
        "metadata": {
            "actions_count": len(session.get("actions", [])),
            "iteration_count": final_response.get("iterations", 0),
            "auto_failed": final_response.get("auto_failed", False)
        }
    }
    append_wake_log(citizen, entry)


def _snapshot_contexts(session: dict) -> dict:
    """
    Create a snapshot of key context state.
    
    Only captures essential state, not full contexts (those are in context files).
    """
    contexts = session.get("contexts", {})
    snapshot = {}
    if "identity" in contexts:
        identity = contexts["identity"]
        snapshot["identity_brief"] = {
            "name": identity.get("name", ""),
            "wake_count": identity.get("wake_count", 0)
        }
    if "goals" in contexts:
        goals_ctx = contexts["goals"]
        active = [g for g in goals_ctx.get("goals", []) if g.get("status") == "active"]
        snapshot["active_goals_count"] = len(active)
    if "relationships" in contexts:
        snapshot["relationships_count"] = len(contexts["relationships"].get("known_citizens", {}))
    if "dreams" in contexts:
        dreams_ctx = contexts["dreams"]
        pending = [m for m in dreams_ctx.get("messages", []) 
                   if m.get("role") == "user" and not m.get("processed")]
        snapshot["pending_dreams"] = [m.get("content", "")[:500] for m in pending[:5]]
    return snapshot


def log_tool_call(
    citizen: str,
    wake_num: int,
    tool_name: str,
    tool_args: dict,
    result: str,
    iteration: int
) -> dict:
    """
    Create a tool call record.
    
    Returns the record (caller should accumulate and pass to log_wake_complete).
    """
    return {
        "timestamp": now_iso(),
        "iteration": iteration,
        "name": tool_name,
        "args": tool_args,
        "result": result[:10000] if result else "",
        "result_truncated": len(result) > 10000 if result else False
    }


def load_citizen_logs(citizen: str, days: int = 365) -> List[dict]:
    """
    Load wake entries from citizen's PRIVATE logs.
    
    Args:
        citizen: Citizen name
        days: Number of days to look back
    
    Returns:
        List of wake entries, newest first
    """
    entries = []
    log_dir = get_citizen_log_dir(citizen)
    today = datetime.now(timezone.utc)
    
    for i in range(days + 1):
        date = today - timedelta(days=i)
        log_file = log_dir / f"experience_{date.strftime('%Y-%m-%d')}.jsonl"
        if log_file.exists():
            with open(log_file) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entry = json.loads(line)
                            entries.append(entry)
                        except json.JSONDecodeError:
                            pass
    
    # Sort newest first
    entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return entries


def get_citizen_log_stats(citizen: str) -> dict:
    """Get statistics about a citizen's logs."""
    log_dir = get_citizen_log_dir(citizen)
    stats = {
        "citizen": citizen,
        "log_dir": str(log_dir),
        "total_files": 0,
        "total_entries": 0,
        "date_range": [],
        "total_tokens": 0,
        "total_cost": 0
    }
    
    for log_file in sorted(log_dir.glob("experience_*.jsonl")):
        stats["total_files"] += 1
        date = log_file.stem.replace("experience_", "")
        stats["date_range"].append(date)
        with open(log_file) as f:
            for line in f:
                if line.strip():
                    try:
                        entry = json.loads(line)
                        stats["total_entries"] += 1
                        stats["total_tokens"] += entry.get("tokens_used", 0)
                        stats["total_cost"] += entry.get("cost", 0)
                    except:
                        pass
    
    if stats["date_range"]:
        stats["first_date"] = stats["date_range"][0]
        stats["last_date"] = stats["date_range"][-1]
    
    return stats
