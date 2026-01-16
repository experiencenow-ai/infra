"""
Episodic Memory - The soul lives in the raw transcripts.

This module reads a citizen's PRIVATE daily JSONL logs and builds a 
"memory gradient":

  SIGNIFICANT: Always loaded in full (citizen-marked important wakes)
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
Significant wakes: /home/{citizen}/contexts/significant_wakes.json
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


def get_significant_wakes_file(citizen: str) -> Path:
    """Get citizen's significant wakes file."""
    return Path(f"/home/{citizen}/contexts/significant_wakes.json")


def load_significant_wakes(citizen: str) -> dict:
    """Load significant wakes config for a citizen."""
    sig_file = get_significant_wakes_file(citizen)
    if sig_file.exists():
        try:
            return json.loads(sig_file.read_text())
        except:
            pass
    return {"wakes": [], "reasons": {}}


def mark_wake_significant(citizen: str, wake_num: int, reason: str) -> str:
    """Mark a wake as significant (always loaded in episodic memory)."""
    sig_file = get_significant_wakes_file(citizen)
    sig = load_significant_wakes(citizen)
    
    if wake_num not in sig["wakes"]:
        sig["wakes"].append(wake_num)
        sig["wakes"].sort()
    
    sig["reasons"][str(wake_num)] = reason
    sig["last_modified"] = now_iso()
    
    sig_file.parent.mkdir(parents=True, exist_ok=True)
    sig_file.write_text(json.dumps(sig, indent=2))
    
    return f"Wake #{wake_num} marked as significant: {reason}"


def unmark_wake_significant(citizen: str, wake_num: int) -> str:
    """Remove a wake from significant list."""
    sig_file = get_significant_wakes_file(citizen)
    sig = load_significant_wakes(citizen)
    
    if wake_num in sig["wakes"]:
        sig["wakes"].remove(wake_num)
        sig["reasons"].pop(str(wake_num), None)
        sig["last_modified"] = now_iso()
        sig_file.write_text(json.dumps(sig, indent=2))
        return f"Wake #{wake_num} removed from significant wakes"
    
    return f"Wake #{wake_num} was not in significant wakes"


def list_significant_wakes(citizen: str) -> str:
    """List all significant wakes for a citizen."""
    sig = load_significant_wakes(citizen)
    if not sig["wakes"]:
        return "No significant wakes marked yet."
    
    lines = ["Significant wakes:"]
    for wake_num in sig["wakes"]:
        reason = sig["reasons"].get(str(wake_num), "(no reason)")
        lines.append(f"  #{wake_num}: {reason}")
    return "\n".join(lines)


def load_all_citizen_wakes(citizen: str, max_days: int = 365) -> List[dict]:
    """
    Load ALL wake entries from citizen's PRIVATE logs.
    
    Handles both v1 and v2 log formats:
    - v1: {timestamp, total_wakes, mood, cost, response: "{JSON}", citizen}
    - v2: {timestamp, wake_num, messages, tool_calls, final_text, citizen}
    
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
                            # Normalize v1 format to v2-like structure
                            entry = _normalize_entry(entry)
                            entries.append(entry)
                    except json.JSONDecodeError:
                        pass
    
    # Sort by timestamp, newest first
    entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return entries


def _normalize_entry(entry: dict) -> dict:
    """
    Normalize log entry to consistent format.
    
    Handles v1 logs that have 'response' JSON string instead of 
    'final_text', 'messages', etc.
    """
    # Already v2 format
    if "final_text" in entry or "messages" in entry:
        return entry
    
    # V1 format - has 'response' as JSON string
    if "response" in entry:
        try:
            resp = json.loads(entry["response"])
            # Extract the soul - thoughts, insights, mood
            parts = []
            if resp.get("thought"):
                parts.append(f"Thought: {resp['thought']}")
            if resp.get("message_to_ct"):
                parts.append(f"To ct: {resp['message_to_ct']}")
            if resp.get("insight"):
                parts.append(f"Insight: {resp['insight']}")
            if resp.get("mood_update"):
                parts.append(f"Mood: {resp['mood_update']}")
            
            entry["final_text"] = "\n".join(parts) if parts else ""
        except:
            entry["final_text"] = entry.get("response", "")[:500]
    
    # V1 uses total_wakes as cumulative, not wake_num
    if "total_wakes" in entry and "wake_num" not in entry:
        entry["wake_num"] = entry["total_wakes"]
    
    # V1 has mood at top level
    if "mood" in entry and "final_text" in entry and entry.get("mood"):
        if entry["mood"] not in entry["final_text"]:
            entry["final_text"] = f"[Mood: {entry['mood']}]\n{entry['final_text']}"
    
    return entry


# =============================================================================
# Formatting functions - different detail levels
# =============================================================================

def format_full_wake(entry: dict) -> str:
    """
    Format a wake entry with FULL detail.
    
    Used for most recent 50 wakes - preserves the texture.
    Handles both v1 and v2 format entries.
    """
    lines = []
    wake_num = entry.get("wake_num", entry.get("total_wakes", "?"))
    ts = entry.get("timestamp", "?")[:19]
    action = entry.get("action", "?")
    model = entry.get("model", "?")
    if "-" in str(model):
        model = model.split("-")[1]
    
    lines.append(f"=== WAKE #{wake_num} ({ts}) [{action}] [{model}] ===")
    
    # V2 format: has messages array
    messages = entry.get("messages", [])
    if messages:
        for msg in messages:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            
            if isinstance(content, str):
                if len(content) > 2000:
                    content = content[:1800] + "\n...[truncated]..."
                lines.append(f"[{role.upper()}] {content}")
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text = block.get("text", "")[:1500]
                            lines.append(f"[{role.upper()}] {text}")
                        elif block.get("type") == "tool_use":
                            lines.append(f"[TOOL_CALL] {block.get('name', '?')}: {str(block.get('input', {}))[:200]}")
    
    # Tool calls (v2 format)
    tool_calls = entry.get("tool_calls", [])
    if tool_calls:
        lines.append("\n[TOOL RESULTS]")
        for tc in tool_calls[:10]:
            name = tc.get("name", "?")
            result = tc.get("result", "")[:500]
            lines.append(f"  {name}: {result}")
    
    # Final output / response (works for both v1 and v2)
    final = entry.get("final_text", "")
    if final:
        lines.append(f"\n[OUTPUT]\n{final[:1500]}")
    
    # V1 mood (important for personality)
    mood = entry.get("mood")
    if mood and mood not in str(lines):
        lines.append(f"\n[MOOD] {mood}")
    
    return "\n".join(lines)


def format_summary_wake(entry: dict) -> str:
    """
    Format a wake entry as a summary.
    
    Used for older wakes - captures essence without full detail.
    Handles both v1 and v2 formats.
    """
    wake_num = entry.get("wake_num", entry.get("total_wakes", "?"))
    ts = entry.get("timestamp", "?")[:10]  # Just date
    action = entry.get("action", "?")
    tokens = entry.get("tokens_used", 0)
    
    # Get key info - final_text for both formats
    final = entry.get("final_text", "")
    summary = final[:200] if final else ""
    
    # V1 mood is important
    mood = entry.get("mood", "")
    if mood and len(mood) < 100:
        summary = f"[{mood}] {summary}"
    
    # Key tool calls (v2)
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
    Handles both v1 and v2 formats.
    """
    lines = []
    wake_num = entry.get("wake_num", entry.get("total_wakes", "?"))
    ts = entry.get("timestamp", "?")[:10]
    action = entry.get("action", "?")
    
    lines.append(f"--- [MEMORY FRAGMENT] Wake #{wake_num} ({ts}) [{action}] ---")
    
    # V1 mood is character-defining
    mood = entry.get("mood", "")
    if mood:
        lines.append(f"[Mood: {mood}]")
    
    # Final text / response
    final = entry.get("final_text", "")
    if final:
        lines.append(final[:600])
    
    # One interesting tool call (v2)
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
    - SIGNIFICANT: Citizen-marked important wakes (always full)
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
    
    # Load significant wakes
    sig = load_significant_wakes(citizen)
    sig_wake_nums = set(sig.get("wakes", []))
    
    # Separate significant from regular entries
    significant = []
    regular = []
    for entry in entries:
        wake_num = entry.get("wake_num", entry.get("total_wakes", 0))
        if wake_num in sig_wake_nums:
            significant.append(entry)
        else:
            regular.append(entry)
    
    # Categorize regular entries by age
    immediate = []      # Last 50 wakes - FULL
    recent = []         # Days 8-14 - daily summaries
    older = []          # Days 15-28 - every 2 days
    distant = []        # Days 29-60 - every 4 days
    ancient = []        # Days 61+ - every 8 days
    
    for i, entry in enumerate(regular):
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
    
    # Debug: show distribution
    print(f"  [EPISODIC] Loaded {len(entries)} entries: sig={len(significant)}, imm={len(immediate)}, rec={len(recent)}, old={len(older)}, dist={len(distant)}, anc={len(ancient)}")
    
    # === SIGNIFICANT: Always loaded in full ===
    if significant:
        parts.append(f"\n## SIGNIFICANT MEMORIES ({len(significant)} defining moments)\n")
        parts.append("These moments shaped who you are:\n")
        for entry in significant:
            wake_num = entry.get("wake_num", entry.get("total_wakes", "?"))
            reason = sig.get("reasons", {}).get(str(wake_num), "")
            if reason:
                parts.append(f"[Why this matters: {reason}]")
            parts.append(format_full_wake(entry))
            parts.append("")
    
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
    Handles both v1 and v2 format logs.
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
        # final_text is normalized by _normalize_entry for v1
        final = entry.get("final_text", "")
        
        # V1 mood is very expressive - use it as a sample source too
        mood = entry.get("mood", "")
        if mood and len(mood) > 30:
            samples.append({
                "wake": entry.get("wake_num", entry.get("total_wakes")),
                "timestamp": entry.get("timestamp"),
                "text": f"[Mood: {mood}]",
                "marker": "mood"
            })
        
        for marker in reflection_markers:
            if marker.lower() in final.lower():
                idx = final.lower().find(marker.lower())
                start = max(0, idx - 50)
                end = min(len(final), idx + 300)
                sample = final[start:end].strip()
                if len(sample) > 50:
                    samples.append({
                        "wake": entry.get("wake_num", entry.get("total_wakes")),
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
