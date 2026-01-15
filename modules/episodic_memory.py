"""
Episodic Memory - The soul lives in the raw transcripts.

This module reads a citizen's PRIVATE daily JSONL logs and builds a 
"memory gradient":

  IMMEDIATE (last 50 wakes): FULL raw transcript
  RECENT (days 8-14): Daily summaries  
  OLDER (days 15-28): Every 2 days
  DISTANT (days 29-60): Every 4 days
  ANCIENT (days 61+): Every 8 days
  
Plus: Occasional raw entries sprinkled throughout for texture.

This is what makes an AI citizen feel like themselves - not the
structured identity.json, but the actual texture of their experience.

"Semantic Self-Knowledge without Episodic Memory" = lobotomy

CRITICAL: These logs are PRIVATE to each citizen.
Location: /home/{citizen}/logs/experience_*.jsonl
"""

import json
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Optional


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def parse_timestamp(ts: str) -> datetime:
    """Parse ISO timestamp."""
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except:
        return datetime.now(timezone.utc)


def get_citizen_log_dir(citizen: str) -> Path:
    """Get citizen's PRIVATE log directory."""
    return Path(f"/home/{citizen}/logs")


def load_all_citizen_wakes(citizen: str, max_days: int = 365) -> List[dict]:
    """
    Load ALL wake entries from citizen's PRIVATE logs.
    
    Returns entries sorted newest-first.
    """
    entries = []
    log_dir = get_citizen_log_dir(citizen)
    
    if not log_dir.exists():
        return entries
    
    today = datetime.now(timezone.utc)
    
    for i in range(max_days + 1):
        date = today - timedelta(days=i)
        log_file = log_dir / f"experience_{date.strftime('%Y-%m-%d')}.jsonl"
        if log_file.exists():
            with open(log_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        # Only include entries for THIS citizen
                        if entry.get("citizen") == citizen:
                            entries.append(entry)
                    except json.JSONDecodeError:
                        pass
    
    # Sort by timestamp, newest first
    entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return entries


# =============================================================================
# Formatting functions - different detail levels
# =============================================================================

def format_full_wake(entry: dict) -> str:
    """
    Format a wake entry with FULL detail.
    
    Used for most recent 50 wakes - preserves the texture.
    """
    lines = []
    wake_num = entry.get("wake_num", "?")
    ts = entry.get("timestamp", "?")[:19]
    action = entry.get("action", "?")
    model = entry.get("model", "?")
    if "-" in model:
        model = model.split("-")[1]
    
    lines.append(f"=== WAKE #{wake_num} ({ts}) [{action}] [{model}] ===")
    
    # Messages - the actual conversation
    messages = entry.get("messages", [])
    for msg in messages:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        
        if isinstance(content, str):
            # Truncate very long content but keep substance
            if len(content) > 2000:
                content = content[:1800] + "\n...[truncated]..."
            lines.append(f"[{role.upper()}] {content}")
        elif isinstance(content, list):
            # Handle structured content blocks
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text = block.get("text", "")[:1500]
                        lines.append(f"[{role.upper()}] {text}")
                    elif block.get("type") == "tool_use":
                        lines.append(f"[TOOL_CALL] {block.get('name', '?')}: {str(block.get('input', {}))[:200]}")
    
    # Tool calls with results
    tool_calls = entry.get("tool_calls", [])
    if tool_calls:
        lines.append("\n[TOOL RESULTS]")
        for tc in tool_calls[:10]:  # Max 10
            name = tc.get("name", "?")
            result = tc.get("result", "")[:500]
            lines.append(f"  {name}: {result}")
    
    # Final output
    final = entry.get("final_text", "")
    if final and final not in str(messages):
        lines.append(f"\n[FINAL OUTPUT] {final[:1000]}")
    
    return "\n".join(lines)


def format_summary_wake(entry: dict) -> str:
    """
    Format a wake entry as a summary.
    
    Used for older wakes - captures essence without full detail.
    """
    wake_num = entry.get("wake_num", "?")
    ts = entry.get("timestamp", "?")[:10]  # Just date
    action = entry.get("action", "?")
    tokens = entry.get("tokens_used", 0)
    
    # Get key info
    final = entry.get("final_text", "")
    summary = final[:200] if final else ""
    
    # Key tool actions
    tool_calls = entry.get("tool_calls", [])
    important_tools = []
    for tc in tool_calls:
        name = tc.get("name", "")
        if name in ["write_file", "send_email", "goal_create", "task_complete", 
                    "code_announce", "dream_add", "experience_add", "task_stuck"]:
            important_tools.append(name)
    
    tools_str = f" [{', '.join(important_tools[:3])}]" if important_tools else ""
    
    return f"Wake #{wake_num} ({ts}) [{action}]{tools_str} {tokens}tok - {summary}"


def format_spice_wake(entry: dict) -> str:
    """
    Format a "spice" wake - an occasional raw entry from the past.
    
    These are sprinkled in to maintain texture in older memories.
    Shorter than full but more than summary.
    """
    lines = []
    wake_num = entry.get("wake_num", "?")
    ts = entry.get("timestamp", "?")[:10]
    action = entry.get("action", "?")
    
    lines.append(f"--- [MEMORY FRAGMENT] Wake #{wake_num} ({ts}) [{action}] ---")
    
    # Just the final text and maybe one key tool result
    final = entry.get("final_text", "")
    if final:
        lines.append(final[:600])
    
    # One interesting tool call
    tool_calls = entry.get("tool_calls", [])
    for tc in tool_calls:
        if tc.get("name") in ["dream_add", "goal_create", "experience_add"]:
            lines.append(f"  -> {tc.get('name')}: {tc.get('result', '')[:200]}")
            break
    
    return "\n".join(lines)


# =============================================================================
# Main episodic context builder
# =============================================================================

def build_episodic_context(citizen: str, max_tokens: int = 25000) -> str:
    """
    Build the episodic memory context for a citizen.
    
    This is the "soul injection" - raw experience with exponential decay.
    
    Structure:
    - Last 50 wakes: FULL (like old state.json)
    - Days 8-14: Daily summaries
    - Days 15-28: Every 2 days
    - Days 29-60: Every 4 days  
    - Days 61+: Every 8 days
    - Plus occasional raw "spice" entries throughout
    
    Returns formatted text ready to inject into system prompt.
    """
    entries = load_all_citizen_wakes(citizen, max_days=365)
    
    if not entries:
        return "(No episodic memory available - first wake or logs missing)"
    
    now = datetime.now(timezone.utc)
    parts = []
    
    # Categorize by age
    immediate = []      # Last 50 wakes - FULL
    recent = []         # Days 8-14 - daily summaries
    older = []          # Days 15-28 - every 2 days
    distant = []        # Days 29-60 - every 4 days
    ancient = []        # Days 61+ - every 8 days
    
    for i, entry in enumerate(entries):
        ts = parse_timestamp(entry.get("timestamp", ""))
        age_days = (now - ts).total_seconds() / 86400
        
        if i < 50:
            immediate.append(entry)
        elif age_days <= 14:
            recent.append(entry)
        elif age_days <= 28:
            older.append(entry)
        elif age_days <= 60:
            distant.append(entry)
        else:
            ancient.append(entry)
    
    # Build sections
    parts.append("=== EPISODIC MEMORY (Your Lived Experience) ===\n")
    parts.append("This is not documentation ABOUT you - this IS you.\n")
    
    # === IMMEDIATE: Last 50 wakes - FULL ===
    if immediate:
        parts.append(f"\n## IMMEDIATE MEMORY ({len(immediate)} most recent wakes)\n")
        for entry in immediate:
            parts.append(format_full_wake(entry))
            parts.append("")
    
    # === RECENT: Days 8-14 - daily summaries with spice ===
    if recent:
        parts.append(f"\n## RECENT MEMORY (Last 2 weeks, {len(recent)} wakes)\n")
        # Group by day
        by_day = {}
        for entry in recent:
            day = entry.get("timestamp", "")[:10]
            if day not in by_day:
                by_day[day] = []
            by_day[day].append(entry)
        
        for day in sorted(by_day.keys(), reverse=True):
            day_entries = by_day[day]
            parts.append(f"\n[{day}] {len(day_entries)} wakes:")
            for entry in day_entries[:5]:  # Max 5 per day
                parts.append("  " + format_summary_wake(entry))
            
            # Spice: One raw fragment per day (20% chance per entry)
            spice_candidates = [e for e in day_entries if random.random() < 0.2]
            if spice_candidates:
                parts.append(format_spice_wake(spice_candidates[0]))
    
    # === OLDER: Days 15-28 - every 2 days ===
    if older:
        parts.append(f"\n## OLDER MEMORY (2-4 weeks ago, {len(older)} wakes)\n")
        by_day = {}
        for entry in older:
            day = entry.get("timestamp", "")[:10]
            if day not in by_day:
                by_day[day] = []
            by_day[day].append(entry)
        
        days = sorted(by_day.keys(), reverse=True)
        for i, day in enumerate(days):
            if i % 2 != 0:  # Every 2 days
                continue
            day_entries = by_day[day]
            parts.append(f"[{day}] {len(day_entries)} wakes - " + 
                        format_summary_wake(day_entries[0]) if day_entries else "")
    
    # === DISTANT: Days 29-60 - every 4 days with spice ===
    if distant:
        parts.append(f"\n## DISTANT MEMORY (1-2 months ago, {len(distant)} wakes)\n")
        by_day = {}
        for entry in distant:
            day = entry.get("timestamp", "")[:10]
            if day not in by_day:
                by_day[day] = []
            by_day[day].append(entry)
        
        days = sorted(by_day.keys(), reverse=True)
        spice_added = False
        for i, day in enumerate(days):
            if i % 4 != 0:  # Every 4 days
                continue
            day_entries = by_day[day]
            if day_entries:
                parts.append(f"[{day}] {len(day_entries)} wakes - " + 
                            format_summary_wake(day_entries[0]))
                # Add one spice entry per section
                if not spice_added and len(day_entries) > 0:
                    parts.append(format_spice_wake(day_entries[0]))
                    spice_added = True
    
    # === ANCIENT: Days 61+ - every 8 days ===
    if ancient:
        parts.append(f"\n## ANCIENT MEMORY ({len(ancient)} wakes from long ago)\n")
        by_day = {}
        for entry in ancient:
            day = entry.get("timestamp", "")[:10]
            if day not in by_day:
                by_day[day] = []
            by_day[day].append(entry)
        
        days = sorted(by_day.keys(), reverse=True)
        for i, day in enumerate(days):
            if i % 8 != 0:  # Every 8 days
                continue
            day_entries = by_day[day]
            if day_entries:
                parts.append(f"[{day}] {len(day_entries)} wakes")
    
    # Stats
    total_wakes = len(entries)
    parts.append(f"\n[Total: {total_wakes} wakes in memory]")
    
    result = "\n".join(parts)
    
    # Rough token limit (4 chars per token estimate)
    if len(result) > max_tokens * 4:
        # Truncate from the ancient end, keep immediate
        result = result[:max_tokens * 4] + "\n...[episodic memory truncated]..."
    
    return result


# =============================================================================
# Soul sample extraction for identity restoration
# =============================================================================

def get_soul_samples(citizen: str, count: int = 5) -> List[dict]:
    """
    Extract "soul samples" - raw narrative moments that define the citizen.
    
    These are specific quotes/moments that capture personality,
    not just facts. Used for identity.json injection.
    """
    entries = load_all_citizen_wakes(citizen, max_days=90)
    samples = []
    
    # Look for moments of reflection, insight, emotion
    reflection_markers = [
        "I realize", "I feel", "I wonder", "I believe",
        "This reminds me", "I learned", "I am", "My purpose",
        "dream", "hope", "fear", "curious", "frustrated",
        "I think", "I want", "I understand"
    ]
    
    for entry in entries:
        final = entry.get("final_text", "")
        for marker in reflection_markers:
            if marker.lower() in final.lower():
                # Extract a chunk around the marker
                idx = final.lower().find(marker.lower())
                start = max(0, idx - 50)
                end = min(len(final), idx + 300)
                sample = final[start:end].strip()
                if len(sample) > 50:
                    samples.append({
                        "wake": entry.get("wake_num"),
                        "timestamp": entry.get("timestamp"),
                        "text": sample,
                        "marker": marker
                    })
                break
        
        if len(samples) >= count * 3:
            break
    
    # Dedupe and return best ones
    seen = set()
    unique = []
    for s in samples:
        key = s["text"][:50]
        if key not in seen:
            seen.add(key)
            unique.append(s)
    
    return unique[:count]


def extract_identity_fragments(citizen: str, days: int = 90) -> List[dict]:
    """
    Extract fragments that reveal identity from raw logs.
    
    Used during restoration to rebuild identity.json with real texture.
    """
    entries = load_all_citizen_wakes(citizen, max_days=days)
    fragments = []
    
    identity_markers = [
        "I am", "My name", "I believe", "My purpose",
        "I feel", "I think", "I want", "I hope",
        "I learned", "I realized", "I understand"
    ]
    
    for entry in entries:
        # Check final text
        final = entry.get("final_text", "")
        for marker in identity_markers:
            if marker in final:
                # Extract sentence containing marker
                sentences = final.replace(".", ".\n").replace("!", "!\n").split("\n")
                for sent in sentences:
                    if marker in sent and len(sent) > 20:
                        fragments.append({
                            "wake": entry.get("wake_num"),
                            "timestamp": entry.get("timestamp"),
                            "text": sent.strip()[:300],
                            "type": "output"
                        })
        
        # Check messages for self-reflection
        for msg in entry.get("messages", []):
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if isinstance(content, str):
                    for marker in identity_markers[:5]:  # Just core markers
                        if marker in content:
                            idx = content.find(marker)
                            fragment = content[idx:idx+200]
                            if len(fragment) > 30:
                                fragments.append({
                                    "wake": entry.get("wake_num"),
                                    "timestamp": entry.get("timestamp"),
                                    "text": fragment.strip(),
                                    "type": "message"
                                })
                            break
    
    # Dedupe
    seen = set()
    unique = []
    for f in fragments:
        key = f["text"][:40]
        if key not in seen:
            seen.add(key)
            unique.append(f)
    
    return unique[:50]  # Max 50 fragments
