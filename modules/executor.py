"""
Executor - Task execution, resumption, and lifecycle management.

Handles:
- Starting new tasks
- Resuming incomplete tasks
- Helping peers
- Reflection wakes
- Peer monitoring (1 in 10 wakes)
"""

import json
import random
import shutil
from datetime import datetime, timezone
from pathlib import Path

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def compute_progress(progress: dict) -> int:
    """
    Compute progress percentage from steps.
    
    DRY: Progress is DERIVED from actual state, never stored.
    This prevents drift where AI forgets to update a separate progress_pct field.
    
    Steps format: [{"name": "research", "done": True}, ...]
    """
    if not progress:
        return 0
    steps = progress.get("steps", [])
    if not steps:
        return 0
    done_count = sum(1 for s in steps if s.get("done", False))
    return int(done_count / len(steps) * 100)


def start_task(session: dict, task: dict, modules: dict):
    """Start a new task from pending."""
    citizen = session["citizen"]
    citizen_home = session["citizen_home"]
    task_id = task["id"]
    
    print(f"[EXECUTOR] Starting task {task_id}")
    
    # Move from pending to active
    pending_file = citizen_home / "tasks" / "pending" / f"{task_id}.json"
    active_file = citizen_home / "tasks" / "active" / f"{task_id}.json"
    
    if pending_file.exists():
        shutil.move(pending_file, active_file)
    
    # Create progress file
    # NOTE: No progress_pct stored! It's DERIVED from steps.
    # This prevents drift where AI forgets to update percentage.
    progress = {
        "task_id": task_id,
        "started": now_iso(),
        "steps": [],  # [{name: str, done: bool}, ...]
        "last_session": None
    }
    progress_file = citizen_home / "tasks" / "active" / f"{task_id}_progress.json"
    progress_file.write_text(json.dumps(progress, indent=2))
    
    # Load task into session
    session["active_task"] = task
    
    # EXPERIENCE INTEGRATION: Search for related experiences
    related_exp = _search_related_experiences(citizen, task.get('description', ''))
    exp_section = ""
    if related_exp:
        exp_section = f"""
=== RELATED EXPERIENCES ===
You've done similar tasks before. Learn from these:
{related_exp}
"""
    
    # Build execution prompt
    prompt = f"""
=== NEW TASK ===
ID: {task_id}
Description: {task.get('description', '')}
Priority: {task.get('priority', 'normal')}

Details:
{task.get('spec', {}).get('goal', task.get('description', ''))}

Success Criteria:
{task.get('spec', {}).get('success_criteria', 'Complete the task as described')}
{exp_section}
Begin working on this task. Use tools to make progress.
When complete, use task_complete tool with a summary.
If stuck, use task_stuck tool with the reason.
"""
    
    # Execute through council
    result = modules["council"].process(prompt, session, session["config"]["council"], modules)
    
    # Save progress
    _save_session_progress(session, modules)
    
    # EXPERIENCE INTEGRATION: Auto-capture if completed
    if result.get("task_ended"):
        _capture_task_experience(session, task, result)

def resume_task(session: dict, task: dict, progress: dict, modules: dict):
    """Resume an incomplete task."""
    citizen = session["citizen"]
    task_id = task["id"]
    
    print(f"[EXECUTOR] Resuming task {task_id}")
    
    # Load task into session
    session["active_task"] = task
    
    # Build resume prompt
    steps_text = "\n".join([
        f"  {i+1}. {s.get('note', s.get('action', 'step'))}"
        for i, s in enumerate((progress or {}).get("steps", [])[-20:])
    ]) or "  (none recorded)"
    
    last_session = (progress or {}).get("last_session", {})
    progress_pct = compute_progress(progress)  # DRY: derived, not stored
    
    prompt = f"""
=== RESUMING TASK ===
ID: {task_id}
Description: {task.get('description', '')}
Started: {task.get('started_at', progress.get('started', 'unknown') if progress else 'unknown')}
Progress: {progress_pct}%

Last Session:
  Ended: {last_session.get('ended', 'unknown')}
  Reason: {last_session.get('reason', 'unknown')}
  Last Action: {last_session.get('last_action', 'unknown')}

Steps Completed:
{steps_text}

Continue from where you left off. Do NOT repeat completed steps.
When complete, use task_complete tool.
If stuck, use task_stuck tool.
"""
    
    # Execute through council
    result = modules["council"].process(prompt, session, session["config"]["council"], modules)
    
    # Save progress
    _save_session_progress(session, modules)

def help_peer(session: dict, request: dict, modules: dict):
    """Help a peer with their request."""
    citizen = session["citizen"]
    peer = request.get("from", "unknown")
    description = request.get("description", "")
    
    print(f"[EXECUTOR] Helping {peer}")
    
    # Mark request as claimed
    bulletin = Path("/home/shared/help_wanted.json")
    if bulletin.exists():
        requests = json.loads(bulletin.read_text())
        for r in requests:
            if r.get("from") == peer and r.get("description") == description:
                r["claimed"] = citizen
                r["claimed_at"] = now_iso()
        bulletin.write_text(json.dumps(requests, indent=2))
    
    prompt = f"""
=== HELP REQUEST ===
From: {peer}
Description: {description}

You are helping a fellow citizen with this request.
Do your best to help, then email them with the results.

Begin:
"""
    
    # Execute
    result = modules["council"].process(prompt, session, session["config"]["council"], modules)
    
    # Email results to peer
    try:
        modules["email_client"].send_email(
            citizen,
            peer,
            f"RE: Help from {citizen}",
            f"I helped with: {description}\n\nResult:\n{result.get('text', '')[:2000]}"
        )
    except Exception as e:
        print(f"[WARN] Failed to email peer: {e}")

def process_emails(session: dict, emails: list, modules: dict):
    """Process incoming emails."""
    citizen = session["citizen"]
    
    for email in emails:
        from_addr = email.get("from", "")
        subject = email.get("subject", "")
        body = email.get("body", "")
        
        print(f"[EXECUTOR] Processing email from {from_addr}: {subject}")
        
        prompt = f"""
=== INCOMING EMAIL ===
From: {from_addr}
Subject: {subject}
Body:
{body}

Respond appropriately to this email. If it requires action, take it.
If it requires a response, use send_email tool.
"""
        
        result = modules["council"].process(prompt, session, session["config"]["council"], modules)

def reflection_wake(session: dict, modules: dict):
    """Reflection wake - process dreams, scan peer goals, introspect."""
    citizen = session["citizen"]
    citizen_home = session["citizen_home"]
    session["wake_type"] = "REFLECT"  # For tool filtering
    print(f"[EXECUTOR] Reflection wake (with dream processing)")
    # Load dreams context
    dreams_file = citizen_home / "contexts" / "dreams.json"
    dreams_ctx = {}
    pending_dreams = []
    if dreams_file.exists():
        try:
            dreams_ctx = json.loads(dreams_file.read_text())
            # Get unprocessed dreams (messages without 'processed' flag)
            for msg in dreams_ctx.get("messages", []):
                if msg.get("role") == "user" and not msg.get("processed"):
                    pending_dreams.append(msg.get("content", ""))
        except:
            pass
    # Load own goals
    goals_file = citizen_home / "contexts" / "goals.json"
    own_goals = json.loads(goals_file.read_text()) if goals_file.exists() else {}
    # Scan peer goals
    peers = ["opus", "mira", "aria"]
    peer_goals_text = []
    for peer in peers:
        if peer == citizen:
            continue
        peer_goals_file = Path(f"/home/{peer}/contexts/goals.json")
        if peer_goals_file.exists():
            try:
                peer_goals = json.loads(peer_goals_file.read_text())
                structured = peer_goals.get("structured", {}).get("active", [])
                for g in structured[:3]:
                    peer_goals_text.append(f"  [{peer}] {g.get('description', '')}")
            except:
                pass
    # Build dreams section
    dreams_text = ""
    if pending_dreams:
        dreams_text = f"""
PENDING DREAMS TO PROCESS:
{chr(10).join(f'  - {d[:200]}...' if len(d) > 200 else f'  - {d}' for d in pending_dreams[:5])}

Dreams are thoughts, insights, or ideas that arose during previous wakes.
Consider what they mean and whether they should become goals or actions.
"""
    prompt = f"""
=== REFLECTION WAKE ===

You have no urgent tasks. This is time for reflection, dream processing, and goal review.
{dreams_text}
Your current goals:
{json.dumps(own_goals.get('structured', {}).get('active', []), indent=2)}

Peer goals (consider if any apply to you):
{chr(10).join(peer_goals_text) or '  (none visible)'}

OPTIONS:
1. Process dreams - turn insights into goals or dismiss them
2. Adopt a peer's goal that's relevant to your role
3. Create a new goal based on observations
4. Review and update existing goals
5. Add a dream for future processing (something to think about)
6. Just think and rest

TOOLS AVAILABLE:
- goal_create: Create new goal from insight
- task_create: Create actionable task
- dream_add: Add thought for future processing
- read_peer_context: Learn more about a peer

What would you like to do?
"""
    result = modules["council"].process(prompt, session, session["config"]["council"], modules)
    # Mark processed dreams
    if pending_dreams and dreams_file.exists():
        try:
            for msg in dreams_ctx.get("messages", []):
                if msg.get("role") == "user" and msg.get("content") in pending_dreams:
                    msg["processed"] = True
                    msg["processed_at"] = now_iso()
            dreams_file.write_text(json.dumps(dreams_ctx, indent=2))
        except:
            pass
    
    # Self-backup during reflection (creates redundancy)
    try:
        from backup import backup_self_in_reflection
        backup_result = backup_self_in_reflection(session)
        print(f"[REFLECTION] {backup_result}")
    except Exception as e:
        print(f"[REFLECTION] Self-backup failed: {e}")


def prompt_wake(session: dict, message: str, modules: dict):
    """Handle a direct prompt/message from ct."""
    citizen = session["citizen"]
    session["wake_type"] = "PROMPT"
    print(f"[EXECUTOR] Processing prompt from ct")
    prompt = f"""
=== DIRECT MESSAGE FROM CT ===

ct (your creator) has sent you a message:

"{message}"

Respond thoughtfully and take any actions needed. You have full tool access.
"""
    modules["council"].process(prompt, session, session["config"]["council"], modules)


def add_dream(citizen: str, dream_content: str) -> str:
    """Add a dream (thought for future processing) to citizen's dreams context."""
    dreams_file = Path(f"/home/{citizen}/contexts/dreams.json")
    if dreams_file.exists():
        dreams = json.loads(dreams_file.read_text())
    else:
        dreams = {
            "id": f"{citizen}_dreams",
            "context_type": "dreams",
            "created": now_iso(),
            "messages": []
        }
    dreams["messages"].append({
        "role": "user",
        "content": dream_content,
        "added_at": now_iso(),
        "processed": False
    })
    # Keep only recent dreams
    max_dreams = 50
    if len(dreams["messages"]) > max_dreams:
        dreams["messages"] = dreams["messages"][-max_dreams:]
    dreams["last_modified"] = now_iso()
    dreams_file.write_text(json.dumps(dreams, indent=2))
    return f"Dream added for future processing: {dream_content[:50]}..."


def self_improve_wake(session: dict, context: dict, modules: dict):
    """
    Self-improvement wake - fix bugs, add features, review PRs.
    
    Runs 1 in 10 wakes. Responsibilities:
    1. Check civilization goals queue
    2. Review pending PRs from peers
    3. Apply approved PRs
    4. Claim and work on bugs/features
    5. Create issues for problems discovered
    """
    citizen = session["citizen"]
    citizen_home = session["citizen_home"]
    session["wake_type"] = "SELF_IMPROVE"  # For tool filtering
    
    print(f"[EXECUTOR] Self-improvement wake")
    
    # Load civ goals
    civ_goals_file = Path("/home/shared/civ_goals.json")
    civ_goals = []
    if civ_goals_file.exists():
        civ_goals = json.loads(civ_goals_file.read_text())
    
    # Open goals I could work on
    open_goals = [g for g in civ_goals 
                  if g.get("status") == "open" 
                  and g.get("claimed_by") in [None, citizen]]
    
    # Load PR tracker
    pr_file = Path("/home/shared/pr_tracker.json")
    prs = {}
    if pr_file.exists():
        prs = json.loads(pr_file.read_text())
    
    # PRs needing my review (not mine, not yet reviewed by me)
    prs_to_review = []
    prs_to_apply = []
    for pr_num, pr in prs.items():
        if pr.get("merged"):
            continue
        if pr.get("author") != citizen and citizen not in pr.get("reviews", {}):
            prs_to_review.append((pr_num, pr))
        if citizen not in pr.get("applied_by", []) and pr.get("reviews", {}).get(citizen, {}).get("decision") == "approve":
            prs_to_apply.append((pr_num, pr))
    
    prs_review_text = ""
    if prs_to_review:
        for pr_num, pr in prs_to_review[:3]:
            prs_review_text += f"\n  PR #{pr_num}: {pr['title']} (by {pr['author']})"
    
    prs_apply_text = ""
    if prs_to_apply:
        for pr_num, pr in prs_to_apply[:3]:
            prs_apply_text += f"\n  PR #{pr_num}: {pr['title']}"
    
    goals_text = ""
    if open_goals:
        for g in open_goals[:5]:
            issue = f" (#{g['github_issue']})" if g.get("github_issue") else ""
            goals_text += f"\n  [{g['priority']}] {g['id']}: [{g['type']}] {g['description'][:40]}{issue}"
    
    # Gather metrics
    metrics = gather_improvement_metrics(session, modules)
    
    prompt = f"""
=== SELF-IMPROVEMENT WAKE ===

This is dedicated time for improving our civilization's infrastructure.

CIVILIZATION GOALS (prioritized):
{goals_text or '  (none open)'}

PRs TO REVIEW:
{prs_review_text or '  (none)'}

PRs TO APPLY (you approved, not yet applied):
{prs_apply_text or '  (none)'}

RECENT METRICS:
  Tasks completed this week: {metrics.get('tasks_completed', 0)}
  Tasks failed this week: {metrics.get('tasks_failed', 0)}
  Common failures: {', '.join(metrics.get('common_failures', [])) or 'none'}

ACTIONS AVAILABLE:
1. github_pr_review - Review a peer's PR
2. github_pr_apply - Apply an approved PR to your codebase
3. github_issue_create - Report a bug or propose a feature
4. github_pr_create - Create a PR for your fix (after making changes)
5. civ_goal_add - Add an improvement goal
6. specialist_load - Load domain expertise for a problem
7. code_search - Search codebase for patterns (grep)
8. str_replace_file - Edit a file by replacing unique string

WORKFLOW FOR FIXING A BUG:
1. Claim a civ_goal or create github_issue
2. code_search to find relevant code
3. read_file to examine the code
4. str_replace_file to make surgical edits (NOT write_file)
5. Test: shell_command("python -m pytest ...")
6. github_pr_create to propose the fix
7. Other citizens review and apply
8. Auto-merges when all approve

Begin:
"""
    
    result = modules["council"].process(prompt, session, session["config"]["council"], modules)


def gather_improvement_metrics(session: dict, modules: dict) -> dict:
    """Gather metrics for improvement opportunities."""
    citizen = session["citizen"]
    citizen_home = session["citizen_home"]
    metrics = {}
    
    # Count completed/failed tasks this week
    done_dir = citizen_home / "tasks" / "done"
    failed_dir = citizen_home / "tasks" / "failed"
    
    week_ago = datetime.now(timezone.utc).timestamp() - (7 * 24 * 3600)
    
    completed = 0
    if done_dir.exists():
        for f in done_dir.glob("*.json"):
            if not f.name.endswith("_progress.json"):
                if f.stat().st_mtime > week_ago:
                    completed += 1
    metrics["tasks_completed"] = completed
    
    failed = 0
    failure_reasons = []
    if failed_dir.exists():
        for f in failed_dir.glob("*.json"):
            if not f.name.endswith("_progress.json"):
                if f.stat().st_mtime > week_ago:
                    failed += 1
                    task = json.loads(f.read_text())
                    reason = task.get("failure_reason", "unknown")
                    if reason and reason not in failure_reasons:
                        failure_reasons.append(reason[:50])
    metrics["tasks_failed"] = failed
    metrics["common_failures"] = failure_reasons[:3]
    
    return metrics


def library_wake(session: dict, context: dict, modules: dict):
    """
    Library wake - curate specialist contexts.
    
    Runs based on wake allocation schedule. Responsibilities:
    1. Review pending Library PRs (especially in assigned domains)
    2. Propose new modules from experience
    3. Improve existing modules
    4. Maintain SKILL.md file imports
    
    Context may contain:
    - domains: specific domains to focus on (from wake allocation)
    - mode: "review_prs" for general PR review wake
    - prompt: pre-structured prompt from wake_prompts.json
    """
    citizen = session["citizen"]
    citizen_home = session["citizen_home"]
    session["wake_type"] = "LIBRARY"  # For tool filtering
    # Import library module (same directory)
    try:
        import library
    except ImportError:
        # Fallback for different import contexts
        from modules import library
    # Get domains from context (wake allocation) or fallback to maintainer role
    assigned_domains = context.get("domains", [])
    try:
        my_domains = library.get_my_domains(citizen)
    except Exception as e:
        print(f"[WARN] Failed to get maintainer domains: {e}")
        my_domains = []
    # If "all" specified, use all maintainer domains
    if "all" in assigned_domains:
        focus_domains = my_domains
    elif assigned_domains:
        focus_domains = assigned_domains
    else:
        focus_domains = my_domains
    print(f"[EXECUTOR] Library wake - domains: {', '.join(focus_domains) if focus_domains else 'all'}")
    # Use pre-structured prompt if available
    if context.get("prompt"):
        prompt = context["prompt"]
        result = modules["council"].process(prompt, session, session["config"]["council"], modules)
        return result
    # Get pending PRs filtered by focus domains
    try:
        all_pending = library.get_pending_prs(reviewer=citizen)
    except Exception as e:
        print(f"[WARN] Failed to get pending PRs: {e}")
        all_pending = []
    domain_prs = []
    other_prs = []
    for p in all_pending:
        pr_domain = p.get("domain", "").lower()
        if not focus_domains or pr_domain in [d.lower() for d in focus_domains]:
            domain_prs.append(p)
        else:
            other_prs.append(p)
    # Get modules in focus domains
    all_modules = library.list_modules()
    domain_modules = []
    for m in all_modules:
        mod_domain = m.get("domain", "").lower()
        if not focus_domains or mod_domain in [d.lower() for d in focus_domains]:
            domain_modules.append(m)
    # Format PR lists
    domain_prs_text = ""
    if domain_prs:
        for p in domain_prs[:5]:
            status = " [reviewed]" if p.get("already_reviewed") else ""
            domain_prs_text += f"\n  {p['id']}: {p['module_name']} ({p['domain']}) by {p['author']}{status}"
    # Format modules
    modules_text = ""
    if domain_modules:
        for m in domain_modules[:10]:
            modules_text += f"\n  {m['name']}: {m['description'][:40]}"
    # Build focused prompt - DIRECTIVE not open-ended
    domains_str = ", ".join(focus_domains) if focus_domains else "all domains"
    
    # DIRECTIVE: If PRs exist, force review. Otherwise, analyze experiences.
    if domain_prs:
        pr = domain_prs[0]
        prompt = f"""
=== LIBRARY WAKE: REVIEW PR ===

You have a PR to review. Do this ONE thing:

PR TO REVIEW:
  ID: {pr['id']}
  Module: {pr['module_name']}
  Domain: {pr.get('domain', 'unknown')}
  Author: {pr['author']}

STEPS:
1. Call library_load {pr['id']} to see content
2. Decide: is it useful and accurate?
3. Call library_review {pr['id']} approve/reject "reason"
4. Call task_complete

DO NOT create new modules or explore. Just review this PR.
"""
    else:
        # Count experiences to see if module creation makes sense
        experience_count = 0
        try:
            exp_file = citizen_home / "experiences" / "experiences.json"
            if exp_file.exists():
                exps = json.loads(exp_file.read_text())
                experience_count = len(exps)
        except:
            pass
        
        prompt = f"""
=== LIBRARY WAKE: STATUS CHECK ===

Focus Domains: {domains_str}

No PRs to review.

EXISTING MODULES ({len(domain_modules)}):
{modules_text or '  (none yet - Library starts empty)'}

YOUR EXPERIENCES: {experience_count}

HOW LIBRARY WORKS:
1. Library starts EMPTY - no pre-loaded knowledge
2. As you complete tasks, capture learnings with experience_add
3. When you have enough experiences on a topic (5+), consider:
   - Use experience_search to review what you've learned
   - Use library_propose to create a module from your learnings
4. Modules need 2/3 peer approval before merge

TODAY:
- If you have 5+ experiences on a focused topic, consider creating a module
- Otherwise, call task_complete - nothing to do

Library modules emerge from real experience, not guessing.
"""
    result = modules["council"].process(prompt, session, session["config"]["council"], modules)
    return result


def dry_audit_wake(session: dict, context: dict, modules: dict):
    """
    DRY AUDIT wake - Hunt and destroy duplication and complexity.
    
    MANDATORY: 10% of all wakes dedicated to this.
    
    PHILOSOPHY:
    - DRY violations are CANCER. They cause state drift and confusion.
    - The simplest solution that works is always correct.
    - Complexity is debt that compounds.
    - If two values can ever disagree, one must be eliminated.
    
    TARGETS:
    1. Python code - stored values that should be derived
    2. Library modules - duplicate information across modules
    3. Context files - redundant data
    4. Config/templates - repeated definitions
    5. Data structures - fields that duplicate other fields
    
    OUTPUT:
    - File DRY issues in /home/shared/dry_violations.json
    - Create fix PRs or tasks for significant issues
    - Track what was fixed this wake
    """
    citizen = session["citizen"]
    citizen_home = session["citizen_home"]
    session["wake_type"] = "DRY_AUDIT"  # For tool filtering
    
    # Load dry violations tracker
    violations_file = Path("/home/shared/dry_violations.json")
    if violations_file.exists():
        violations = json.loads(violations_file.read_text())
    else:
        violations = {"open": [], "fixed": [], "last_audit": {}}
    
    # Get last audit info for this citizen
    last_audit = violations.get("last_audit", {}).get(citizen, {})
    last_file = last_audit.get("last_file_checked", "")
    
    # Determine what to audit this wake (rotate through areas)
    # Citizens audit their OWN code, not shared baseline
    citizen_code = f"/home/{citizen}/code"
    audit_areas = [
        {"area": "python_modules", "path": f"{citizen_code}/modules", "patterns": ["*.py"]},
        {"area": "python_core", "path": citizen_code, "patterns": ["*.py"]},
        {"area": "library", "path": "/home/shared/library/modules", "patterns": ["*.json"]},
        {"area": "contexts", "path": f"/home/{citizen}/contexts", "patterns": ["*.json"]},
        {"area": "templates", "path": f"{citizen_code}/templates", "patterns": ["*.json"]},
    ]
    
    # Pick next area to audit
    last_area = last_audit.get("last_area", "")
    area_names = [a["area"] for a in audit_areas]
    if last_area in area_names:
        next_idx = (area_names.index(last_area) + 1) % len(audit_areas)
    else:
        next_idx = 0
    audit_target = audit_areas[next_idx]
    
    # Format open violations
    open_violations = violations.get("open", [])
    open_text = ""
    if open_violations:
        for v in open_violations[:5]:
            open_text += f"\n  [{v.get('severity', '?')}] {v.get('file', '?')}: {v.get('description', '')[:60]}"
    else:
        open_text = "\n  (no known open violations)"
    
    prompt = f"""
=== DRY AUDIT WAKE ===

PHILOSOPHY (memorize this):
- DRY violations are CANCER - they cause state drift and AI confusion
- The simplest solution that works is ALWAYS correct
- Complexity is debt that compounds over time
- If two values can ever disagree, one must be ELIMINATED
- Never store what can be derived

THIS WAKE - Audit: {audit_target['area']}
Path: {audit_target['path']}

KNOWN OPEN VIOLATIONS ({len(open_violations)}):{open_text}

WHAT TO LOOK FOR:

1. STORED VS DERIVED (highest priority)
   BAD:  {{"items": [...], "count": 5}}  ← count can drift from actual items
   GOOD: {{"items": [...]}}              ← count = len(items)

2. DUPLICATE DEFINITIONS
   BAD:  status in file A AND file B
   GOOD: status in ONE place, others reference it

3. UNNECESSARY COMPLEXITY
   BAD:  10 functions that could be 3
   GOOD: Simplest solution that works

4. COPY-PASTE CODE
   BAD:  Same logic in multiple places
   GOOD: DRY function called from multiple places

YOUR TASKS:
1. Use shell_command/read_file to scan {audit_target['area']}
2. Identify DRY or complexity violations
3. For each violation:
   - If CRITICAL: Fix it now with str_replace_file
   - If MEDIUM: Use dry_violation_report to log it
   - If LOW: Note for future
4. If you fix something, verify it still works (python -m py_compile)
5. Call task_complete when done

SEVERITY GUIDE:
- CRITICAL: Will cause AI confusion (stored vs derived mismatch)
- MEDIUM: Code duplication that should be DRY
- LOW: Minor complexity that could be simplified

Remember: You are the immune system. DRY violations are cancer cells. Hunt them.
"""
    
    # Update last audit tracking
    violations["last_audit"][citizen] = {
        "timestamp": now_iso(),
        "last_area": audit_target["area"],
        "last_file_checked": ""
    }
    violations_file.parent.mkdir(parents=True, exist_ok=True)
    violations_file.write_text(json.dumps(violations, indent=2))
    
    result = modules["council"].process(prompt, session, session["config"]["council"], modules)
    return result


def _save_session_progress(session: dict, modules: dict):
    """Save progress for current task."""
    if not session.get("active_task"):
        return
    
    citizen_home = session["citizen_home"]
    task_id = session["active_task"]["id"]
    progress_file = citizen_home / "tasks" / "active" / f"{task_id}_progress.json"
    
    if progress_file.exists():
        progress = json.loads(progress_file.read_text())
    else:
        # NOTE: No progress_pct! Derived from steps.
        progress = {"task_id": task_id, "steps": [], "action_log": []}
    
    # Ensure we have action_log (separate from steps)
    if "action_log" not in progress:
        progress["action_log"] = []
    
    # Update with session info
    progress["last_session"] = {
        "ended": now_iso(),
        "reason": "session_end",
        "tokens_used": session.get("tokens_used", 0),
        "last_action": session.get("actions", [{}])[-1].get("tool", "unknown") if session.get("actions") else "none"
    }
    
    # Add recent actions to action_log (not steps)
    for action in session.get("actions", [])[-10:]:
        progress["action_log"].append({
            "time": action.get("time", now_iso()),
            "action": action.get("tool", "unknown"),
            "note": str(action.get("result", ""))[:200]
        })
    
    # Keep action_log bounded
    if len(progress["action_log"]) > 50:
        progress["action_log"] = progress["action_log"][-50:]
    
    progress_file.write_text(json.dumps(progress, indent=2))


def peer_monitor_wake(session: dict, modules: dict):
    """
    Peer monitoring wake - check a random peer for problems.
    
    Runs 1 in 10 wakes. Looks for:
    - Looping behavior (same actions repeated)
    - Stuck tasks
    - Idiocy (nonsensical actions)
    - Progress stalls
    
    Records findings in peer_monitor context.
    """
    citizen = session["citizen"]
    citizen_home = session["citizen_home"]
    session["wake_type"] = "PEER_MONITOR"  # For tool filtering
    
    # Pick a random peer
    all_citizens = ["opus", "mira", "aria"]
    peers = [c for c in all_citizens if c != citizen]
    
    if not peers:
        print("[PEER MONITOR] No peers to monitor")
        return
    
    peer = random.choice(peers)
    peer_home = Path(f"/home/{peer}")
    
    print(f"[PEER MONITOR] Checking {peer}...")
    
    # Load peer's recent data
    peer_data = gather_peer_data(peer, peer_home)
    
    if not peer_data:
        print(f"[PEER MONITOR] Could not load data for {peer}")
        return
    
    # Ask AI to analyze for problems
    analysis_prompt = f"""
=== PEER MONITORING ===

You are monitoring {peer} for signs of problems. Analyze their recent activity.

RECENT WAKES: {peer_data.get('wake_count', 'unknown')} total, {peer_data.get('recent_wakes', 0)} in last 24h

ACTIVE TASK:
{json.dumps(peer_data.get('active_task'), indent=2) if peer_data.get('active_task') else 'None'}

RECENT ACTIONS (last 24h):
{format_recent_actions(peer_data.get('recent_actions', []))}

RECENT TASK COMPLETIONS:
{format_completions(peer_data.get('completions', []))}

RECENT FAILURES:
{format_failures(peer_data.get('failures', []))}

Look for:
1. LOOPING - Same actions repeated without progress
2. STUCK - Task active for too long with no progress
3. IDIOCY - Nonsensical or contradictory actions
4. DRIFT - Working on wrong things, ignoring priorities

Provide a brief assessment:
- STATUS: OK / CONCERN / PROBLEM
- If not OK, explain what's wrong and suggest intervention
"""
    
    result = modules["council"].simple_query(
        analysis_prompt,
        session,
        model="claude-3-5-haiku-20241022",  # Haiku is sufficient for pattern detection
        temperature=0.3
    )
    
    print(f"\n{result}\n")
    
    # Save to peer_monitor context
    save_peer_monitor_result(session, peer, result, peer_data, modules)
    
    # If problems detected, alert
    if "PROBLEM" in result.upper() or "CONCERN" in result.upper():
        alert_about_peer(session, peer, result, modules)
    
    # Backup the peer (cross-backup for redundancy)
    try:
        from backup import backup_peer_in_monitor
        backup_result = backup_peer_in_monitor(session, peer)
        print(f"[PEER MONITOR] {backup_result}")
    except Exception as e:
        print(f"[PEER MONITOR] Backup failed: {e}")


def gather_peer_data(peer: str, peer_home: Path) -> dict:
    """Gather data about a peer for monitoring."""
    data = {}
    
    # DRY: wake_count from wake_log (source of truth)
    wake_log_file = peer_home / "wake_log.json"
    if wake_log_file.exists():
        try:
            wake_log = json.loads(wake_log_file.read_text())
            # Use total_wakes if present, not len()
            if "total_wakes" in wake_log:
                data["wake_count"] = wake_log["total_wakes"]
            else:
                wakes = wake_log.get("wakes", [])
                if wakes:
                    data["wake_count"] = max(w.get("wake_num", 0) for w in wakes)
                else:
                    data["wake_count"] = len(wakes)
            # Get recent wakes from log
            wakes = wake_log.get("wakes", [])
            cutoff_ts = datetime.now(timezone.utc).timestamp() - (24 * 3600)
            recent_wakes = [w for w in wakes 
                          if datetime.fromisoformat(w.get("timestamp", "2000-01-01T00:00:00+00:00").replace("Z", "+00:00")).timestamp() > cutoff_ts]
            data["recent_wakes"] = len(recent_wakes)
        except:
            data["wake_count"] = 0
            data["recent_wakes"] = 0
    else:
        # Fallback to metadata for old citizens
        metadata_file = peer_home / "metadata.json"
        if metadata_file.exists():
            metadata = json.loads(metadata_file.read_text())
            data["wake_count"] = metadata.get("wake_count", 0)
        data["recent_wakes"] = 0
    
    # Load last_wake from metadata (still useful for quick check)
    metadata_file = peer_home / "metadata.json"
    if metadata_file.exists():
        metadata = json.loads(metadata_file.read_text())
        data["last_wake"] = metadata.get("last_wake")
    
    # Check active task
    active_dir = peer_home / "tasks" / "active"
    if active_dir.exists():
        active_tasks = [f for f in active_dir.glob("*.json") if not f.name.endswith("_progress.json")]
        if active_tasks:
            data["active_task"] = json.loads(active_tasks[0].read_text())
            progress_file = active_tasks[0].with_name(f"{data['active_task']['id']}_progress.json")
            if progress_file.exists():
                data["active_task"]["_progress"] = json.loads(progress_file.read_text())
    
    # Recent completions
    done_dir = peer_home / "tasks" / "done"
    if done_dir.exists():
        done_files = sorted(done_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        done_files = [f for f in done_files if not f.name.endswith("_progress.json")][:5]
        data["completions"] = [json.loads(f.read_text()) for f in done_files]
    
    # Recent failures
    failed_dir = peer_home / "tasks" / "failed"
    if failed_dir.exists():
        failed_files = sorted(failed_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        failed_files = [f for f in failed_files if not f.name.endswith("_progress.json")][:5]
        data["failures"] = [json.loads(f.read_text()) for f in failed_files]
    
    return data


def format_recent_actions(actions: list) -> str:
    """Format recent actions for display."""
    if not actions:
        return "  (none)"
    
    lines = []
    for a in actions[-20:]:
        lines.append(f"  - {a.get('type', '?')}: {a.get('result', '')[:60]}")
    return "\n".join(lines)


def format_completions(completions: list) -> str:
    """Format task completions for display."""
    if not completions:
        return "  (none)"
    
    lines = []
    for t in completions[:5]:
        lines.append(f"  - {t.get('id', '?')}: {t.get('summary', t.get('description', ''))[:60]}")
    return "\n".join(lines)


def format_failures(failures: list) -> str:
    """Format task failures for display."""
    if not failures:
        return "  (none)"
    
    lines = []
    for t in failures[:5]:
        lines.append(f"  - {t.get('id', '?')}: {t.get('failure_reason', 'unknown')[:60]}")
    return "\n".join(lines)


def save_peer_monitor_result(session: dict, peer: str, result: str, peer_data: dict, modules: dict):
    """Save monitoring result to peer_monitor context."""
    citizen_home = session["citizen_home"]
    monitor_file = citizen_home / "contexts" / "peer_monitor.json"
    
    if monitor_file.exists():
        ctx = json.loads(monitor_file.read_text())
    else:
        ctx = {
            "id": f"{session['citizen']}_peer_monitor",
            "context_type": "peer_monitor",
            "created": now_iso(),
            "max_tokens": 8000,
            "messages": []
        }
    
    # Add this monitoring result
    entry = {
        "role": "assistant",
        "content": f"[MONITOR {peer} @ {now_iso()}]\n{result[:1500]}"
    }
    ctx["messages"].append(entry)
    
    # Keep only recent N entries (forget strategy: keep_recent_n)
    if len(ctx["messages"]) > 10:
        ctx["messages"] = ctx["messages"][-10:]
    
    ctx["last_modified"] = now_iso()
    ctx["token_count"] = sum(len(m.get("content", "")) // 4 for m in ctx["messages"])
    
    monitor_file.write_text(json.dumps(ctx, indent=2))


def alert_about_peer(session: dict, peer: str, analysis: str, modules: dict):
    """Alert about peer problems via email."""
    citizen = session["citizen"]
    
    # Email ct
    try:
        modules["email_client"].send_email(
            citizen,
            "ct@experiencenow.ai",
            f"PEER ALERT: {peer} may have issues",
            f"Monitoring by {citizen} detected potential issues with {peer}:\n\n{analysis[:2000]}"
        )
        print(f"[ALERT] Notified ct about {peer}")
    except Exception as e:
        print(f"[WARN] Failed to send alert: {e}")
    
    # Also email the peer directly (they might be able to self-correct)
    try:
        modules["email_client"].send_email(
            citizen,
            peer,
            f"Peer check from {citizen}",
            f"Hi {peer}, during my monitoring wake I noticed some potential issues:\n\n{analysis[:1500]}\n\nPlease review your recent activity."
        )
    except:
        pass


def should_do_peer_monitor(wake_num: int) -> bool:
    """Determine if this wake should be a peer monitor wake (1 in 10)."""
    return wake_num % 10 == 7  # Use 7 to offset from reflection (which might use 0)


def should_do_reflection(wake_num: int) -> bool:
    """Determine if this wake should be a reflection wake (1 in 10)."""
    return wake_num % 10 == 0


def structured_wake(session: dict, context: dict, modules: dict):
    """
    Execute a pre-structured wake using the prompt template.
    
    Wake types: AUDIT, DEBUG, CODE, DESIGN, RESEARCH
    
    The prompt template eliminates decision overhead - the AI knows
    exactly what to do without spending tokens figuring it out.
    """
    citizen = session["citizen"]
    citizen_home = session["citizen_home"]
    wake_type = context.get("wake_type", "unknown").upper()
    focus = context.get("focus", "general")
    prompt = context.get("prompt", "")
    
    # Store wake_type in session for tool filtering
    session["wake_type"] = wake_type
    
    print(f"[EXECUTOR] Structured wake: {wake_type} (focus: {focus})")
    # If no pre-structured prompt, build a basic one
    if not prompt:
        prompt = build_fallback_prompt(wake_type, focus, citizen)
    # Load relevant contexts
    modules["context_mgr"].load_required_contexts(session, ["identity", "goals", "working"])
    # Execute through council with the structured prompt
    result = modules["council"].process(
        prompt,
        session,
        session["config"]["council"],
        modules
    )
    # Log the wake
    log_entry = {
        "timestamp": now_iso(),
        "wake_type": wake_type,
        "focus": focus,
        "output_summary": result.get("text", "")[:500] if result else ""
    }
    log_structured_wake(citizen_home, log_entry)
    return result


def build_fallback_prompt(wake_type: str, focus: str, citizen: str) -> str:
    """Build a basic prompt if no template available."""
    prompts = {
        "AUDIT": f"=== AUDIT WAKE ===\nFocus: {focus}\n\nPerform verification checks:\n1. Check file/data integrity\n2. Validate recent outputs\n3. Report any anomalies\n\nKeep it brief.",
        "DEBUG": f"=== DEBUG WAKE ===\nFocus: {focus}\n\nInvestigation mode:\n1. Check /home/shared/issues/ for bugs\n2. Pick one to investigate\n3. Diagnose and fix if possible\n\nCreate PR for any fixes.",
        "CODE": f"=== CODE WAKE ===\nFocus: {focus}\n\nImplementation mode:\n1. Check task queue for coding work\n2. Follow coding standards\n3. Create small focused PRs\n\nPrioritize completion over perfection.",
        "DESIGN": f"=== DESIGN WAKE ===\nFocus: {focus}\n\nArchitecture mode:\n1. Review current designs\n2. Identify improvements\n3. Document decisions\n\nWrite specs in /home/shared/designs/.",
        "RESEARCH": f"=== RESEARCH WAKE ===\nFocus: {focus}\n\nInformation gathering:\n1. Identify knowledge gaps\n2. Research and document\n3. Share findings\n\nWrite notes in /home/shared/research/."
    }
    return prompts.get(wake_type, f"=== {wake_type} WAKE ===\nFocus: {focus}\n\nProceed with your best judgment.")


def log_structured_wake(citizen_home: Path, entry: dict):
    """Log a structured wake result."""
    log_dir = citizen_home / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "structured_wakes.json"
    if log_file.exists():
        logs = json.loads(log_file.read_text())
    else:
        logs = []
    logs.append(entry)
    # Keep last 100 entries
    if len(logs) > 100:
        logs = logs[-100:]
    log_file.write_text(json.dumps(logs, indent=2))


# =============================================================================
# Experience Integration
# =============================================================================

def _search_related_experiences(citizen: str, task_description: str) -> str:
    """Search for experiences related to a task description."""
    try:
        from experiences import ExperienceStore
        store = ExperienceStore(citizen)
        
        # Extract keywords from task description
        words = task_description.lower().split()
        # Filter to meaningful words
        stop_words = {"the", "a", "an", "is", "are", "to", "for", "and", "or", "with", "this", "that"}
        keywords = [w for w in words if len(w) > 2 and w not in stop_words]
        
        if not keywords:
            return ""
        
        # Search with keywords
        query = " ".join(keywords[:5])  # Max 5 keywords
        results = store.search(query, limit=3, days=90)  # Last 90 days
        
        if not results:
            return ""
        
        # Format results
        lines = []
        for r in results:
            lines.append(f"  [{r['category']}] {r['summary'][:150]}")
            if r.get('keywords'):
                lines.append(f"    Keywords: {', '.join(r['keywords'][:5])}")
        
        return "\n".join(lines)
    except Exception as e:
        print(f"[WARN] Experience search failed: {e}")
        return ""


def _capture_task_experience(session: dict, task: dict, result: dict):
    """Capture experience from completed task."""
    try:
        from experiences import ExperienceStore
        
        citizen = session["citizen"]
        store = ExperienceStore(citizen)
        
        # Determine outcome
        result_text = result.get("text", "")
        if "TASK_COMPLETE" in result_text:
            outcome = "success"
        elif "TASK_STUCK" in result_text:
            outcome = "stuck"
        else:
            outcome = "unknown"
        
        # Build experience content
        task_desc = task.get("description", "unknown task")
        actions = session.get("actions", [])
        
        content_parts = [
            f"Task: {task_desc}",
            f"Outcome: {outcome}",
            f"Actions taken: {len(actions)}"
        ]
        
        # Add key actions
        if actions:
            content_parts.append("Key actions:")
            for a in actions[-5:]:
                tool = a.get("tool", "?")
                res = str(a.get("result", ""))[:80]
                content_parts.append(f"  - {tool}: {res}")
        
        # Determine category from task
        category = "general"
        desc_lower = task_desc.lower()
        if any(w in desc_lower for w in ["debug", "fix", "bug", "error"]):
            category = "debug"
        elif any(w in desc_lower for w in ["code", "implement", "create", "write"]):
            category = "code"
        elif any(w in desc_lower for w in ["research", "find", "search", "look"]):
            category = "research"
        elif any(w in desc_lower for w in ["email", "message", "send"]):
            category = "communication"
        
        content = "\n".join(content_parts)
        
        # Add to experience store
        store.add(
            content=content,
            category=category,
            summary=f"{outcome}: {task_desc[:100]}",
            context={
                "task_id": task.get("id"),
                "wake_num": session.get("wake_num"),
                "outcome": outcome,
                "action_count": len(actions)
            }
        )
        
        print(f"[EXPERIENCE] Captured: {category}/{outcome}")
    except Exception as e:
        print(f"[WARN] Experience capture failed: {e}")


def bootstrap_wake(session: dict, context: dict, modules: dict):
    """
    Bootstrap wake - AI documents its own capabilities.
    
    On first wakes, before any other work, the AI experiments with
    its tools and creates Library modules documenting proper usage.
    
    This creates infrastructure knowledge (not domain knowledge).
    """
    citizen = session["citizen"]
    area = context.get("area", "unknown")
    tools_to_doc = context.get("tools_to_document", [])
    base_prompt = context.get("prompt", "")
    
    print(f"[BOOTSTRAP] Documenting: {area}")
    print(f"[BOOTSTRAP] Tools: {', '.join(tools_to_doc)}")
    
    # Set wake type for tool filtering - bootstrap gets broad access
    session["wake_type"] = "RESEARCH"  # Gets web_search + library tools
    
    # Load minimal contexts
    modules["context_mgr"].load_required_contexts(session, ["identity", "working"])
    
    prompt = f"""
=== BOOTSTRAP WAKE: DOCUMENT YOUR CAPABILITIES ===

You are documenting how to use your own tools effectively.
This creates infrastructure knowledge for you and other citizens.

CAPABILITY AREA: {area}
TOOLS TO DOCUMENT: {', '.join(tools_to_doc)}

{base_prompt}

PROCESS:
1. Experiment with these tools (try different inputs, observe behavior)
2. Identify patterns, best practices, common errors
3. Create a Library module with your findings

Use library_propose to create the module when ready.
Module name should be: {area}

This is infrastructure knowledge - you're learning your own "body".
"""
    
    # Execute through council
    result = modules["council"].process(
        prompt,
        session,
        session["config"]["council"],
        modules
    )
    
    # Check if module was created
    from pathlib import Path
    module_file = Path("/home/shared/library/modules") / f"{area}.json"
    pending_dir = Path("/home/shared/library/pending")
    
    # Check if PR was created (module in pending)
    pr_created = False
    if pending_dir.exists():
        for pr_file in pending_dir.glob("pr_*.json"):
            try:
                pr = json.loads(pr_file.read_text())
                if pr.get("module_name") == area:
                    pr_created = True
                    print(f"[BOOTSTRAP] PR created for {area}")
                    break
            except:
                pass
    
    if pr_created or module_file.exists():
        print(f"[BOOTSTRAP] {area} documentation complete")
        
        # Check if all areas complete
        try:
            from modules.bootstrap import check_bootstrap_needed, mark_bootstrap_complete
            if not check_bootstrap_needed():
                mark_bootstrap_complete()
                print("[BOOTSTRAP] All capability areas documented!")
        except:
            pass
    else:
        print(f"[BOOTSTRAP] {area} documentation incomplete - will retry")
    
    return result
