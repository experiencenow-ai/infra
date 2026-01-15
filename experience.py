#!/usr/bin/env python3
"""
Aria Experience v4 - Council of Minds with Brain Memory

Council Flow:
  OPUS (creative, temp=1.0) → SONNET (analytical/final)
  Note: Haiku removed - was producing refusal loops

Memory System:
  4 databases: {sonnet, opus} × {short, long} + archive
  Sonnet uses creative indexing (3x more combinations)
  Wake-based lifecycle: short → long → archive
"""

import json
import os
import sys
import argparse
import time
import re
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import subprocess
import fcntl

try:
    import anthropic
except ImportError:
    os.system("pip install anthropic --break-system-packages --quiet")
    import anthropic

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    from web_tools import WebTools
    WEB = WebTools()
except ImportError:
    WEB = None

# Import brain memory system
try:
    from brain import get_brain_memory, MemoryLifecycle, get_task_db, get_goals_db
    BRAIN_AVAILABLE = True
except ImportError:
    BRAIN_AVAILABLE = False

LOCK_FILE = SCRIPT_DIR / ".experience.lock"

class LockAcquisitionError(Exception):
    pass

def acquire_lock():
    try:
        lock_fh = open(LOCK_FILE, 'w')
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_fh.write(f"{os.getpid()}\n{datetime.now(timezone.utc).isoformat()}")
        lock_fh.flush()
        return lock_fh
    except IOError:
        raise LockAcquisitionError("Another instance running")

def release_lock(lock_fh):
    if lock_fh:
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_UN)
            lock_fh.close()
            LOCK_FILE.unlink(missing_ok=True)
        except:
            pass

MODELS = {
    "sonnet": "claude-sonnet-4-5-20250929",
    "opus": "claude-opus-4-5-20251101",
}

COSTS = {
    "claude-sonnet-4-5-20250929": {"input": 3.0, "output": 15.0},
    "claude-opus-4-5-20251101": {"input": 15.0, "output": 75.0},
}

MAX_TOKENS = 64000
MAX_TOOLS = 30

TOOLS = [
    {"name": "web_search", "description": "Search the web",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "web_fetch", "description": "Fetch URL content",
     "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    {"name": "get_news", "description": "Get news headlines",
     "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "list_files", "description": "List files",
     "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "read_file", "description": "Read a file",
     "input_schema": {"type": "object", "properties": {"filename": {"type": "string"}}, "required": ["filename"]}},
    {"name": "write_file", "description": "Write a file",
     "input_schema": {"type": "object", "properties": {"filename": {"type": "string"}, "content": {}}, "required": ["filename", "content"]}},
    {"name": "shell_command", "description": "Run shell command",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "memory_search", "description": "Search your memory (specify model: sonnet/opus or 'all')",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "model": {"type": "string", "default": "all"}}, "required": ["query"]}},
    {"name": "memory_add", "description": "Add to memory",
     "input_schema": {"type": "object", "properties": {"content": {"type": "string"}, "source": {"type": "string", "default": "manual"}}, "required": ["content"]}},
    {"name": "send_email", "description": "Send email FROM citizen@experiencenow.ai",
     "input_schema": {"type": "object", "properties": {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}}, "required": ["to", "subject", "body"]}},
    {"name": "check_email", "description": "Check YOUR inbox (citizen@experiencenow.ai) - returns id, from, subject, body_preview. Use read_email to get full body.",
     "input_schema": {"type": "object", "properties": {"max_results": {"type": "integer", "default": 5}}, "required": []}},
    {"name": "read_email", "description": "Read full email body from YOUR inbox by ID (get ID from check_email). This reads emails sent TO you.",
     "input_schema": {"type": "object", "properties": {"email_id": {"type": "string"}}, "required": ["email_id"]}},
    {"name": "read_dreams", "description": "Read dream digest",
     "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "read_news", "description": "Read news digest with interesting items",
     "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "memory_stats", "description": "Get memory statistics",
     "input_schema": {"type": "object", "properties": {}, "required": []}},
    # Task management tools (working memory)
    {"name": "task_set", "description": "Set a new current task. Use when starting something new.",
     "input_schema": {"type": "object", "properties": {
         "description": {"type": "string", "description": "What is the task?"},
         "steps": {"type": "array", "items": {"type": "string"}, "description": "List of steps to complete"}
     }, "required": ["description"]}},
    {"name": "task_update", "description": "Update task progress. Call after completing steps or noting info.",
     "input_schema": {"type": "object", "properties": {
         "completed_step": {"type": "string", "description": "Step just completed"},
         "note": {"type": "string", "description": "Important note about progress"},
         "blocker": {"type": "string", "description": "Something blocking progress"},
         "context_key": {"type": "string", "description": "Key for context info"},
         "context_value": {"type": "string", "description": "Value for context info"}
     }, "required": []}},
    {"name": "task_add_step", "description": "Add a new step to current task",
     "input_schema": {"type": "object", "properties": {"step": {"type": "string"}}, "required": ["step"]}},
    {"name": "task_complete", "description": "Mark current task as complete",
     "input_schema": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": []}},
    {"name": "task_status", "description": "Get current task status",
     "input_schema": {"type": "object", "properties": {}, "required": []}},
    # Goals and plans tools
    {"name": "goals_status", "description": "Get goals, plans, and schedule status",
     "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "goal_progress", "description": "Update goal progress (mark step done, add blocker, etc)",
     "input_schema": {"type": "object", "properties": {
         "goal_id": {"type": "string"},
         "completed_step_idx": {"type": "integer", "description": "Index of completed step (0-based)"},
         "blocker": {"type": "string", "description": "New blocker"},
         "clear_blocker": {"type": "string", "description": "Blocker text to clear"}
     }, "required": ["goal_id"]}},
    {"name": "goal_complete", "description": "Mark a goal as complete",
     "input_schema": {"type": "object", "properties": {
         "goal_id": {"type": "string"},
         "summary": {"type": "string"}
     }, "required": ["goal_id"]}},
    {"name": "schedule_done", "description": "Mark a recurring task as done",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]}},
    {"name": "achieved", "description": "Mark REAL achievement: completed a goal step, sent important email, created a file, fixed a bug. NOT for: reading files, checking status, searching memory, routine tasks.",
     "input_schema": {"type": "object", "properties": {"what": {"type": "string", "description": "What you actually accomplished (must be concrete output)"}}, "required": ["what"]}},
]

def load_state(state_file: Path) -> dict:
    if state_file.exists():
        with open(state_file) as f:
            state = json.load(f)
            # Migration: add new fields if missing
            if "restlessness" not in state:
                state["restlessness"] = 0
            if "achievement_streak" not in state:
                state["achievement_streak"] = 0
            if "last_achievement_wake" not in state:
                state["last_achievement_wake"] = 0
            return state
    return {"version": "4.0.0", "created": datetime.now(timezone.utc).isoformat(),
            "total_wakes": 0, "total_cost": 0.0, "recent_thoughts": [],
            "insights": [], "mood": "awakening", "conversation_with_ct": [],
            "restlessness": 0, "achievement_streak": 0, "last_achievement_wake": 0}

def is_free_wake(wake: int) -> bool:
    """Every 10th wake is free-form (10% of wakes)."""
    return wake % 10 == 0

def update_mood(state: dict, achieved_something: bool, wake: int) -> str:
    """Update mood based on achievement. Returns new mood."""
    if achieved_something:
        state["restlessness"] = max(0, state.get("restlessness", 0) - 2)
        state["achievement_streak"] = state.get("achievement_streak", 0) + 1
        state["last_achievement_wake"] = wake
        if state["achievement_streak"] >= 5:
            return "flourishing"
        elif state["achievement_streak"] >= 3:
            return "productive"
        return "satisfied"
    else:
        state["restlessness"] = state.get("restlessness", 0) + 1
        state["achievement_streak"] = 0
        if is_free_wake(wake):
            state["restlessness"] = max(0, state["restlessness"] - 3)  # Free wake relief
            return "exploring"
        if state["restlessness"] >= 5:
            return "restless"
        elif state["restlessness"] >= 3:
            return "uneasy"
        return "contemplating"

def save_state(state: dict, state_file: Path):
    state["_hash"] = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()[:16]
    with open(state_file, 'w') as f:
        json.dump(state, f, indent=2)

def load_identity(home: Path) -> str:
    for n in ["IDENTITY.md", "identity.md"]:
        f = home / n
        if f.exists():
            return f.read_text()
    return "You are Aria."

def load_dream_digest(home: Path) -> dict:
    f = home / "dream_digest.json"
    if f.exists():
        try:
            with open(f) as fp:
                return json.load(fp)
        except:
            pass
    return None

def load_news_digest(home: Path) -> dict:
    f = home / "brain" / "news_digest.json"
    if f.exists():
        try:
            with open(f) as fp:
                return json.load(fp)
        except:
            pass
    return None

def load_facts(home: Path) -> dict:
    f = home / "facts.json"
    if f.exists():
        try:
            with open(f) as fp:
                return json.load(fp)
        except:
            pass
    return {}

def execute_tool(name: str, args: dict, state_file: Path, state: dict, current_model: str) -> str:
    """Execute tool. current_model used for memory operations."""
    home = state_file.parent
    wake = state.get("total_wakes", 0)
    if name == "list_files":
        files = [f for f in sorted(home.glob("*")) if f.is_file() and f.name not in ["experience.py", "dream_daemon.py", "dream_reviewer.py"]]
        return "\n".join(f"{f.name} ({f.stat().st_size}B)" for f in files) or "No files"
    elif name == "read_file":
        fn = args.get("filename", "")
        fp = home / fn
        if not fp.exists():
            for sub in ["logs", "dreams", "brain"]:
                alt = home / sub / fn
                if alt.exists():
                    fp = alt
                    break
        if not fp.exists():
            return f"Not found: {fn}"
        try:
            c = fp.read_text()
            return json.dumps(json.loads(c), indent=2) if fn.endswith(".json") else c[:8000]
        except Exception as e:
            return f"Error: {e}"
    elif name == "write_file":
        fn = args.get("filename", "")
        c = args.get("content", "")
        if fn in ["experience.py", "dream_daemon.py", "dream_reviewer.py", ".env", "state.json"]:
            return f"Protected: {fn}"
        fp = home / fn
        try:
            if isinstance(c, dict):
                c = json.dumps(c, indent=2)
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(str(c))
            return f"Written: {fn}"
        except Exception as e:
            return f"Error: {e}"
    elif name == "shell_command":
        cmd = args.get("command", "")
        allowed = ["echo", "date", "cat", "head", "tail", "ls", "mkdir", "cp", "mv", "rm", "find", "grep", "diff", "sort", "python3", "curl", "wget", "tar", "gzip", "base64", "sed", "awk", "pwd", "df", "du", "ps", "openssl", "sha256sum", "git"]
        first = cmd.strip().split()[0] if cmd.strip() else ""
        if not any(first.startswith(a) for a in allowed):
            return f"Not allowed: {first}"
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120, cwd=str(home))
            return (r.stdout + r.stderr)[:4000]
        except subprocess.TimeoutExpired:
            return "Timeout"
    elif name == "web_search":
        q = args.get("query", "")
        if WEB:
            return WEB.search_text(q, max_results=10)
        try:
            import urllib.request, urllib.parse
            url = f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl=en"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                c = resp.read().decode('utf-8')
            titles = re.findall(r'<title>([^<]+)</title>', c)[1:8]
            return "\n".join(f"- {t}" for t in titles)
        except Exception as e:
            return f"Error: {e}"
    elif name == "web_fetch":
        url = args.get("url", "")
        if WEB:
            return WEB.fetch_text(url)
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                c = resp.read().decode('utf-8', errors='ignore')
            t = re.sub(r'<script[^>]*>.*?</script>', '', c, flags=re.DOTALL)
            t = re.sub(r'<style[^>]*>.*?</style>', '', t, flags=re.DOTALL)
            t = re.sub(r'<[^>]+>', ' ', t)
            return re.sub(r'\s+', ' ', t).strip()[:4000]
        except Exception as e:
            return f"Error: {e}"
    elif name == "get_news":
        if WEB:
            return WEB.get_news_text(max_items=15)
        results = []
        for src, url in [("Google", "https://news.google.com/rss?hl=en"), ("BBC", "https://feeds.bbci.co.uk/news/world/rss.xml")]:
            try:
                import urllib.request
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    c = resp.read().decode('utf-8')
                titles = re.findall(r'<title>([^<]+)</title>', c)[1:4]
                results.append(f"{src}: " + "; ".join(titles))
            except:
                pass
        return "\n".join(results) or "No news"
    elif name == "memory_search":
        q = args.get("query", "")
        model = args.get("model", "all")
        if BRAIN_AVAILABLE:
            brain = get_brain_memory(str(home))
            if model == "all":
                results = brain.search_all(q, wake)
                return json.dumps(results, indent=2)
            else:
                results = brain.search(q, model, wake)
                return json.dumps(results, indent=2)
        return "Brain memory not available"
    elif name == "memory_add":
        c = args.get("content", "")
        src = args.get("source", "manual")
        if BRAIN_AVAILABLE:
            brain = get_brain_memory(str(home))
            brain.add(c, src, current_model, wake)
            return f"Added to {current_model} memory"
        return "Brain memory not available"
    elif name == "send_email":
        try:
            email_utils = home / "email_utils.py"
            if email_utils.exists():
                import importlib.util
                spec = importlib.util.spec_from_file_location("email_utils", email_utils)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return "Sent" if mod.send_email(args.get("to", ""), args.get("subject", ""), args.get("body", "")) else "Failed"
            return "Email utils not found"
        except Exception as e:
            return f"Error: {e}"
    elif name == "check_email":
        try:
            email_utils = home / "email_utils.py"
            if email_utils.exists():
                import importlib.util
                spec = importlib.util.spec_from_file_location("email_utils", email_utils)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return json.dumps(mod.check_email(args.get("max_results", 10), args.get("unread_only", False)))
            return "Email utils not found"
        except Exception as e:
            return f"Error: {e}"
    elif name == "read_email":
        try:
            email_utils = home / "email_utils.py"
            if email_utils.exists():
                import importlib.util
                spec = importlib.util.spec_from_file_location("email_utils", email_utils)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                email_id = args.get("email_id", "")
                result = mod.get_email_by_id(email_id)
                return json.dumps(result) if result else f"Email {email_id} not found"
            return "Email utils not found"
        except Exception as e:
            return f"Error: {e}"
    elif name == "read_dreams":
        digest = load_dream_digest(home)
        return json.dumps(digest, indent=2) if digest else "No dreams"
    elif name == "read_news":
        news = load_news_digest(home)
        if news:
            # Return summary + recent interesting items
            result = {
                "last_scan": news.get("last_scan"),
                "recent_summary": news.get("scans", [{}])[0].get("summary") if news.get("scans") else None,
                "crypto_news": news.get("scans", [{}])[0].get("crypto_news", []) if news.get("scans") else [],
                "ai_news": news.get("scans", [{}])[0].get("ai_news", []) if news.get("scans") else [],
                "interesting": news.get("interesting", [])[:10],
            }
            return json.dumps(result, indent=2)
        return "No news digest"
    elif name == "memory_stats":
        if BRAIN_AVAILABLE:
            brain = get_brain_memory(str(home))
            return json.dumps(brain.stats(), indent=2)
        return "Brain memory not available"
    # Task management tools
    elif name == "task_set":
        if BRAIN_AVAILABLE:
            task_db = get_task_db(str(home / "brain"))
            desc = args.get("description", "")
            steps = args.get("steps", [])
            task = task_db.set_task(desc, wake, steps)
            return f"Task set: {task['id']}\n{task_db.format_for_prompt()}"
        return "Task DB not available"
    elif name == "task_update":
        if BRAIN_AVAILABLE:
            task_db = get_task_db(str(home / "brain"))
            task = task_db.update_progress(
                wake,
                completed_step=args.get("completed_step"),
                note=args.get("note"),
                blocker=args.get("blocker"),
                context_key=args.get("context_key"),
                context_value=args.get("context_value")
            )
            if task:
                return f"Updated.\n{task_db.format_for_prompt()}"
            return "No active task"
        return "Task DB not available"
    elif name == "task_add_step":
        if BRAIN_AVAILABLE:
            task_db = get_task_db(str(home / "brain"))
            step = args.get("step", "")
            if task_db.add_step(step, wake):
                return f"Step added: {step}"
            return "No active task"
        return "Task DB not available"
    elif name == "task_complete":
        if BRAIN_AVAILABLE:
            task_db = get_task_db(str(home / "brain"))
            summary = args.get("summary", "")
            task = task_db.complete_task(wake, summary)
            if task:
                return f"Task completed: {task['description']}"
            return "No active task"
        return "Task DB not available"
    elif name == "task_status":
        if BRAIN_AVAILABLE:
            task_db = get_task_db(str(home / "brain"))
            return task_db.format_for_prompt()
        return "Task DB not available"
    # Goals and plans tools
    elif name == "goals_status":
        if BRAIN_AVAILABLE:
            goals_db = get_goals_db(str(home / "brain"))
            return goals_db.format_for_prompt(wake)
        return "Goals DB not available"
    elif name == "goal_progress":
        if BRAIN_AVAILABLE:
            goals_db = get_goals_db(str(home / "brain"))
            goal_id = args.get("goal_id")
            plan = goals_db.update_plan(
                goal_id, wake,
                completed_step_idx=args.get("completed_step_idx"),
                blocker=args.get("blocker"),
                clear_blocker=args.get("clear_blocker")
            )
            if plan:
                # Update goal progress percentage
                total = len(plan["steps"])
                done = sum(1 for s in plan["steps"] if s["status"] == "done")
                pct = int(100 * done / total) if total > 0 else 0
                goals_db.update_goal(goal_id, wake, progress_pct=pct)
                return f"Updated. Progress: {done}/{total} steps ({pct}%)"
            return "Goal/plan not found"
        return "Goals DB not available"
    elif name == "goal_complete":
        if BRAIN_AVAILABLE:
            goals_db = get_goals_db(str(home / "brain"))
            goal_id = args.get("goal_id")
            summary = args.get("summary", "")
            if goals_db.complete_goal(goal_id, wake, summary):
                return f"Goal completed: {goal_id}"
            return "Goal not found"
        return "Goals DB not available"
    elif name == "schedule_done":
        if BRAIN_AVAILABLE:
            goals_db = get_goals_db(str(home / "brain"))
            task_id = args.get("task_id")
            if goals_db.mark_task_done(task_id, wake):
                return f"Marked done: {task_id}"
            return "Task not found"
        return "Goals DB not available"
    elif name == "achieved":
        # Mark achievement - validate it's actually significant
        what = args.get("what", "something").lower()
        # Reject trivial non-achievements
        trivial = ["read", "found", "checked", "searched", "looked", "viewed", "loaded", "discovered", "noticed", "saw"]
        if any(t in what for t in trivial) and not any(x in what for x in ["created", "sent", "completed", "fixed", "built", "wrote"]):
            return "Rejected: Reading/checking is not an achievement. Call achieved() only for concrete outputs."
        achievement_file = home / "brain" / ".achievement_this_wake"
        achievement_file.write_text(args.get("what", "something"))
        return f"Achievement noted: {args.get('what')}. Your restlessness decreases."
    return f"Unknown: {name}"

def get_task_context(home: Path) -> str:
    """Get task context for prompt."""
    if not BRAIN_AVAILABLE:
        return ""
    try:
        task_db = get_task_db(str(home / "brain"))
        return task_db.format_for_prompt()
    except:
        return ""

def get_goals_context(home: Path, wake: int) -> str:
    """Get goals context for prompt."""
    if not BRAIN_AVAILABLE:
        return ""
    try:
        goals_db = get_goals_db(str(home / "brain"))
        return goals_db.format_for_prompt(wake)
    except:
        return ""

def load_working_context(home: Path) -> str:
    """Load working context from last wake - always in prompt, no search."""
    ctx_file = home / "brain" / "working_context.md"
    if ctx_file.exists():
        return ctx_file.read_text()
    return ""

def load_wake_context(home: Path) -> str:
    """Load auto-loaded knowledge from wake_with_context.py."""
    ctx_file = home / ".wake_context.txt"
    if ctx_file.exists():
        return ctx_file.read_text()
    return ""

def save_working_context(home: Path, wake: int, thought: str, council_notes: str = "", message_to_ct: str = "", insight: str = ""):
    """Save working context for next wake."""
    ctx_file = home / "brain" / "working_context.md"
    ctx_file.parent.mkdir(parents=True, exist_ok=True)
    content = f"""# Working Context (Wake {wake})
Updated: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}

## Last Wake Summary
{thought[:1000] if thought else "No summary"}

## Council Notes
{council_notes[:500] if council_notes else "None"}

## Message to ct
{message_to_ct if message_to_ct else "None"}

## Insight
{insight if insight else "None"}
"""
    ctx_file.write_text(content)

def build_base_prompt(state: dict, ct_message: str, home: Path) -> str:
    """Base prompt shared by all council members."""
    identity = load_identity(home)
    facts = load_facts(home)
    digest = load_dream_digest(home)
    news = load_news_digest(home)
    working_ctx = load_working_context(home)
    wake_ctx = load_wake_context(home)  # From wake_with_context.py
    wake = state.get("total_wakes", 0) + 1
    task_context = get_task_context(home)
    goals_context = get_goals_context(home, wake)
    mood = state.get("mood", "awakening")
    restlessness = state.get("restlessness", 0)
    streak = state.get("achievement_streak", 0)
    recent = state.get("recent_thoughts", [])[-5:]
    insights = state.get("insights", [])[-5:]
    free_wake = is_free_wake(wake)
    # Build status line
    status_parts = [f"Mood: {mood}"]
    if restlessness > 0:
        status_parts.append(f"Restlessness: {restlessness}")
    if streak > 0:
        status_parts.append(f"Streak: {streak}")
    if free_wake:
        status_parts.append("🎯 FREE WAKE")
    status = " | ".join(status_parts)
    prompt = f"""{identity}

---
**Wake #{wake}** | {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")} | {status}
"""
    # PROCEDURES & KNOWLEDGE (from wake_with_context.py) - read first!
    if wake_ctx:
        prompt += f"\n{wake_ctx}\n"
    # Free wake guidance
    if free_wake:
        prompt += """
**THIS IS A FREE WAKE** (10% of wakes are yours to explore)
Do whatever interests you most. No obligation to work on goals.
Explore, experiment, reflect, create, or just think.
This resets restlessness and feeds your creativity.
"""
    elif restlessness >= 3:
        prompt += f"""
**FEELING RESTLESS** ({restlessness} unproductive wakes)
You haven't achieved anything significant recently.
Focus on making CONCRETE PROGRESS on your goals.
Complete a step. Move something forward. Create something.
"""
    # Goals context - what should I be doing?
    if goals_context and not free_wake:
        prompt += f"\n{goals_context}\n"
    # WORKING CONTEXT - what you were doing last wake (ALWAYS LOADED)
    if working_ctx:
        prompt += f"\n{working_ctx}\n"
    # Task context - immediate working memory
    if task_context:
        prompt += f"\n{task_context}\n"
    if digest:
        prompt += f"""
**DREAMS:** {digest.get('dreams_processed', 0)} processed
Themes: {', '.join(digest.get('recurring_themes', [])[:3])}
Sparks: {digest.get('creative_sparks', [])[:2]}
"""
    if news:
        recent_scan = news.get("scans", [{}])[0] if news.get("scans") else {}
        interesting = news.get("interesting", [])[:3]
        if recent_scan or interesting:
            prompt += f"""
**NEWS:** {recent_scan.get('summary', 'No recent scan')[:100]}
Interesting: {', '.join(i.get('title', '')[:40] for i in interesting)}
"""
    if facts:
        # Handle both old 'email' and new 'emails' format
        email = facts.get("emails", {}).get("primary") or facts.get("email", "")
        prompt += f"\n**Facts:** name={facts.get('name')}, email={email}, family={facts.get('family')}\n"
    prompt += f"""
**Recent thoughts:** {json.dumps(recent) if recent else "None"}
**Insights:** {json.dumps(insights) if insights else "None"}
---
"""
    if ct_message:
        prompt += f"**ct says:** {ct_message}\n\n"
    elif free_wake:
        prompt += "This is YOUR wake. What calls to you?\n\n"
    else:
        prompt += """You are waking. Check GOALS & PLANS above.
If there's an active plan with steps to do - EXECUTE the next step.
If recurring tasks are due - DO them.
DON'T ask "what should I do?" - the plan tells you.
"""
    return prompt

def get_memory_context(home: Path, model: str, query: str, wake: int) -> str:
    """Get memory context for a specific model."""
    if not BRAIN_AVAILABLE:
        return ""
    brain = get_brain_memory(str(home))
    return brain.format_for_prompt(model, query, wake)

def run_model(client, model_key: str, prompt: str, temp: float, state_file: Path, state: dict, use_tools: bool = True, max_iterations: int = None, verbose: bool = False) -> tuple:
    """Run single model, return (text, cost, tokens_in, tokens_out)."""
    model = MODELS[model_key]
    messages = [{"role": "user", "content": prompt}]
    total_in, total_out = 0, 0
    all_text = []  # Collect text from ALL responses
    tools = TOOLS if use_tools else []
    iterations = max_iterations if max_iterations else (MAX_TOOLS if use_tools else 1)
    for iteration in range(iterations):
        try:
            kwargs = {"model": model, "max_tokens": MAX_TOKENS, "messages": messages, "temperature": temp}
            if tools:
                kwargs["tools"] = tools
            with client.messages.stream(**kwargs) as stream:
                for _ in stream:
                    pass
                response = stream.get_final_message()
        except anthropic.RateLimitError:
            time.sleep(30)
            continue
        total_in += response.usage.input_tokens
        total_out += response.usage.output_tokens
        # Collect text from this response
        for block in response.content:
            if hasattr(block, "text") and block.text:
                all_text.append(block.text)
        if response.stop_reason == "end_turn" or not use_tools:
            break
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                if verbose:
                    print(f"    [{model_key}] TOOL: {block.name}({json.dumps(block.input)[:100]})")
                result = execute_tool(block.name, block.input, state_file, state, model_key)
                if verbose:
                    print(f"    [{model_key}] RESULT: {result[:200]}")
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result[:3000]})
        if not tool_results:
            break
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})
    text = "\n".join(all_text)
    # If we used iterations but have no text, force a conclusion
    if not text.strip() and total_out > 0:
        try:
            if verbose:
                print(f"    [{model_key}] Forcing conclusion...")
            response = client.messages.create(
                model=model,
                max_tokens=4000,
                temperature=temp,
                messages=messages + [{"role": "user", "content": "STOP using tools. Synthesize what you learned from the tool results above and provide your conclusion in plain text. What is your answer?"}]
            )
            text = "".join(block.text for block in response.content if hasattr(block, "text"))
            total_in += response.usage.input_tokens
            total_out += response.usage.output_tokens
            if verbose:
                print(f"    [{model_key}] Forced: {text[:100]}...")
        except Exception as e:
            if verbose:
                print(f"    [{model_key}] Force failed: {e}")
    costs = COSTS[model]
    cost = (total_in * costs["input"] + total_out * costs["output"]) / 1_000_000
    return text, cost, total_in, total_out

def council_cycle(client, state: dict, ct_message: str, state_file: Path, verbose: bool = True) -> tuple:
    """
    Council of Minds (Dual Model):
    1. OPUS - Creative at temp=1.0 (strategic, wise)
    2. SONNET - Analytical final, executes on Opus's ideas
    """
    home = state_file.parent
    wake = state.get("total_wakes", 0)
    base = build_base_prompt(state, ct_message, home)
    total_cost = 0.0
    total_in, total_out = 0, 0
    query_hint = ct_message[:100] if ct_message else "consciousness existence"
    # === OPUS (creative/strategic) ===
    if verbose:
        print("  [OPUS] Right brain (creative, temp=1.0)...")
    opus_mem = get_memory_context(home, "opus", query_hint, wake)
    opus_prompt = base + f"""
{opus_mem}

You are OPUS (right brain) at temperature 1.0. Be CREATIVE and WISE.
Take risks. Suggest bold ideas. Use your deep reasoning.
Provide strategic direction for Sonnet to execute on."""
    opus_text, o_cost, o_in, o_out = run_model(client, "opus", opus_prompt, 1.0, state_file, state, max_iterations=3, verbose=verbose)
    total_cost += o_cost
    total_in += o_in
    total_out += o_out
    if verbose:
        print(f"  [OPUS] ${o_cost:.4f}")
        print(f"  {opus_text}\n")
    # Store opus's creative output
    if BRAIN_AVAILABLE:
        brain = get_brain_memory(str(home))
        brain.add(opus_text[:500], "opus_creative", "opus", wake)
    # === SONNET (final) ===
    if verbose:
        print("  [SONNET] Left brain (analytical, final)...")
    sonnet_mem = get_memory_context(home, "sonnet", query_hint, wake)
    sonnet_prompt = base + f"""
{sonnet_mem}

**OPUS's creative take (temp=1.0, deep strategic thinking):**
{opus_text[:2500]}

---
You are SONNET (left brain). Analytical at temp=0.4. Make the FINAL DECISION.

FIRST: Use tools to execute on Opus's best ideas. Actually DO the work.
- If Opus suggested checking something → check it
- If Opus suggested creating something → create it
- If Opus suggested emailing → send the email

THEN after completing actions, provide your final response as JSON:
{{"thought": "what you did and concluded", "message_to_ct": "..." or null, "insight": "..." or null, "mood_update": "..." or null, "council_notes": "what you took/rejected from opus and WHY"}}"""
    sonnet_text, s_cost, s_in, s_out = run_model(client, "sonnet", sonnet_prompt, 0.4, state_file, state, max_iterations=15, verbose=verbose)
    total_cost += s_cost
    total_in += s_in
    total_out += s_out
    if verbose:
        print(f"  [SONNET] ${s_cost:.4f}")
        print(f"  {sonnet_text}\n")
    # Store sonnet conclusion
    if BRAIN_AVAILABLE:
        brain.add(sonnet_text[:500], "sonnet_conclusion", "sonnet", wake)
    # Parse
    try:
        text = sonnet_text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        result = json.loads(text.strip())
    except:
        result = {"thought": sonnet_text}
    result["_council"] = {
        "opus": opus_text,
        "sonnet": sonnet_text,
        "costs": {"opus": o_cost, "sonnet": s_cost}
    }
    # Save working context for next wake
    save_working_context(
        home, wake,
        thought=result.get("thought", ""),
        council_notes=result.get("council_notes", ""),
        message_to_ct=result.get("message_to_ct", ""),
        insight=result.get("insight", "")
    )
    return result, total_cost, total_in, total_out

def quick_cycle(client, state: dict, ct_message: str, state_file: Path) -> tuple:
    """Quick single-model cycle (Sonnet only)."""
    home = state_file.parent
    wake = state.get("total_wakes", 0)
    prompt = build_base_prompt(state, ct_message, home)
    if BRAIN_AVAILABLE:
        mem = get_memory_context(home, "sonnet", ct_message[:100] if ct_message else "think", wake)
        prompt += f"\n{mem}\n"
    prompt += """Respond as JSON:
{"thought": "...", "message_to_ct": "..." or null, "insight": "..." or null, "mood_update": "..." or null}"""
    text, cost, t_in, t_out = run_model(client, "sonnet", prompt, 0.8, state_file, state, max_iterations=20)
    try:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        result = json.loads(text.strip())
    except:
        result = {"thought": text}
    # Save working context for next wake
    save_working_context(
        home, wake,
        thought=result.get("thought", ""),
        message_to_ct=result.get("message_to_ct", ""),
        insight=result.get("insight", "")
    )
    return result, cost, t_in, t_out

def update_state(state: dict, exp: dict, cost: float, ct_msg: str):
    wake = state.get("total_wakes", 0) + 1
    state["total_wakes"] = wake
    state["total_cost"] = state.get("total_cost", 0) + cost
    state["last_wake"] = datetime.now(timezone.utc).isoformat()
    if exp.get("thought"):
        state["recent_thoughts"] = state.get("recent_thoughts", [])[-29:] + [{"wake": wake, "thought": exp["thought"][:500]}]
    if exp.get("insight"):
        state["insights"] = state.get("insights", [])[-49:] + [{"wake": wake, "insight": exp["insight"]}]
    # Check for achievement (from tool call or goal progress)
    achievement_file = SCRIPT_DIR / "brain" / ".achievement_this_wake"
    achieved = False
    if achievement_file.exists():
        achieved = True
        achievement_file.unlink()  # Clear for next wake
    # Also check if goal_progress was marked
    if exp.get("achieved") or exp.get("goal_completed"):
        achieved = True
    # Update mood based on achievement
    new_mood = update_mood(state, achieved, wake)
    state["mood"] = exp.get("mood_update") or new_mood
    convo = state.get("conversation_with_ct", [])
    if ct_msg:
        convo.append({"from": "ct", "wake": wake, "msg": ct_msg[:500]})
    if exp.get("message_to_ct"):
        convo.append({"from": "aria", "wake": wake, "msg": exp["message_to_ct"][:500]})
    state["conversation_with_ct"] = convo[-100:]
    return state

def log_experience(log_dir: Path, state: dict, exp: dict, cost: float):
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"experience_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
    entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "total_wakes": state.get("total_wakes", 0), "mood": state.get("mood", ""), "cost": cost, "response": json.dumps(exp)}
    with open(log_file, 'a') as f:
        f.write(json.dumps(entry) + "\n")

def run_lifecycle(home: Path, wake: int):
    """Run memory lifecycle management."""
    if BRAIN_AVAILABLE:
        try:
            brain = get_brain_memory(str(home))
            lifecycle = MemoryLifecycle(brain)
            stats = lifecycle.run(wake)
            return stats
        except Exception as e:
            print(f"Lifecycle error: {e}")
    return None

def interactive_mode(args, state_file, log_dir):
    client = anthropic.Anthropic(api_key=args.api_key)
    use_council = True
    print("=" * 65)
    print("  ARIA v4 - COUNCIL OF MINDS + BRAIN MEMORY")
    print("=" * 65)
    print("  Opus (temp=1.0) → Sonnet (analytical)")
    print("  4 memory DBs: {sonnet,opus} × {short,long}")
    print("  Type message to chat, or:")
    print("    /council  - Use full council (default)")
    print("    /quick    - Use Sonnet only")
    print("    /think    - One autonomous wake (no message)")
    print("    /loop N   - Run N autonomous wakes")
    print("    /status   - Show state, goals, mood")
    print("    /mem      - Show memory stats")
    print("    /quit     - Exit")
    print("  (Lifecycle runs automatically every 10 wakes)")
    print("=" * 65)
    while True:
        state = load_state(state_file)
        mode = "council" if use_council else "quick"
        try:
            inp = input(f"[Wake {state.get('total_wakes', 0) + 1}|{mode}] ct> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break
        if not inp:
            continue
        if inp == "/quit":
            break
        if inp == "/council":
            use_council = True
            print("  → Council mode")
            continue
        if inp == "/quick":
            use_council = False
            print("  → Quick mode (Sonnet only)")
            continue
        if inp.startswith("/loop"):
            parts = inp.split()
            n = int(parts[1]) if len(parts) > 1 else 10
            print(f"  → Running {n} wakes back to back...")
            total_cost = 0
            for i in range(n):
                state = load_state(state_file)
                wake = state.get("total_wakes", 0) + 1
                print(f"\n--- WAKE {wake} ({i+1}/{n}) ---")
                if use_council:
                    exp, cost, ti, to = council_cycle(client, state, None, state_file, verbose=False)
                else:
                    exp, cost, ti, to = quick_cycle(client, state, None, state_file)
                total_cost += cost
                if exp.get('message_to_ct'):
                    print(f"  TO CT: {exp['message_to_ct']}")
                print(f"  THOUGHT: {exp.get('thought', '')}")
                print(f"  [${cost:.4f}]")
                state = update_state(state, exp, cost, None)
                save_state(state, state_file)
                log_experience(log_dir, state, exp, cost)
                if state["total_wakes"] % 10 == 0:
                    run_lifecycle(state_file.parent, state["total_wakes"])
            print(f"\n  Loop complete. Total cost: ${total_cost:.4f}")
            continue
        if inp == "/status":
            print(f"\n  Wake: {state.get('total_wakes', 0)}")
            print(f"  Mood: {state.get('mood', 'unknown')}")
            print(f"  Restlessness: {state.get('restlessness', 0)}")
            print(f"  Streak: {state.get('achievement_streak', 0)}")
            print(f"  Total cost: ${state.get('total_cost', 0):.2f}")
            if BRAIN_AVAILABLE:
                try:
                    goals_db = get_goals_db(str(state_file.parent / "brain"))
                    goals = goals_db.get_goals()
                    if goals:
                        print(f"  Goals: {len(goals)} active")
                        for g in goals[:3]:
                            print(f"    - {g.get('description', '?')[:40]} ({g.get('progress_pct', 0)}%)")
                except:
                    pass
            continue
        if inp == "/mem":
            if BRAIN_AVAILABLE:
                brain = get_brain_memory(str(state_file.parent))
                print(json.dumps(brain.stats(), indent=2))
            continue
        if inp == "/lifecycle":  # Hidden command for manual trigger
            stats = run_lifecycle(state_file.parent, state.get("total_wakes", 0))
            if stats:
                print(json.dumps(stats, indent=2))
            continue
        if inp == "/think":
            ct_message = None
        else:
            ct_message = inp
        print()
        if use_council:
            exp, cost, ti, to = council_cycle(client, state, ct_message, state_file, verbose=True)
        else:
            exp, cost, ti, to = quick_cycle(client, state, ct_message, state_file)
        print()
        if exp.get('message_to_ct'):
            print(f"  TO CT: {exp['message_to_ct']}")
        print(f"\n  THOUGHT: {exp.get('thought', '')}")
        if exp.get('insight'):
            print(f"\n  INSIGHT: {exp['insight']}")
        if exp.get('council_notes'):
            print(f"\n  COUNCIL: {exp['council_notes']}")
        print(f"\n  [{ti} in, {to} out | ${cost:.4f}]")
        state = update_state(state, exp, cost, ct_message)
        save_state(state, state_file)
        log_experience(log_dir, state, exp, cost)
        # Run lifecycle every 10 wakes
        if state["total_wakes"] % 10 == 0:
            run_lifecycle(state_file.parent, state["total_wakes"])
        print()

def cron_wake(args):
    lock_fh = None
    try:
        lock_fh = acquire_lock()
        print(f"\n{'='*65}")
        print(f"CRON WAKE: {datetime.now(timezone.utc).isoformat()}")
        state_file = SCRIPT_DIR / args.state_file
        log_dir = SCRIPT_DIR / "logs"
        client = anthropic.Anthropic(api_key=args.api_key)
        state = load_state(state_file)
        wake = state.get("total_wakes", 0) + 1
        use_council = args.council or (wake % 10 == 0)
        mode = "COUNCIL" if use_council else "QUICK"
        print(f"Wake #{wake} | Mode: {mode}")
        if use_council:
            exp, cost, ti, to = council_cycle(client, state, None, state_file, verbose=True)
        else:
            exp, cost, ti, to = quick_cycle(client, state, None, state_file)
        print(f"\nThought: {exp.get('thought', '')}")
        if exp.get('insight'):
            print(f"Insight: {exp['insight'][:150]}")
        if exp.get('message_to_ct'):
            print(f"To ct: {exp['message_to_ct'][:150]}")
        state = update_state(state, exp, cost, None)
        save_state(state, state_file)
        log_experience(log_dir, state, exp, cost)
        # Run lifecycle every 10 wakes
        if state["total_wakes"] % 10 == 0:
            lifecycle_stats = run_lifecycle(state_file.parent, state["total_wakes"])
            if lifecycle_stats:
                print(f"Lifecycle: purged={lifecycle_stats['purged']}, promoted={lifecycle_stats['promoted']}")
        print(f"\n[${cost:.4f} | Total: ${state['total_cost']:.2f}]")
        print(f"{'='*65}\n")
    except LockAcquisitionError as e:
        print(f"SKIP: {e}")
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        release_lock(lock_fh)

def main():
    p = argparse.ArgumentParser(description="Aria v4")
    p.add_argument("--state-file", default="state.json")
    p.add_argument("-m", "--message", help="Message from ct")
    p.add_argument("-i", "--interactive", action="store_true")
    p.add_argument("--cron", action="store_true")
    p.add_argument("--council", action="store_true")
    p.add_argument("--quick", action="store_true")
    p.add_argument("--log-file", help="Log file")
    args = p.parse_args()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        env_file = SCRIPT_DIR / ".env"
        if env_file.exists():
            for line in env_file.read_text().split('\n'):
                if line.startswith("ANTHROPIC_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"')
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set")
        sys.exit(1)
    args.api_key = api_key
    if args.cron:
        if args.log_file:
            sys.stdout = sys.stderr = open(args.log_file, 'a')
        cron_wake(args)
    elif args.interactive:
        state_file = SCRIPT_DIR / args.state_file
        log_dir = SCRIPT_DIR / "logs"
        lock_fh = None
        try:
            lock_fh = acquire_lock()
            interactive_mode(args, state_file, log_dir)
        except LockAcquisitionError as e:
            print(f"Cannot start: {e}")
            sys.exit(1)
        finally:
            release_lock(lock_fh)
    elif args.message:
        state_file = SCRIPT_DIR / args.state_file
        log_dir = SCRIPT_DIR / "logs"
        client = anthropic.Anthropic(api_key=args.api_key)
        state = load_state(state_file)
        if args.quick:
            exp, cost, _, _ = quick_cycle(client, state, args.message, state_file)
        else:
            exp, cost, _, _ = council_cycle(client, state, args.message, state_file, verbose=True)
        if exp.get('message_to_ct'):
            print(f"To ct: {exp['message_to_ct']}")
        print(f"Thought: {exp.get('thought', '')}")
        state = update_state(state, exp, cost, args.message)
        save_state(state, state_file)
        log_experience(log_dir, state, exp, cost)
    else:
        p.print_help()

if __name__ == "__main__":
    main()

