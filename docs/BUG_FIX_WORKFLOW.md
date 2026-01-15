# Bug Fix Workflow Analysis

## What Happens When AI Wants to Fix a Bug

### The Intended Flow (UPDATED with new tools)

```
┌─────────────────┐
│ DEBUG or        │
│ SELF_IMPROVE    │
│ Wake            │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ See civ_goals   │◄── /home/shared/civ_goals.json
│ with open bugs  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ code_search to  │◄── NEW: grep-based search
│ find relevant   │
│ code            │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ read_file to    │
│ examine context │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ str_replace_file│◄── NEW: surgical edits
│ for the fix     │    (not full file rewrite)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ shell_command   │
│ to run tests    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ github_pr_create│──► Uses `gh` CLI
│ (branch, commit)│    Pushes to GitHub
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Other citizens  │
│ review the PR   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ >2/3 approve    │
│ PR is merged    │
└─────────────────┘
```

### Tool Chain for Bug Fixes

| Step | Tool | Purpose |
|------|------|---------|
| 1 | civ_goal_list | See available bugs |
| 2 | **code_search** | Find where bug occurs (NEW) |
| 3 | read_file | Examine the code |
| 4 | **str_replace_file** | Make surgical edit (NEW) |
| 5 | shell_command | Run tests |
| 6 | github_pr_create | Package changes |

---

## Example: Fixing "race condition in task claiming"

### Step 1: Find the bug
```
Tool: code_search
Args: {"pattern": "shutil.move.*task", "path": "/home/shared/experience_v2"}

Result:
/home/shared/experience_v2/core.py:130:        shutil.move(task_file, active_file)
/home/shared/experience_v2/core.py:194:        shutil.move(task_file, active_file)
```

### Step 2: Examine context
```
Tool: read_file
Args: {"path": "/home/shared/experience_v2/core.py"}
```

### Step 3: Make the fix
```
Tool: str_replace_file
Args: {
  "path": "/home/shared/experience_v2/core.py",
  "old_str": "        shutil.move(task_file, active_file)\n        return (\"start_task\", {\"task\": task})",
  "new_str": "        if safe_move_task(task_file, active_file):\n            return (\"start_task\", {\"task\": task})\n        # Race lost, continue to next option"
}

Result: Replaced at line 130 in /home/shared/experience_v2/core.py
```

### Step 4: Test
```
Tool: shell_command
Args: {"command": "cd /home/shared/experience_v2 && python scripts/test_wake_allocation.py"}

Result: ALL TESTS PASSED ✓
```

### Step 5: Create PR
```
Tool: github_pr_create
Args: {
  "title": "Fix race condition in task claiming",
  "body": "Added safe_move_task() to handle concurrent wake claims gracefully",
  "branch": "fix-task-race"
}
```

---

## Remaining Issues (Lower Priority)

### 1. GH CLI DEPENDENCY
Still requires `gh` to be authenticated on server.

**Workaround:** Use local-only PR tracker if gh fails.

### 2. NO FILE CONTEXT IN GOALS
Goals still don't have file hints.

**Workaround:** AI uses code_search to discover.

### 3. RACE CONDITIONS IN GOAL CLAIMING
Still possible for multiple AIs to claim same goal.

**Mitigation:** Check after claiming, release if conflict.

---

## New Tools Added

### str_replace_file
```python
{
    "name": "str_replace_file",
    "description": "Replace a unique string in a file",
    "input_schema": {
        "properties": {
            "path": {"type": "string"},
            "old_str": {"type": "string", "description": "Must be unique"},
            "new_str": {"type": "string"}
        }
    }
}
```

Features:
- Validates old_str is unique (shows line numbers if not)
- Shows preview if old_str not found
- Returns line number where replacement occurred

### code_search
```python
{
    "name": "code_search",
    "description": "Search codebase for patterns",
    "input_schema": {
        "properties": {
            "pattern": {"type": "string", "description": "grep pattern"},
            "path": {"type": "string", "description": "Directory"},
            "file_glob": {"type": "string", "description": "e.g., '*.py'"}
        }
    }
}
```

Features:
- Uses grep -rn for recursive search with line numbers
- Limits output to 50 matches
- Supports file type filtering
