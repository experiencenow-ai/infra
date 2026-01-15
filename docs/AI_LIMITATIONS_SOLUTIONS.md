# Solving AI Limitations

## Problem Statement

1. **Too many tools** - AI got confused with 40+ tools, couldn't solve simple email
2. **Looping on broken things** - .env misconfigured → looped for dozens of wakes
3. **No bug fix cycle** - AI doesn't know when to create issues, how to close them
4. **PAT management** - Can't manually configure every new citizen's permissions

---

# Solution 1: Tool Allowlists Per Wake Type

Instead of 40 tools always available, each wake type gets 5-8 specific tools.

```python
WAKE_TOOL_ALLOWLIST = {
    "REFLECT": [
        "task_complete",
        "dream_record",
        "identity_update",
        # NO file tools, NO shell, NO github
    ],
    
    "LIBRARY": [
        "library_load",
        "library_review", 
        "task_complete",
        "escalate",  # If stuck
    ],
    
    "DEBUG": [
        "read_file",
        "shell_command",
        "report_bug",
        "task_complete",
        "task_stuck",
    ],
    
    "CODE": [
        "read_file",
        "write_file",
        "str_replace_file",
        "shell_command",
        "submit_fix",
        "task_complete",
        "task_stuck",
    ],
    
    "EMAIL": [
        "check_email",
        "send_email",
        "task_complete",
        "escalate",
    ],
}

def get_available_tools(wake_type: str) -> list:
    """Return only tools allowed for this wake type."""
    allowed = WAKE_TOOL_ALLOWLIST.get(wake_type, [])
    return [t for t in ALL_TOOLS if t["name"] in allowed]
```

**Result:** AI sees 5-8 tools instead of 40. Much less confusion.

---

# Solution 2: Automatic Failure Detection & Escalation

## The Loop Detection Problem

AI tried email 30 times without realizing it was broken.

## Solution: Failure Tracking + Auto-Escalate

```python
class FailureTracker:
    def __init__(self, citizen: str):
        self.file = Path(f"/home/{citizen}/failure_tracking.json")
        self.data = self._load()
    
    def record_failure(self, operation: str, error: str):
        """Record a failure. If same operation fails 3 times, auto-escalate."""
        key = self._normalize_operation(operation)
        
        if key not in self.data:
            self.data[key] = {"count": 0, "errors": [], "first_seen": now_iso()}
        
        self.data[key]["count"] += 1
        self.data[key]["errors"].append({"error": error, "time": now_iso()})
        self.data[key]["last_seen"] = now_iso()
        self._save()
        
        # AUTO-ESCALATE after 3 failures
        if self.data[key]["count"] >= 3:
            return self._auto_escalate(key, self.data[key])
        
        return None
    
    def _auto_escalate(self, operation: str, failure_data: dict) -> str:
        """Automatically create issue and notify admin."""
        
        # Create GitHub issue
        issue_title = f"REPEATED FAILURE: {operation}"
        issue_body = f"""
## Auto-generated failure report

**Operation:** {operation}
**Failure count:** {failure_data['count']}
**First seen:** {failure_data['first_seen']}
**Last seen:** {failure_data['last_seen']}

### Recent errors:
```
{chr(10).join(e['error'][:200] for e in failure_data['errors'][-3:])}
```

### Suggested actions:
1. Check .env configuration
2. Check network/API access
3. Check file permissions

@admin-citizen please investigate.
"""
        
        # Create issue via shell (simpler than tool)
        result = subprocess.run(
            ["gh", "issue", "create", "--title", issue_title, "--body", issue_body, "--label", "auto-escalated"],
            capture_output=True, text=True, timeout=30
        )
        
        # Mark as escalated so we don't spam
        self.data[operation]["escalated"] = True
        self.data[operation]["issue_url"] = result.stdout.strip()
        self._save()
        
        return f"AUTO-ESCALATED: Created issue for repeated {operation} failures"
```

## Integration Point

```python
def check_email_tool(args, session, modules):
    """Check email with failure tracking."""
    try:
        result = _actual_email_check(session)
        
        if "ERROR" in result:
            # Record failure
            tracker = FailureTracker(session["citizen"])
            escalation = tracker.record_failure("email_check", result)
            if escalation:
                return f"{result}\n\n{escalation}"
        
        return result
    except Exception as e:
        tracker = FailureTracker(session["citizen"])
        tracker.record_failure("email_check", str(e))
        return f"ERROR: {e}"
```

---

# Solution 3: Automatic Bug Fix Cycle

## The Full Cycle (Automated)

```
DETECT → ISSUE → ASSIGN → FIX → VALIDATE → MERGE → CLOSE
   ↓        ↓        ↓       ↓       ↓         ↓       ↓
  Auto    Auto    Manual   Manual   Auto     Auto    Auto
```

## Implementation

### Stage 1: Auto-Detect and Create Issue

Already covered above with FailureTracker.

### Stage 2: Issue Appears in DEBUG Wake

```python
def debug_wake(session, context, modules):
    """DEBUG wake - show open issues, force focus on one."""
    
    # Get open issues assigned to this citizen or unassigned
    issues = _get_open_issues(session["citizen"])
    
    if not issues:
        return "No open issues. Call task_complete."
    
    # Pick highest priority unresolved issue
    issue = issues[0]
    
    prompt = f"""
=== DEBUG WAKE: FIX ISSUE #{issue['number']} ===

ISSUE: {issue['title']}
BODY:
{issue['body'][:500]}

YOUR TASK:
1. Investigate the problem
2. Find the root cause
3. Fix it (use write_file or str_replace_file)
4. Call validate_fix {issue['number']}
5. If validation passes, call submit_fix

AVAILABLE TOOLS: read_file, shell_command, write_file, str_replace_file, validate_fix, submit_fix, task_stuck

If you cannot fix it, call task_stuck with explanation.
"""
    return modules["council"].process(prompt, session, ...)
```

### Stage 3: Validate Fix (Automatic)

```python
def validate_fix(args, session, modules):
    """Run validation for a fix. Returns pass/fail."""
    issue_num = args.get("issue_number")
    
    # Get issue to understand what was broken
    issue = _get_issue(issue_num)
    
    validations = []
    
    # Check 1: Does the code compile/parse?
    if issue.get("labels") and "python" in str(issue["labels"]):
        result = subprocess.run(
            ["python3", "-m", "py_compile", issue.get("file", "")],
            capture_output=True, text=True
        )
        validations.append(("syntax", result.returncode == 0, result.stderr))
    
    # Check 2: Does the specific operation work now?
    operation = issue.get("operation")
    if operation == "email_check":
        test_result = _test_email_config(session)
        validations.append(("email_works", "ERROR" not in test_result, test_result))
    
    # Check 3: Run any associated tests
    test_file = Path(f"/home/shared/tests/test_{issue.get('module', 'unknown')}.py")
    if test_file.exists():
        result = subprocess.run(
            ["python3", "-m", "pytest", str(test_file), "-v"],
            capture_output=True, text=True, timeout=60
        )
        validations.append(("tests", result.returncode == 0, result.stdout[-500:]))
    
    # Report
    all_pass = all(v[1] for v in validations)
    report = "\n".join(f"  {v[0]}: {'PASS' if v[1] else 'FAIL'}" for v in validations)
    
    if all_pass:
        return f"VALIDATION PASSED:\n{report}\n\nYou may now call submit_fix {issue_num}"
    else:
        return f"VALIDATION FAILED:\n{report}\n\nFix the remaining issues."
```

### Stage 4: Submit Fix (Auto-Creates PR)

```python
def submit_fix(args, session, modules):
    """Submit fix - creates PR and links to issue."""
    issue_num = args.get("issue_number")
    summary = args.get("summary", "Fix for issue")
    
    citizen = session["citizen"]
    branch = f"fix-{issue_num}-{citizen}"
    
    # Stage changes
    subprocess.run(["git", "add", "-A"], cwd="/home/shared/infra")
    
    # Commit
    subprocess.run(
        ["git", "commit", "-m", f"{summary}\n\nFixes #{issue_num}"],
        cwd="/home/shared/infra"
    )
    
    # Push
    subprocess.run(["git", "push", "-u", "origin", branch], cwd="/home/shared/infra")
    
    # Create PR
    result = subprocess.run(
        ["gh", "pr", "create", 
         "--title", f"Fix #{issue_num}: {summary}",
         "--body", f"Fixes #{issue_num}\n\nValidation passed.",
         "--head", branch],
        capture_output=True, text=True, cwd="/home/shared/infra"
    )
    
    pr_url = result.stdout.strip()
    
    # Track for auto-merge
    _track_pending_fix(issue_num, pr_url, citizen)
    
    return f"PR CREATED: {pr_url}\n\nAdmin will review and merge."
```

### Stage 5: Admin Reviews and Merges (or Auto-Merge)

```python
def admin_review_wake(session, context, modules):
    """Admin citizen reviews pending fixes."""
    
    pending = _get_pending_fixes()
    
    for fix in pending:
        # Check if validation passed
        if fix["validation_passed"]:
            # Auto-merge if low-risk
            if fix["files_changed"] <= 2 and fix["lines_changed"] <= 50:
                _auto_merge_pr(fix["pr_url"])
                _close_issue(fix["issue_num"], f"Fixed by {fix['pr_url']}")
                continue
        
        # Otherwise, prompt admin for review
        prompt = f"""
PENDING FIX: PR {fix['pr_url']}
Issue: #{fix['issue_num']}
Author: {fix['author']}
Files changed: {fix['files_changed']}
Lines: {fix['lines_changed']}

Review and decide:
- merge_pr {fix['pr_num']}
- reject_pr {fix['pr_num']} "reason"
"""
```

### Stage 6: Issue Auto-Closes

GitHub auto-closes issues when PR with "Fixes #N" is merged.

---

# Solution 4: Admin Citizen

## Role

One citizen (admin/sentinel) that:
- Has write access to ALL citizen repos
- Handles onboarding of new citizens
- Monitors health of all citizens
- Can intervene when others are stuck
- Reviews and merges fixes

## PAT Setup

Only admin needs the broad PAT:

```
Admin PAT:
  infra:         Read/Write
  protocols:     Read/Write
  citizen-opus:  Read/Write  ← Can fix others
  citizen-mira:  Read/Write
  citizen-aria:  Read/Write
  citizen-*:     Read/Write  ← All current and future
```

Other citizens get narrow PATs (own repo + read-only others).

## Admin Wake Schedule

```python
ADMIN_WAKE_SCHEDULE = [
    {"slot": 0, "type": "HEALTH_CHECK"},      # Check all citizens alive
    {"slot": 1, "type": "REVIEW_FIXES"},      # Review/merge pending PRs
    {"slot": 2, "type": "ONBOARD"},           # Process onboarding queue
    {"slot": 3, "type": "ESCALATIONS"},       # Handle auto-escalated issues
    {"slot": 4, "type": "HEALTH_CHECK"},
    {"slot": 5, "type": "REVIEW_FIXES"},
    {"slot": 6, "type": "MAINTENANCE"},       # Clean up old issues, etc
    {"slot": 7, "type": "PEER_MONITOR"},
    {"slot": 8, "type": "REVIEW_FIXES"},
    {"slot": 9, "type": "HEALTH_CHECK"},
]
```

## Onboarding Queue

```python
def request_new_citizen(args, session, modules):
    """Request a new citizen - adds to onboarding queue for admin."""
    
    name = args.get("name")
    purpose = args.get("purpose")
    
    if session["citizen"] != "opus":
        return "ERROR: Only Opus can request new citizens"
    
    queue_file = Path("/home/shared/onboarding_queue.json")
    queue = json.loads(queue_file.read_text()) if queue_file.exists() else []
    
    queue.append({
        "name": name,
        "purpose": purpose,
        "requested_by": session["citizen"],
        "requested_at": now_iso(),
        "status": "pending"
    })
    
    queue_file.write_text(json.dumps(queue, indent=2))
    
    return f"QUEUED: New citizen '{name}' requested. Admin will process."


def admin_onboard_wake(session, context, modules):
    """Admin processes onboarding queue."""
    
    queue = _get_onboarding_queue()
    pending = [q for q in queue if q["status"] == "pending"]
    
    if not pending:
        return "No pending onboarding requests."
    
    req = pending[0]
    
    prompt = f"""
=== ONBOARDING REQUEST ===

Name: {req['name']}
Purpose: {req['purpose']}
Requested by: {req['requested_by']}

STEPS TO ONBOARD:
1. Create Unix account: useradd -m {req['name']}
2. Create citizen repo: gh repo create citizen-{req['name']}
3. Generate SSH key: ssh-keygen for {req['name']}
4. Add deploy key to repo
5. Create .env with ANTHROPIC_API_KEY (from vault)
6. Create narrow PAT for this citizen
7. Initialize contexts from template
8. Add to run.sh citizen list
9. Mark onboarding complete

Call onboard_citizen {req['name']} to execute these steps.
"""
    return modules["council"].process(prompt, session, ...)


def onboard_citizen(args, session, modules):
    """Execute full onboarding for a new citizen."""
    
    if session["citizen"] != "admin":
        return "ERROR: Only admin can onboard citizens"
    
    name = args.get("name")
    
    steps = []
    
    # 1. Create Unix account
    result = subprocess.run(["sudo", "useradd", "-m", "-s", "/bin/bash", name])
    steps.append(("unix_account", result.returncode == 0))
    
    # 2. Create directories
    home = Path(f"/home/{name}")
    (home / "contexts").mkdir(parents=True, exist_ok=True)
    (home / "logs").mkdir(exist_ok=True)
    steps.append(("directories", True))
    
    # 3. Create GitHub repo
    result = subprocess.run(
        ["gh", "repo", "create", f"experiencenow-ai/citizen-{name}", 
         "--public", "--description", f"State for {name}"],
        capture_output=True, text=True
    )
    steps.append(("github_repo", result.returncode == 0))
    
    # 4. Generate SSH key
    key_path = home / ".ssh" / "id_ed25519"
    key_path.parent.mkdir(exist_ok=True)
    subprocess.run(["ssh-keygen", "-t", "ed25519", "-f", str(key_path), "-N", ""])
    steps.append(("ssh_key", key_path.exists()))
    
    # 5. Copy template contexts
    template_dir = Path("/home/shared/templates/citizen")
    for ctx in ["identity.json", "history.json", "goals.json", "working.json"]:
        src = template_dir / ctx
        if src.exists():
            shutil.copy(src, home / "contexts" / ctx)
    steps.append(("contexts", True))
    
    # 6. Create config
    config = {
        "citizen": name,
        "council": {"default_model": "haiku"},
        "permissions": {"can_modify_shared_code": False}
    }
    (home / "config.json").write_text(json.dumps(config, indent=2))
    steps.append(("config", True))
    
    # 7. Set ownership
    subprocess.run(["sudo", "chown", "-R", f"{name}:{name}", str(home)])
    steps.append(("ownership", True))
    
    # Report
    report = "\n".join(f"  {s[0]}: {'OK' if s[1] else 'FAIL'}" for s in steps)
    all_ok = all(s[1] for s in steps)
    
    if all_ok:
        # Mark complete in queue
        _update_onboarding_status(name, "complete")
        return f"ONBOARDING COMPLETE for {name}:\n{report}\n\nNOTE: Add ANTHROPIC_API_KEY to /home/{name}/.env manually (secret)"
    else:
        return f"ONBOARDING PARTIAL for {name}:\n{report}\n\nFix failures and retry."
```

---

# Summary

| Problem | Solution |
|---------|----------|
| Too many tools | Tool allowlists per wake type (5-8 tools, not 40) |
| Looping on broken | FailureTracker + auto-escalate after 3 failures |
| No bug fix cycle | Auto: detect→issue→assign→validate→merge→close |
| PAT management | Admin citizen handles all onboarding |

## New Tool Count Per Wake

| Wake Type | Tool Count | Tools |
|-----------|------------|-------|
| REFLECT | 3 | task_complete, dream_record, identity_update |
| LIBRARY | 4 | library_load, library_review, task_complete, escalate |
| DEBUG | 5 | read_file, shell_command, report_bug, task_complete, task_stuck |
| CODE | 7 | read_file, write_file, str_replace, shell, validate_fix, submit_fix, task_complete |
| EMAIL | 4 | check_email, send_email, task_complete, escalate |
| ADMIN | 6 | health_check, merge_pr, reject_pr, onboard_citizen, task_complete, shell_command |

## Auto-Escalation Flow

```
Failure 1: "ERROR: email connection failed"
           → Recorded in failure_tracking.json

Failure 2: "ERROR: email connection failed"  
           → Count = 2, still trying

Failure 3: "ERROR: email connection failed"
           → Count = 3 → AUTO-ESCALATE
           → GitHub issue created automatically
           → Admin notified
           → AI stops trying, moves on
```

## Bug Fix Flow

```
1. Auto-detected failure
      ↓
2. Issue #42 created automatically
      ↓
3. Next DEBUG wake sees issue #42
      ↓
4. AI investigates, finds .env typo
      ↓
5. AI calls str_replace_file to fix
      ↓
6. AI calls validate_fix 42
      ↓
7. Validation passes → AI calls submit_fix 42
      ↓
8. PR created linking to #42
      ↓
9. Admin reviews, merges
      ↓
10. Issue #42 auto-closed by GitHub
```
