"""
Forgetter - Smart context compression.

This is the hardest part of the system. It must:
1. Compress without losing essential information
2. Know what's important vs redundant
3. Always get context under 85% when triggered at 90%
4. NEVER delete identity statements

Uses Opus model for forgetting decisions - this is judgment work.
"""

import json
import os
import anthropic
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from .time_utils import now_iso

# Model selection for forgetting
# Sonnet for normal compression (cost effective, follows instructions well)
# Opus only for escalation (when first pass fails or for identity context)
FORGET_MODEL_DEFAULT = "claude-sonnet-4-5-20250929"
FORGET_MODEL_ESCALATE = "claude-opus-4-5-20251101"

COSTS = {
    "claude-opus-4-5-20251101": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-5-20250929": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.25, "output": 1.25}
}



def get_client():
    """Get Anthropic client."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return anthropic.Anthropic(api_key=api_key)

def maybe_forget(ctx: dict, config: dict, session: dict):
    """
    Check if context needs forgetting, trigger if so.
    
    Trigger: > 90% full
    Target: < 85% full
    """
    token_count = ctx.get("token_count", 0)
    max_tokens = ctx.get("max_tokens", 10000)
    
    # Get limits from config if available
    ctx_type = ctx.get("context_type", ctx.get("id", "unknown"))
    ctx_config = config.get("context_limits", {}).get(ctx_type, {})
    if ctx_config:
        max_tokens = ctx_config.get("max_tokens", max_tokens)
        ctx["max_tokens"] = max_tokens
    
    threshold = max_tokens * 0.90
    
    if token_count < threshold:
        return  # Not needed
    
    print(f"[FORGET] {ctx_type} at {token_count}/{max_tokens} ({token_count/max_tokens*100:.1f}%)")
    
    strategy = ctx_config.get("forget_strategy", "compress_oldest")
    
    if strategy == "never":
        # Don't forget, but warn
        print(f"[WARN] {ctx_type} context approaching limit but strategy is 'never'")
        return
    
    if strategy == "clear_on_task_complete":
        # Working context - will be cleared when task completes
        print(f"[INFO] {ctx_type} will clear on task complete")
        return
    
    # Perform forgetting
    force_forget(ctx, config, session)

def force_forget(ctx: dict, config: dict, session: dict):
    """Force forgetting on a context. Uses Sonnet first, escalates to Opus if needed."""
    ctx_type = ctx.get("context_type", ctx.get("id", "unknown"))
    ctx_config = config.get("context_limits", {}).get(ctx_type, {})
    strategy = ctx_config.get("forget_strategy", "compress_oldest")
    
    max_tokens = ctx.get("max_tokens", 10000)
    target = int(max_tokens * 0.85)
    current = ctx.get("token_count", 0)
    need_to_free = current - target
    
    if need_to_free <= 0:
        return
    
    print(f"[FORGET] {ctx_type}: {current:,} → target {target:,} (free {need_to_free:,})")
    
    # First pass with Sonnet (cost effective)
    if strategy == "compress_oldest":
        compress_oldest(ctx, target, session, escalate=False)
    elif strategy == "archive_completed":
        archive_completed(ctx, target, session, escalate=False)
    elif strategy == "keep_recent_n":
        n = ctx_config.get("n", 20)
        keep_recent_n(ctx, n, session, escalate=False)
    elif strategy == "compress":
        compress_all(ctx, target, session, escalate=False)
    else:
        compress_oldest(ctx, target, session, escalate=False)
    
    # Check if we're under target
    if ctx.get("token_count", 0) <= target:
        log_forget(ctx_type, current, ctx.get("token_count", 0), strategy, session)
        return
    
    # Still over - escalate to Opus for second pass
    print(f"[FORGET] {ctx_type}: Still at {ctx.get('token_count', 0):,}, escalating to Opus")
    
    if strategy in ["compress_oldest", "compress", "archive_completed"]:
        compress_oldest(ctx, target, session, escalate=True)
    elif strategy == "keep_recent_n":
        n = ctx_config.get("n", 20)
        keep_recent_n(ctx, n, session, escalate=True)
    
    # If STILL over, use fallback deletion
    if ctx.get("token_count", 0) > target:
        delete_least_useful(ctx, target, session)
    
    # Log the forget action
    log_forget(ctx_type, current, ctx.get("token_count", 0), strategy, session)

def compress_oldest(ctx: dict, target: int, session: dict, escalate: bool = False):
    """Compress oldest messages while preserving facts."""
    messages = ctx.get("messages", [])
    
    if len(messages) < 4:
        return  # Not enough to compress
    
    # FIRST: Deduplicate files - keep only latest instance
    dedup_count = deduplicate_file_content(ctx)
    if dedup_count > 0:
        print(f"[DEDUP] Removed {dedup_count} duplicate file instances before compression")
        if ctx.get("token_count", 0) <= target:
            return
        messages = ctx.get("messages", [])  # Refresh after dedup
    
    # SECOND: Deduplicate identical content
    content_dedup = deduplicate_identical_content(ctx)
    if content_dedup > 0:
        if ctx.get("token_count", 0) <= target:
            return
        messages = ctx.get("messages", [])
    
    # Keep system prompt and recent messages
    system_msgs = [m for m in messages if m.get("role") == "system"]
    other_msgs = [m for m in messages if m.get("role") != "system"]
    
    if len(other_msgs) < 6:
        return
    
    # Take oldest half for compression
    mid = len(other_msgs) // 2
    old_msgs = other_msgs[:mid]
    recent_msgs = other_msgs[mid:]
    
    # Ask model to compress
    compressed = ask_model_to_compress(old_msgs, ctx.get("context_type", ""), session, escalate=escalate)
    
    if compressed:
        # Replace old messages with compressed summary
        ctx["messages"] = system_msgs + [
            {"role": "system", "content": f"[COMPRESSED HISTORY]\n{compressed}"}
        ] + recent_msgs
        
        # Recalculate tokens
        ctx["token_count"] = count_context_tokens(ctx)

def archive_completed(ctx: dict, target: int, session: dict, escalate: bool = False):
    """Move completed items to history context."""
    # For goals context - archive completed goals
    structured = ctx.get("structured", {})
    completed = structured.get("completed", [])
    
    if not completed:
        # Nothing to archive, fall back to compression
        compress_oldest(ctx, target, session, escalate=escalate)
        return
    
    # Move completed to history
    history_ctx = session.get("contexts", {}).get("history")
    if history_ctx:
        for item in completed:
            summary = f"[COMPLETED GOAL] {item.get('id', '?')}: {item.get('description', '')[:100]}"
            history_ctx["messages"].append({"role": "system", "content": summary})
    
    # Clear completed from this context
    structured["completed"] = []
    ctx["structured"] = structured
    
    # Also compress old messages
    compress_oldest(ctx, target, session, escalate=escalate)

def keep_recent_n(ctx: dict, n: int, session: dict, escalate: bool = False):
    """Keep only the N most recent entries."""
    messages = ctx.get("messages", [])
    
    # Separate system messages
    system_msgs = [m for m in messages if m.get("role") == "system"]
    other_msgs = [m for m in messages if m.get("role") != "system"]
    
    if len(other_msgs) <= n:
        return
    
    # Ask model to summarize what we're dropping
    dropping = other_msgs[:-n]
    summary = ask_model_to_compress(dropping, ctx.get("context_type", ""), session, escalate=escalate)
    
    # Keep only recent N plus summary
    ctx["messages"] = system_msgs + [
        {"role": "system", "content": f"[ARCHIVED: {len(dropping)} entries]\n{summary}"}
    ] + other_msgs[-n:]
    
    ctx["token_count"] = count_context_tokens(ctx)

def compress_all(ctx: dict, target: int, session: dict, escalate: bool = False):
    """Compress entire context, preserving key facts."""
    messages = ctx.get("messages", [])
    
    if len(messages) < 2:
        return
    
    # Ask model to compress everything
    compressed = ask_model_to_compress(messages, ctx.get("context_type", ""), session, escalate=escalate)
    
    if compressed:
        ctx["messages"] = [
            {"role": "system", "content": f"[COMPRESSED]\n{compressed}"}
        ]
        ctx["token_count"] = count_context_tokens(ctx)

def delete_least_useful(ctx: dict, target: int, session: dict):
    """
    Fallback: Delete least useful content.
    
    This always works - we can always delete something.
    """
    ctx_type = ctx.get("context_type", "")
    
    # Never delete from identity
    if ctx_type == "identity":
        print(f"[WARN] Cannot delete from identity context!")
        return
    
    messages = ctx.get("messages", [])
    
    if len(messages) < 2:
        return
    
    # FIRST: Deduplicate files - keep only latest instance of each file
    dedup_count = deduplicate_file_content(ctx)
    if dedup_count > 0:
        print(f"[DEDUP] Removed {dedup_count} duplicate file instances")
        if ctx.get("token_count", 0) <= target:
            return
    
    # Rank messages by importance (lower = less important)
    ranked = []
    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        content = msg.get("content", "")
        
        # System messages are important
        if role == "system":
            score = 100
        # Recent messages are important
        elif i > len(messages) - 5:
            score = 80
        # User messages slightly more important than assistant
        elif role == "user":
            score = 50
        else:
            score = 40
        
        # Verbose tool output is less important
        if len(content) > 2000:
            score -= 20
        
        # Compressed markers are important
        if "[COMPRESSED" in content:
            score += 30
        
        ranked.append((i, score, msg))
    
    # Sort by score, delete lowest
    ranked.sort(key=lambda x: x[1])
    
    # Delete until under target
    to_delete = set()
    current = ctx.get("token_count", 0)
    
    for i, score, msg in ranked:
        if current <= target:
            break
        if score >= 90:  # Don't delete high importance
            continue
        
        content = msg.get("content", "")
        msg_tokens = len(content) // 4  # Rough estimate
        to_delete.add(i)
        current -= msg_tokens
        print(f"[DELETE] Message {i} (score {score}): {content[:50]}...")
    
    # Apply deletions
    ctx["messages"] = [m for i, m in enumerate(messages) if i not in to_delete]
    ctx["token_count"] = count_context_tokens(ctx)
    
    # FINAL FALLBACK: If still over target, hard truncate
    if ctx["token_count"] > target:
        hard_truncate(ctx, target)


def deduplicate_file_content(ctx: dict) -> int:
    """
    Remove duplicate file content, keeping only the latest instance.
    
    When the same file is read/shown multiple times during iteration,
    we only need the latest version.
    
    Returns number of duplicates removed.
    """
    messages = ctx.get("messages", [])
    if len(messages) < 2:
        return 0
    
    # Track seen files (from latest to earliest)
    seen_files = set()
    to_remove = set()
    
    # Patterns that indicate file content
    file_patterns = [
        r"FILE: (/[^\n]+)",                    # FILE: /path/to/file
        r"Contents of (/[^\n]+):",             # Contents of /path:
        r"```\w*\n// (/[^\n]+)",               # Code block with path comment
        r"read_file\(['\"]([^'\"]+)",          # read_file('/path')
        r"write_file\(['\"]([^'\"]+)",         # write_file('/path')
        r"str_replace_file\(['\"]([^'\"]+)",   # str_replace_file('/path')
    ]
    
    import re
    
    # Process in reverse (newest first)
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        content = msg.get("content", "")
        
        # Find file paths in this message
        for pattern in file_patterns:
            matches = re.findall(pattern, content)
            for filepath in matches:
                filepath = filepath.strip()
                if filepath in seen_files:
                    # This is an older duplicate
                    to_remove.add(i)
                    break
                else:
                    seen_files.add(filepath)
    
    # Remove duplicates
    if to_remove:
        ctx["messages"] = [m for i, m in enumerate(messages) if i not in to_remove]
        ctx["token_count"] = count_context_tokens(ctx)
    
    return len(to_remove)


def deduplicate_identical_content(ctx: dict, min_length: int = 200) -> int:
    """
    Remove messages with identical or near-identical content.
    
    Keeps the LATEST instance of duplicated content.
    Only considers content longer than min_length (short messages often legitimately repeat).
    
    Returns number of duplicates removed.
    """
    import hashlib
    
    messages = ctx.get("messages", [])
    if len(messages) < 2:
        return 0
    
    # Track content hashes (from latest to earliest)
    seen_hashes = {}  # hash -> index of first (latest) occurrence
    to_remove = set()
    
    # Process in reverse (newest first)
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        content = msg.get("content", "")
        
        # Skip short messages (often legitimately repeat like "OK" or "Done")
        if len(content) < min_length:
            continue
        
        # Normalize content for comparison (strip whitespace, lowercase)
        normalized = " ".join(content.lower().split())
        content_hash = hashlib.md5(normalized.encode()).hexdigest()
        
        if content_hash in seen_hashes:
            # This is an older duplicate - mark for removal
            to_remove.add(i)
        else:
            seen_hashes[content_hash] = i
    
    # Also check for near-duplicates (same first 500 chars)
    seen_prefixes = {}
    for i in range(len(messages) - 1, -1, -1):
        if i in to_remove:
            continue
            
        msg = messages[i]
        content = msg.get("content", "")
        
        if len(content) < min_length:
            continue
        
        prefix = " ".join(content[:500].lower().split())
        
        if prefix in seen_prefixes:
            # Near-duplicate - likely same content with minor changes
            to_remove.add(i)
        else:
            seen_prefixes[prefix] = i
    
    if to_remove:
        ctx["messages"] = [m for i, m in enumerate(messages) if i not in to_remove]
        ctx["token_count"] = count_context_tokens(ctx)
        print(f"[DEDUP-CONTENT] Removed {len(to_remove)} identical/near-identical messages")
    
    return len(to_remove)


def hard_truncate(ctx: dict, target: int):
    """
    Guaranteed fallback - always works by hard truncation.
    Keeps first message (usually system) and most recent N messages.
    """
    messages = ctx.get("messages", [])
    if len(messages) <= 2:
        return
    
    print(f"[HARD TRUNCATE] Forced truncation to reach target {target}")
    
    # Save context before truncation for recovery
    save_context_backup(ctx)
    
    # Keep first (system) and most recent messages
    first_msg = messages[0] if messages else None
    recent_msgs = messages[-10:]  # Keep last 10
    
    # Add truncation marker
    marker = {
        "role": "system",
        "content": f"[TRUNCATED {now_iso()}] Earlier content removed to free memory. {len(messages) - 11} messages dropped."
    }
    
    if first_msg:
        ctx["messages"] = [first_msg, marker] + recent_msgs
    else:
        ctx["messages"] = [marker] + recent_msgs
    
    ctx["token_count"] = count_context_tokens(ctx)
    print(f"[HARD TRUNCATE] Reduced to {ctx['token_count']} tokens")


def save_context_backup(ctx: dict):
    """Save context to backup file for potential recovery."""
    ctx_id = ctx.get("id", "unknown")
    backup_dir = Path("/home/shared/context_backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    backup_file = backup_dir / f"{ctx_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    # Only save messages, not internal fields
    save_data = {
        "id": ctx_id,
        "context_type": ctx.get("context_type"),
        "backed_up": now_iso(),
        "token_count": ctx.get("token_count", 0),
        "messages": ctx.get("messages", [])
    }
    
    backup_file.write_text(json.dumps(save_data, indent=2))
    print(f"[BACKUP] Saved {ctx_id} to {backup_file.name}")
    
    # Keep only last 10 backups per context
    backups = sorted(backup_dir.glob(f"{ctx_id}_*.json"))
    for old in backups[:-10]:
        old.unlink()


def restore_context_backup(ctx_id: str, backup_name: str = None) -> Optional[dict]:
    """Restore context from backup."""
    backup_dir = Path("/home/shared/context_backups")
    
    if backup_name:
        backup_file = backup_dir / backup_name
    else:
        # Get most recent
        backups = sorted(backup_dir.glob(f"{ctx_id}_*.json"))
        if not backups:
            return None
        backup_file = backups[-1]
    
    if backup_file.exists():
        return json.loads(backup_file.read_text())
    return None

def ask_model_to_compress(messages: list, ctx_type: str, session: dict, escalate: bool = False) -> Optional[str]:
    """
    Ask model to compress messages.
    
    Uses Sonnet by default (cost effective).
    Uses Opus only if escalate=True (for retries or identity context).
    
    Returns compressed text or None on failure.
    """
    if not messages:
        return None
    
    # Model selection
    if escalate or ctx_type == "identity":
        model = FORGET_MODEL_ESCALATE
    else:
        model = FORGET_MODEL_DEFAULT
    
    # Format messages for compression
    content = "\n".join([
        f"[{m.get('role', '?')}] {m.get('content', '')}"
        for m in messages
    ])
    
    prompt = f"""You are compressing a {ctx_type} context to save space.

CONTENT TO COMPRESS:
{content}

REQUIREMENTS:
1. Preserve ALL facts, dates, names, numbers, and outcomes
2. Preserve cause-effect relationships
3. Remove redundancy, verbose tool output, and conversational filler
4. Use concise language - bullet points are fine
5. Output should be MUCH shorter than input (target: 30-50% of original)

Compress this to a concise summary that preserves all essential information:"""

    try:
        client = get_client()
        response = client.messages.create(
            model=model,
            max_tokens=2000,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Track costs
        costs = COSTS.get(model, COSTS[FORGET_MODEL_DEFAULT])
        session["tokens_used"] = session.get("tokens_used", 0) + \
            response.usage.input_tokens + response.usage.output_tokens
        session["cost"] = session.get("cost", 0) + \
            (response.usage.input_tokens * costs["input"] + 
             response.usage.output_tokens * costs["output"]) / 1_000_000
        
        return response.content[0].text
        
    except Exception as e:
        print(f"[ERROR] Compression failed: {e}")
        return None

def count_context_tokens(ctx: dict) -> int:
    """Count tokens in context."""
    total = 0
    for msg in ctx.get("messages", []):
        content = msg.get("content", "")
        if isinstance(content, str):
            total += len(content) // 4
    return total

def log_forget(ctx_type: str, before: int, after: int, strategy: str, session: dict):
    """Log forget action."""
    action = {
        "timestamp": now_iso(),
        "context": ctx_type,
        "before_tokens": before,
        "after_tokens": after,
        "freed": before - after,
        "strategy": strategy
    }
    session["actions"] = session.get("actions", [])
    session["actions"].append({"type": "forget", "details": action})
    print(f"[FORGET] {ctx_type}: {before:,} → {after:,} (freed {before-after:,})")
