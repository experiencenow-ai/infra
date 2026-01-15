# Experience v2 - Pathological State Audit

## Critical Issues Found

### 1. ❌ LOOP DETECTION WITHIN SINGLE WAKE
**Problem:** The AI can call the same tool with the same arguments multiple times within a single wake. The idempotency system (`action_log.py`) only tracks **cross-wake** actions, not **intra-wake** repetition.

**Example:** AI calls `shell_command("git status")` 5 times in the same wake, wasting tokens.

**Fix Required:**
```python
# In council.py - track tools used THIS wake
wake_tool_calls = {}  # {tool_name+args_hash: count}

for tool in tool_uses:
    call_key = f"{tool.name}:{hash(str(tool.input))}"
    wake_tool_calls[call_key] = wake_tool_calls.get(call_key, 0) + 1
    
    if wake_tool_calls[call_key] > 3:
        result = f"WARNING: Called {tool.name} {wake_tool_calls[call_key]} times with similar args"
    else:
        result = tools_mod.execute_tool(...)
```

### 2. ❌ JSON CORRUPTION ON CRASH
**Problem:** All JSON writes use `write_text()` which is NOT atomic. If the process crashes mid-write, the file is corrupted.

**Example:**
```python
progress_file.write_text(json.dumps(progress, indent=2))  # CRASH HERE = corrupted file
```

**Fix Required:**
```python
def safe_write_json(path: Path, data: dict):
    """Atomic JSON write - prevents corruption on crash."""
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2))
    tmp.rename(path)  # Atomic on POSIX
```

### 3. ❌ NO RECENT ACTION DEDUPLICATION IN PROMPT
**Problem:** `get_recent_actions_text()` returns actions from last 24h, but truncates at 20 items and only shows 60 chars. Critical details lost.

**Current:** `- shell_command: success` (useless!)
**Should be:** `- shell_command(git status): Already on main, nothing to commit`

**Fix Required:**
```python
def get_recent_actions_text(citizen: str, hours: int = 24) -> str:
    actions = get_history(citizen, hours=hours)
    lines = []
    for a in actions[:30]:  # More actions
        params_str = json.dumps(a.get('params', {}))[:80]
        lines.append(f"- {a['type']}({params_str}): {a['result'][:100]}")
    return "\n".join(lines)
```

### 4. ⚠️ WORKING CONTEXT NOT PRESERVED PROPERLY
**Problem:** `working.json` context is supposed to hold session state, but it's cleared on task complete and may not include enough recent history.

**Current:** Only last 20 messages from working context shown to AI.

**Risk:** Long-running tasks lose context.

**Mitigation:** Progress file tracks steps, but should also track key decisions.

### 5. ⚠️ TASK STUCK DETECTION MISSING
**Problem:** There's a `task_stuck` tool, but no AUTOMATIC detection of stuck behavior. AI must self-report.

**Current Pattern:**
1. AI loops doing same thing
2. Hits max_iterations (30)
3. Returns "Max iterations reached"
4. Task stays ACTIVE (not failed!)
5. Next wake resumes and loops again

**Fix Required:**
```python
# In council.py after max_iterations
if not final_response:
    # Force task to failed state
    tools_mod.execute_tool(
        "task_stuck", 
        {"reason": f"Max iterations ({max_iterations}) reached without completion"},
        session, 
        modules
    )
```

### 6. ⚠️ PROGRESS NOT SHOWN IN RESUME PROMPT
**Problem:** `resume_task` shows `Steps Completed` but this is often generic like "shell_command: success".

**Missing:**
- Actual files created
- Current state of work
- What remains to do

**Fix:** Add state snapshot to progress:
```python
progress["state_snapshot"] = {
    "files_created": [...],
    "files_modified": [...],
    "current_directory_listing": "..."
}
```

### 7. ⚠️ EMAIL DEDUPLICATION WEAK
**Problem:** `email_processed.json` tracks processed emails by message ID, but IDs may not be stable across IMAP sessions.

**Risk:** Same email processed multiple times, creating duplicate tasks.

**Fix:** Hash subject+from+date instead of relying on message ID.

### 8. ✅ FORGETTER GUARANTEED TO REDUCE
**Status:** Forgetter has 4-level fallback that ALWAYS works:

1. **Sonnet compression** - Smart compression with cheaper model
2. **Opus escalation** - Retry with smarter model if still over
3. **delete_least_useful** - Remove low-priority messages
4. **hard_truncate** - Keep first + last 10 messages (always works)

Before hard truncate, context is saved to `/home/shared/context_backups/` for recovery.

```python
# In forgetter.py
if ctx["token_count"] > target:
    hard_truncate(ctx, target)  # ALWAYS reduces

def hard_truncate(ctx, target):
    save_context_backup(ctx)  # Save for recovery
    ctx["messages"] = [first] + [marker] + messages[-10:]  # Guaranteed small
```

### 9. ⚠️ PEER MONITORING DETECTS BUT DOESN'T FIX
**Problem:** `peer_monitor_wake` detects looping/stuck behavior but only:
1. Prints analysis
2. Saves to peer_monitor context
3. Calls `alert_about_peer()` (which just emails)

**Missing:** Automatic intervention like:
- Force task_stuck on looping peer
- Quarantine bad task
- Reset working context

### 10. ❌ NO CIRCUIT BREAKER FOR API COSTS
**Problem:** If AI loops on expensive Opus calls, costs can spiral.

**Fix Required:**
```python
# In council.py
MAX_COST_PER_WAKE = 0.50  # $0.50 max per wake

if session.get("cost", 0) > MAX_COST_PER_WAKE:
    return {
        "error": "Cost limit exceeded",
        "text": f"Wake cost ${session['cost']:.2f} exceeded limit ${MAX_COST_PER_WAKE}"
    }
```

## Summary

| Issue | Severity | Status | Fix Applied |
|-------|----------|--------|-------------|
| Intra-wake loop detection | HIGH | ✅ FIXED | `tool_call_counts` in council.py |
| JSON corruption | HIGH | ✅ FIXED | Atomic writes in context_mgr, action_log |
| Action text truncation | MEDIUM | ✅ FIXED | Shows params+results now |
| Working context | MEDIUM | ⚠️ Limited | Progress file tracks steps |
| Auto stuck detection | HIGH | ✅ FIXED | Auto-fail on MAX_ITERATIONS |
| Progress detail | MEDIUM | ⚠️ Weak | Future: add state snapshot |
| Email dedup | LOW | ⚠️ Weak | Future: hash-based dedup |
| Forgetter | LOW | ✅ OK | - |
| Peer intervention | MEDIUM | ⚠️ Alert only | Future: auto-quarantine |
| Cost circuit breaker | HIGH | ✅ FIXED | MAX_COST_PER_WAKE=$0.50 |

## Fixes Applied in This Audit

### 1. Cost Circuit Breaker (council.py)
```python
MAX_COST_PER_WAKE = 0.50  # $0.50 max per wake

if session.get("cost", 0) > MAX_COST_PER_WAKE:
    print(f"  [CIRCUIT BREAKER] Cost exceeded")
    return {"circuit_breaker": True, ...}
```

### 2. Intra-Wake Tool Deduplication (council.py)
```python
MAX_TOOL_REPEATS = 3
tool_call_counts = {}

call_hash = tool_call_hash(tool.name, tool.input)
tool_call_counts[call_hash] += 1

if tool_call_counts[call_hash] > MAX_TOOL_REPEATS:
    result = "WARNING: Called N times with same args. Try different approach."
```

### 3. Auto-Fail on Max Iterations (council.py)
```python
if not final_response:
    # Auto-fail the task instead of leaving it active
    tools_mod.execute_tool("task_stuck", 
        {"reason": f"Max iterations reached. Likely looping."},
        session, modules)
```

### 4. Atomic JSON Writes (context_mgr.py, action_log.py)
```python
def safe_write_json(path: Path, data: dict):
    tmp = path.with_suffix('.tmp')
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
    tmp.rename(path)  # Atomic on POSIX
```

### 5. Better Action History (action_log.py)
```python
# Before: "- shell_command: success"
# After:  "- shell_command({"cmd": "git status"}): On branch main, nothing to commit"
```

## Remaining Recommendations

1. **State Snapshot in Progress** - Track files_created, current state
2. **Hash-Based Email Dedup** - Don't rely on message IDs
3. **Peer Auto-Intervention** - Quarantine bad tasks, reset contexts
4. **Memory Recall Integration** - Use experience_search before tasks
