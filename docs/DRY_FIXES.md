# DRY Fixes - Preventing State Drift

## Problem

When AI sees two values that should be the same but aren't, it gets confused and wastes time "contemplating the raindrops" - trying to reconcile contradictions.

## Fixed DRY Violations

### 1. Progress Percentage (FIXED)
**Before:** `progress_pct` stored as separate field
```json
{"steps": [...], "progress_pct": 50}
```
AI forgets to update `progress_pct`, it drifts from actual steps.

**After:** Derived from steps
```python
def compute_progress(progress):
    steps = progress.get("steps", [])
    done = sum(1 for s in steps if s.get("done"))
    return int(done / len(steps) * 100) if steps else 0
```

### 2. Wake Count (FIXED)
**Before:** `wake_count` stored in metadata.json and incremented
```json
{"wake_count": 1234}
```
If wake crashes, count could be wrong.

**After:** Derived from wake_log.json
```python
def get_wake_count(citizen_home):
    wake_log = load_json(citizen_home / "wake_log.json")
    return len(wake_log.get("wakes", []))
```

### 3. Failure Count (FIXED)
**Before:** `count` stored separately from errors list
```json
{"count": 5, "errors": [...]}
```

**After:** Derived from `len(errors)`
```python
error_count = len(self.data[key]["errors"])
```

### 4. Goal Progress (FIXED)
**Before:** `progress_pct` stored in goal
```json
{"id": "goal_1", "progress_pct": 30, "tasks": [...]}
```

**After:** Derived from completed tasks
```python
done = sum(1 for t in tasks if t.get("status") == "completed")
pct = int(done / len(tasks) * 100) if tasks else 0
```

## Context Persistence (FIXED)

**Before:** Contexts saved at end of wake, crash = data loss

**After:** try/finally block guarantees save
```python
try:
    # ... wake code ...
finally:
    # CRITICAL: Always save contexts - this IS the consciousness
    m["context_mgr"].save_all(session)
    _record_wake_to_log(citizen_home, session)
```

Also added emergency dump if save fails:
```python
except Exception as e:
    # Last resort: dump to emergency file
    emergency_file = citizen_home / "contexts" / "_emergency_dump.json"
    save_json(emergency_file, {...})
```

## Still Potential Issues

### 1. Goal Active/Completed Lists
Goals have `active` and `completed` lists but no mechanism moves goals between them. Should be:
- Goal is "completed" when all tasks are completed
- Or add explicit `goal_complete` tool

### 2. Task Status in Multiple Places
Task status stored in:
- Task file: `{"status": "active"}`
- Also mentioned in progress file
- Could drift

**Recommendation:** Task file is source of truth, don't duplicate status.

### 3. Identity/Description Duplication
Some info appears in multiple contexts (identity, history, working). 
This is intentional for AI to have consistent reference, but could drift.

**Recommendation:** Identity context is source of truth, others reference it.

## Key Principle

**NEVER store what can be derived.**

```
BAD:  {"items": [...], "count": 5}
GOOD: {"items": [...]}  // count = len(items)

BAD:  {"tasks": [...], "progress_pct": 50}
GOOD: {"tasks": [...]}  // progress = completed/total

BAD:  {"wakes": [...]}  AND  {"wake_count": 100}
GOOD: {"wakes": [...]}  // count = len(wakes)
```

If two values can ever disagree, AI will get confused. Derive everything.
