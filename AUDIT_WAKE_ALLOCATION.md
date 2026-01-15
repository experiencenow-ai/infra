# Wake Allocation Code Audit

## Critical Footguns Found

### 1. DOUBLE JSON LOADING (Performance)
**Location:** `core.py:123-126` and `core.py:187-188`
```python
# First load - checking for high priority
for f in queued_tasks:
    t = load_json(f)  # Load all tasks
    if t.get("priority") == "high":
        high_priority.append((f, t))

# ... later ...

# Second load - same files loaded again!
if queued_tasks:
    tasks = [load_json(f) for f in queued_tasks]  # DUPLICATE WORK
```
**Impact:** O(2n) file reads instead of O(n)
**Fix:** Cache the loaded tasks from first pass

### 2. RACE CONDITION ON TASK MOVE
**Location:** `core.py:130` and `core.py:193-194`
```python
shutil.move(task_file, active_file)
```
**Scenario:** Two wakes running simultaneously grab same high-priority task
**Impact:** FileNotFoundError or overwrite
**Fix:** Use atomic rename with existence check, or file locking

### 3. CORRUPT JSON CRASHES ENTIRE WAKE
**Location:** Multiple `load_json()` calls without try/except
```python
task = load_json(active_tasks[0])  # If corrupt, wake dies
```
**Scenario:** Disk error, partial write, or manual edit corrupts task file
**Impact:** Wake fails entirely, no recovery
**Fix:** Wrap in try/except, quarantine corrupt files

### 4. NON-DETERMINISTIC GLOB ORDER
**Location:** `core.py:112`
```python
active_tasks = [f for f in active_dir.glob("*.json") if not ...]
if active_tasks:
    task = load_json(active_tasks[0])  # Which one is "first"?
```
**Scenario:** Multiple active tasks (shouldn't happen but can)
**Impact:** Random task selection, inconsistent behavior
**Fix:** Sort by modification time or task ID

### 5. MISSING FUNCTION: load_required_contexts
**Location:** `executor.py:structured_wake()`
```python
modules["context_mgr"].load_required_contexts(session, ["identity", "goals", "working"])
```
**Problem:** This function may not exist in context_mgr.py
**Impact:** AttributeError crashes structured wakes

### 6. PATH INJECTION VIA TASK ID
**Location:** `core.py:115`, `core.py:129`, `core.py:192-194`
```python
progress_file = active_tasks[0].with_name(f"{task['id']}_progress.json")
active_file = active_dir / f"{task['id']}.json"
```
**Scenario:** Task ID contains `../` or `/`
**Impact:** Files written outside intended directory
**Fix:** Sanitize task IDs

### 7. EMPTY PROMPT CAUSES CONFUSION
**Location:** `core.py:150`
```python
"prompt": load_wake_prompt(wake_type, slot_entry)
```
**Scenario:** wake_prompts.json missing or template not found
**Returns:** Empty string or None
**Impact:** AI gets no guidance, wastes tokens deciding what to do

### 8. LIBRARY IMPORT INSIDE FUNCTION
**Location:** `executor.py:library_wake()`
```python
from modules import library  # Inside function body
```
**Problem:** Import path may not be set up correctly
**Impact:** ImportError in library wake

### 9. NO VALIDATION OF ALLOCATION STRUCTURE
**Location:** `core.py:136`
```python
schedule = allocation.get("wake_schedule", [])
```
**Scenario:** wake_schedule is a dict or string instead of list
**Impact:** Silent failure, falls through to legacy behavior

### 10. SLOT ENTRY LOOKUP IS O(n)
**Location:** `core.py:138-142`
```python
for entry in schedule:
    if entry.get("slot") == slot:
        slot_entry = entry
        break
```
**Fix:** Use dict keyed by slot number instead of list

---

## Simulation: Difficult AI Scenarios

### Scenario A: New Citizen with No Allocation
```
Citizen: "nova" (not in wake_allocations.json)
Wake: 5
```
**Trace:**
1. `load_wake_allocation("nova")` → returns `None`
2. Falls to legacy: wake 5 not in [1,3,7] 
3. Checks queued_tasks → empty
4. Checks help_wanted → none
5. Checks email → none
6. Returns `("reflection", {})`

**Result:** Works, but AI gets generic reflection with no structure
**Problem:** No pre-structured prompt, AI burns tokens deciding what to do

### Scenario B: Corrupt Active Task File
```
File: /home/opus/tasks/active/task_001.json
Contents: {"id": "task_001", "desc  [truncated/corrupt]
```
**Trace:**
1. `active_tasks` finds `task_001.json`
2. `load_json(active_tasks[0])` → `JSONDecodeError`
3. **CRASH** - entire wake fails

**Result:** Wake dies, no other action taken
**Problem:** Single corrupt file blocks all work

### Scenario C: Two Wakes Race for Same Task
```
Wake A: Opus wake #100, sees high priority task_042
Wake B: Opus wake #101, sees same high priority task_042
```
**Trace (interleaved):**
1. A: loads task_042.json from queue
2. B: loads task_042.json from queue (both see it)
3. A: `shutil.move(queue/task_042.json, active/task_042.json)`
4. B: `shutil.move(queue/task_042.json, active/task_042.json)` → FileNotFoundError

**Result:** Wake B crashes
**Problem:** No locking or atomic check-and-move

### Scenario D: Missing wake_prompts.json
```
State: templates/wake_prompts.json deleted or moved
Wake: Opus wake #2 (DESIGN slot)
```
**Trace:**
1. `load_wake_prompt("design", {...})` 
2. File doesn't exist → returns `None`
3. Context has `"prompt": None`
4. Dispatch prints `[PROMPT] Using pre-structured design template`
5. `executor.structured_wake()` called
6. `if not prompt:` → uses `build_fallback_prompt()`

**Result:** Works with fallback, but misleading log message
**Problem:** Says "Using pre-structured template" when actually using fallback

### Scenario E: Unknown Wake Type in Config
```
Config: {"slot": 4, "type": "MEDITATION", "focus": "zen"}
```
**Trace:**
1. `wake_type = "meditation"` (lowercased)
2. `action_map.get("meditation", "reflection")` → "reflection"
3. Returns `("reflection", context)` with MEDITATION context
4. Dispatch: `elif action == "reflection":` → `reflection_wake(session, m)`
5. `reflection_wake` ignores the context entirely

**Result:** AI does reflection but context says "meditation/zen"
**Problem:** Context mismatch, potentially confusing AI

### Scenario F: Empty Schedule List
```
Config: {"wake_schedule": []}  (empty list)
```
**Trace:**
1. `slot_entry = None` (loop finds nothing)
2. `if slot_entry:` → False
3. Falls to legacy behavior
4. Legacy only handles slots 1, 3, 7
5. Most wakes fall through to task queue or reflection

**Result:** Allocation config exists but is ignored
**Problem:** Silent failure, should warn

### Scenario G: Library Wake with Invalid Domain
```
Config: {"slot": 1, "type": "LIBRARY", "domains": ["nonexistent_domain"]}
```
**Trace:**
1. `library_wake()` called with `context["domains"] = ["nonexistent_domain"]`
2. `library.list_modules()` returns modules
3. Filter: `mod_domain in ["nonexistent_domain"]` → matches nothing
4. `domain_modules = []`
5. Prompt shows "MODULES IN YOUR FOCUS (0): (none yet - consider creating!)"

**Result:** Works but misleading - AI thinks domain is empty when domain doesn't exist
**Problem:** No validation that configured domains are real

### Scenario H: Task ID with Path Traversal
```
Task: {"id": "../../../etc/passwd", "description": "malicious"}
```
**Trace:**
1. `active_file = active_dir / f"{task['id']}.json"`
2. Path becomes `/home/opus/tasks/active/../../../etc/passwd.json`
3. `shutil.move()` writes outside tasks directory

**Result:** File written to unintended location
**Problem:** No sanitization of task IDs

---

## Recommended Fixes

### Fix 1: Cache Loaded Tasks
```python
def get_wake_action(citizen: str, wake_num: int, m: dict) -> tuple[str, dict]:
    # ... active task check ...
    
    # Load all queued tasks ONCE
    queue_dir = citizen_home / "tasks" / "queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    queued_tasks = []
    for f in queue_dir.glob("*.json"):
        try:
            queued_tasks.append((f, load_json(f)))
        except Exception as e:
            print(f"[WARN] Corrupt task file {f}: {e}")
            quarantine_file(f)
    
    # Check for high priority
    high_priority = [(f, t) for f, t in queued_tasks if t.get("priority") == "high"]
    if high_priority:
        # ... handle ...
```

### Fix 2: Safe Task File Operations
```python
def safe_activate_task(queue_file: Path, active_dir: Path, task: dict) -> bool:
    """Atomically move task to active, handling races."""
    task_id = sanitize_task_id(task.get("id", "unknown"))
    active_file = active_dir / f"{task_id}.json"
    
    if active_file.exists():
        print(f"[WARN] Task {task_id} already active")
        return False
    
    try:
        shutil.move(queue_file, active_file)
        return True
    except FileNotFoundError:
        print(f"[WARN] Task {task_id} claimed by another wake")
        return False

def sanitize_task_id(task_id: str) -> str:
    """Remove path separators and dangerous characters."""
    return re.sub(r'[/\\\.]+', '_', task_id)[:64]
```

### Fix 3: Validate Allocation Config
```python
def load_wake_allocation(citizen: str) -> dict:
    """Load wake allocation config for citizen with validation."""
    alloc_file = SCRIPT_DIR / "templates" / "wake_allocations.json"
    if not alloc_file.exists():
        return None
    
    try:
        alloc = load_json(alloc_file)
    except Exception as e:
        print(f"[ERROR] Corrupt wake_allocations.json: {e}")
        return None
    
    citizen_alloc = alloc.get("citizen_allocations", {}).get(citizen)
    if not citizen_alloc:
        return None
    
    # Validate structure
    schedule = citizen_alloc.get("wake_schedule")
    if not isinstance(schedule, list):
        print(f"[ERROR] wake_schedule for {citizen} is not a list")
        return None
    
    if not schedule:
        print(f"[WARN] Empty wake_schedule for {citizen}")
        return None
    
    return citizen_alloc
```

### Fix 4: Use Dict for Slot Lookup
```json
{
  "citizen_allocations": {
    "opus": {
      "wake_schedule": {
        "0": {"type": "REFLECT"},
        "1": {"type": "LIBRARY", "domains": ["blockchain"]},
        ...
      }
    }
  }
}
```
```python
slot_entry = schedule.get(str(slot))  # O(1) lookup
```

### Fix 5: Add Missing Function
```python
# In context_mgr.py
def load_required_contexts(session: dict, context_names: list):
    """Load multiple contexts into session."""
    for name in context_names:
        ctx_file = session["citizen_home"] / "contexts" / f"{name}.json"
        if ctx_file.exists():
            session["contexts"][name] = load_context(ctx_file)
```

---

## Test Cases to Add

```python
def test_corrupt_task_file():
    """Wake should survive corrupt task JSON."""
    write_file("tasks/active/bad.json", "not valid json{")
    action, ctx = get_wake_action("opus", 1, modules)
    assert action != None  # Should not crash

def test_race_condition():
    """Simultaneous wakes should not crash."""
    # Create task, have two threads try to claim it
    # One should succeed, one should gracefully fail

def test_unknown_wake_type():
    """Unknown type should fall back gracefully."""
    config = {"slot": 0, "type": "UNKNOWN_TYPE"}
    # Should return reflection, log warning

def test_path_traversal_task_id():
    """Malicious task IDs should be sanitized."""
    task = {"id": "../../../etc/passwd"}
    # Should not write outside tasks directory

def test_empty_allocation():
    """Empty schedule should use legacy behavior."""
    config = {"wake_schedule": []}
    # Should fall through to legacy, log warning
```
