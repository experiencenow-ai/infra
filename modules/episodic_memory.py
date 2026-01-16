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
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Optional

# Stopwords for compression - remove these to save tokens
STOPWORDS = frozenset({
    'the','a','an','is','are','was','were','be','been','being',
    'have','has','had','do','does','did','will','would','could',
    'should','may','might','must','shall','can','need','to','of',
    'in','for','on','with','at','by','from','as','into','through',
    'during','before','after','above','below','between','under',
    'again','further','then','once','here','there','when','where',
    'why','how','all','each','both','few','more','most','other',
    'some','such','no','nor','not','only','own','same','so','than',
    'too','very','just','also','now','i','me','my','myself','we',
    'our','ours','you','your','he','him','his','she','her','it',
    'its','they','them','their','this','that','these','those','am',
    'and','but','if','or','because','until','while','about','into',
    'during','throughout','regarding','concerning'
})

def compress_text(text: str, aggressive: bool = False) -> str:
    """
    Compress text by removing stopwords and redundancy.
    
    aggressive=False: ~30% reduction, readable
    aggressive=True: ~50% reduction, telegraphic
    """
    if not text or len(text) < 100:
        return text
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove common filler phrases
    fillers = [
        r'\bI think that\b', r'\bI believe that\b', r'\bIt seems that\b',
        r'\bIn order to\b', r'\bAs a result\b', r'\bDue to the fact that\b',
        r'\bAt this point in time\b', r'\bIn the event that\b',
        r'\bFor the purpose of\b', r'\bWith regard to\b',
        r'\bI am going to\b', r'\bI will be\b', r'\bI would like to\b',
    ]
    for filler in fillers:
        text = re.sub(filler, '', text, flags=re.IGNORECASE)
    
    if aggressive:
        # Remove stopwords
        words = text.split()
        words = [w for w in words if w.lower().strip('.,!?:;') not in STOPWORDS]
        text = ' '.join(words)
    
    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def parse_timestamp(ts: str) -> datetime:
    """Parse ISO timestamp. Returns very old date on failure to push to ancient."""
    if not ts:
        # Empty timestamp → treat as ancient
        return datetime(2020, 1, 1, tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except:
        # Failed parse → treat as ancient (not recent!)
        return datetime(2020, 1, 1, tzinfo=timezone.utc)


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
    Format a wake entry - COMPACT and COMPRESSED.
    
    Prioritizes: wake number, action, key tools used, and final output.
    Applies text compression to reduce token count.
    """
    lines = []
    wake_num = entry.get("wake_num", entry.get("total_wakes", "?"))
    ts = entry.get("timestamp", "")[:10]  # Just date
    action = entry.get("action", "?")
    
    lines.append(f"#{wake_num} ({ts}) [{action}]")
    
    # Key tool calls only (not full results)
    tool_calls = entry.get("tool_calls", [])
    if tool_calls:
        tool_names = [tc.get("name", "?") for tc in tool_calls[:6]]
        lines.append(f"Tools: {','.join(tool_names)}")
    
    # Final output - compressed
    final = entry.get("final_text", "")
    if final:
        compressed = compress_text(final[:600], aggressive=True)
        lines.append(compressed)
    
    # V1 mood (character-defining) - short only
    mood = entry.get("mood")
    if mood and len(str(mood)) < 100:
        lines.append(f"Mood:{mood}")
    
    return " | ".join(lines)  # Single line format


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
    
    HEAVILY OPTIMIZED for token efficiency:
    - Semantic clustering of similar wakes (sentence-transformers)
    - Linguistic compression (NLTK stopwords + stemming)
    - Global deduplication fallback
    
    Returns formatted text ready to inject into system prompt.
    """
    entries = load_all_citizen_wakes(citizen, max_days=365)
    
    if not entries:
        return "(No episodic memory available)"
    
    # Try semantic clustering first (best compression)
    try:
        from modules.prompt_compress import compress_episodic_wakes, get_compression_status
        status = get_compression_status()
        
        if status["sentence_transformers"]:
            # Use semantic clustering
            result = compress_episodic_wakes(entries, max_output_chars=max_tokens * 4)
            print(f"  [EPISODIC] Semantic clustering: {len(entries)} wakes → {len(result)} chars")
            return f"=== EPISODIC MEMORY ===\n{result}"
    except Exception as e:
        print(f"  [EPISODIC] Semantic clustering failed: {e}, using fallback")
    
    # Fallback: hash-based deduplication
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
    
    # Categorize regular entries
    immediate = regular[:20]   # Last 20 wakes
    older = regular[20:]       # Everything else
    
    # Hash-based deduplication
    seen_content = set()
    
    def dedupe_entry(entry: dict) -> Optional[str]:
        """Return formatted entry only if content is novel."""
        final = entry.get("final_text", "")[:500]
        content_hash = hash(final)
        if content_hash in seen_content:
            return None
        seen_content.add(content_hash)
        return format_full_wake(entry)
    
    # Build sections
    parts.append("=== EPISODIC MEMORY ===\n")
    
    # Count what we actually include
    sig_included = 0
    imm_included = 0
    
    # === SIGNIFICANT: Always loaded, but deduplicated ===
    if significant:
        parts.append(f"\n## DEFINING MOMENTS\n")
        for entry in significant[:10]:
            formatted = dedupe_entry(entry)
            if formatted:
                wake_num = entry.get("wake_num", entry.get("total_wakes", "?"))
                reason = sig.get("reasons", {}).get(str(wake_num), "")
                if reason:
                    parts.append(f"[Why: {reason}]")
                parts.append(formatted)
                parts.append("")
                sig_included += 1
    
    # === IMMEDIATE: Last 20 wakes, deduplicated ===
    if immediate:
        parts.append(f"\n## RECENT ({len(immediate)} wakes)\n")
        for entry in immediate:
            formatted = dedupe_entry(entry)
            if formatted:
                parts.append(formatted)
                parts.append("")
                imm_included += 1
            else:
                # Still note it existed, just don't repeat content
                wake_num = entry.get("wake_num", entry.get("total_wakes", "?"))
                action = entry.get("action", "?")
                parts.append(f"[Wake #{wake_num} - {action} - similar to above]")
    
    # === OLDER: Compressed activity summary only ===
    if older:
        compressed = _compress_older_wakes(older)
        parts.append(f"\n## EARLIER ({len(older)} wakes)\n")
        parts.append(compressed)
    
    # Debug
    total = len(entries)
    skipped = len(significant) + len(immediate) - sig_included - imm_included
    print(f"  [EPISODIC] {total} entries: {sig_included}/{len(significant)} sig, {imm_included}/{len(immediate)} imm, {len(older)} compressed, {skipped} deduped")
    
    result = "\n".join(parts)
    
    # Final size check
    if len(result) > max_tokens * 4:
        result = result[:max_tokens * 4] + "\n...[truncated]..."
    
    return result


def _deduplicate_wakes(entries: List[dict]) -> str:
    """
    Deduplicate similar consecutive wakes.
    
    Groups by action type and summarizes runs:
    "Wakes #100-105: 6 DESIGN wakes - architecture work"
    """
    if not entries:
        return ""
    
    lines = []
    groups = []
    current_group = {"action": None, "wakes": [], "samples": []}
    
    for entry in entries:
        action = entry.get("action", "unknown")
        wake_num = entry.get("wake_num", entry.get("total_wakes", "?"))
        
        if action == current_group["action"]:
            current_group["wakes"].append(wake_num)
            if len(current_group["samples"]) < 2:
                current_group["samples"].append(entry)
        else:
            if current_group["wakes"]:
                groups.append(current_group)
            current_group = {"action": action, "wakes": [wake_num], "samples": [entry]}
    
    if current_group["wakes"]:
        groups.append(current_group)
    
    for g in groups:
        wakes = g["wakes"]
        action = g["action"]
        
        if len(wakes) == 1:
            # Single wake - show summary
            sample = g["samples"][0]
            final = sample.get("final_text", "")[:150]
            lines.append(f"Wake #{wakes[0]} [{action}]: {final}")
        else:
            # Multiple similar wakes - show range and one sample
            wake_range = f"#{min(wakes)}-#{max(wakes)}"
            sample = g["samples"][0]
            final = sample.get("final_text", "")[:100]
            lines.append(f"Wakes {wake_range} ({len(wakes)}x {action}): {final}...")
    
    return "\n".join(lines)


def _compress_older_wakes(entries: List[dict]) -> str:
    """
    Heavily compress older wakes into activity overview.
    
    Returns something like:
    "Jan 10-15: 45 wakes - 20 CODE, 15 DESIGN, 5 LIBRARY, 5 other"
    """
    if not entries:
        return ""
    
    # Group by date
    by_date = {}
    for entry in entries:
        date = entry.get("timestamp", "")[:10]
        if date not in by_date:
            by_date[date] = []
        by_date[date].append(entry)
    
    lines = []
    for date in sorted(by_date.keys(), reverse=True)[:7]:  # Last 7 days only
        day_entries = by_date[date]
        
        # Count actions
        action_counts = {}
        for e in day_entries:
            action = e.get("action", "?")
            action_counts[action] = action_counts.get(action, 0) + 1
        
        # Format
        top_actions = sorted(action_counts.items(), key=lambda x: -x[1])[:4]
        action_str = ", ".join(f"{c}x{a}" for a, c in top_actions)
        
        lines.append(f"{date}: {len(day_entries)} wakes - {action_str}")
    
    if len(by_date) > 7:
        lines.append(f"...and {len(by_date) - 7} earlier days")
    
    return "\n".join(lines)


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
