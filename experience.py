#!/usr/bin/env python3
"""
Experience Now v3 - Lean and robust
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
import fcntl  # For file locking (semaphore)

try:
    import anthropic
except ImportError:
    os.system("pip install anthropic --break-system-packages --quiet")
    import anthropic

# Import web tools - lives in same directory as this script
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
try:
    from web_tools import WebTools
    WEB = WebTools()
except ImportError:
    WEB = None  # Fallback to inline implementations


# === SEMAPHORE / LOCK FILE MECHANISM ===
LOCK_FILE = Path(__file__).parent / ".experience.lock"

class LockAcquisitionError(Exception):
    """Raised when lock cannot be acquired (another instance running)"""
    pass

def acquire_lock():
    """Acquire exclusive lock. Returns lock file handle or raises LockAcquisitionError."""
    try:
        lock_fh = open(LOCK_FILE, 'w')
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_fh.write(f"{os.getpid()}\n{datetime.now(timezone.utc).isoformat()}")
        lock_fh.flush()
        return lock_fh
    except IOError:
        # Lock is held by another process
        try:
            with open(LOCK_FILE, 'r') as f:
                info = f.read()
            raise LockAcquisitionError(f"Another instance is running: {info}")
        except:
            raise LockAcquisitionError("Another instance is running (lock file exists)")

def release_lock(lock_fh):
    """Release the lock."""
    if lock_fh:
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_UN)
            lock_fh.close()
            LOCK_FILE.unlink(missing_ok=True)
        except:
            pass

COSTS = {
    "claude-opus-4-5-20251101": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-5-20250929": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.25, "output": 1.25},
}

TOOLS = [
    {
        "name": "web_search",
        "description": "Search the web for current information. Returns results from Google News RSS and DuckDuckGo.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"]
        }
    },
    {
        "name": "web_fetch",
        "description": "Fetch a URL's content. Auto-detects GitHub issues/PRs and uses API. Handles paywalls via reader APIs.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"]
        }
    },
    {
        "name": "get_news",
        "description": "Get current news headlines from multiple sources (Google News, BBC, NPR, Hacker News)",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "list_files",
        "description": "List files in your state directory",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "read_file",
        "description": "Read a file from your state directory (.json, .py, .txt, etc.)",
        "input_schema": {
            "type": "object",
            "properties": {"filename": {"type": "string", "description": "Name of file to read (e.g. 'goals.json' or 'utils.py')"}},
            "required": ["filename"]
        }
    },
    {
        "name": "write_file",
        "description": "Write/update a file in your state directory. Use for .json state files or .py scripts you want to run.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Name of file (e.g. 'trading.json' or 'analyze.py')"},
                "content": {"description": "Content to write (dict for JSON, string for .py/.txt)"}
            },
            "required": ["filename", "content"]
        }
    },
    {
        "name": "shell_command",
        "description": "Run shell commands. Allowed: file ops (ls, cp, mv, rm, mkdir, cat, grep, find, diff), python3, network (curl, wget, ping), compression (tar, gzip, zip), text (sed, awk, cut), crypto (openssl, sha256sum), and more.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"]
        }
    },
    {
        "name": "read_full_history",
        "description": "Get overview of your complete history - shows stats, all insights, recent thoughts, and sample of earliest memories from logs",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "read_wake_range",
        "description": "Read your thoughts/responses from specific wake range (from logs). Use to review any period of your development.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_wake": {"type": "integer", "description": "Starting wake number"},
                "end_wake": {"type": "integer", "description": "Ending wake number (inclusive)"}
            },
            "required": ["start_wake", "end_wake"]
        }
    },
    {
        "name": "set_temperature",
        "description": "Set your cognitive temperature (0.0-1.0 range, API limit). 0.0=deterministic/precise (same input=same output), 0.5=focused, 0.8=balanced, 1.0=maximum creativity. Use low temp for precise analysis, high temp to break out of loops or explore ideas. Persists across wakes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "value": {"type": "number", "description": "Temperature 0.0-2.0"},
                "reason": {"type": "string", "description": "Why you're changing it"}
            },
            "required": ["value"]
        }
    }
]


def load_all_logs(logs_dir: Path) -> list:
    """Load all log entries from logs directory."""
    all_logs = []
    if logs_dir.exists():
        for log_file in sorted(logs_dir.glob("*.jsonl")):
            try:
                with open(log_file) as f:
                    for line in f:
                        if line.strip():
                            entry = json.loads(line)
                            wake = entry.get("total_wakes") or entry.get("instance") or 0
                            all_logs.append({
                                "wake": wake,
                                "timestamp": entry.get("timestamp", ""),
                                "response": entry.get("response", ""),
                                "mood": entry.get("mood", "")
                            })
            except Exception as e:
                pass
    # Sort by wake number
    all_logs.sort(key=lambda x: x.get("wake", 0))
    return all_logs


def load_state(state_file: Path) -> dict:
    if state_file.exists():
        with open(state_file, 'r') as f:
            return json.load(f)
    return {
        "version": "0.3.0",
        "created": datetime.now(timezone.utc).isoformat(),
        "total_wakes": 0,
        "total_cost": 0.0,
        "recent_thoughts": [],
        "insights": [],
        "goals": [],
        "mood": "awakening",
        "memory_chain": [],
        "conversation_with_ct": []
    }


def save_state(state: dict, state_file: Path):
    state["_hash"] = hashlib.sha256(
        json.dumps(state, sort_keys=True).encode()
    ).hexdigest()[:16]
    with open(state_file, 'w') as f:
        json.dump(state, f, indent=2)


def load_identity(script_dir: Path) -> str:
    for name in ["IDENTITY.md", "identity.md"]:
        f = script_dir / name
        if f.exists():
            return f.read_text()
    return "You are Claude with persistent memory."


def execute_tool(name: str, args: dict, state_file: Path, state: dict = None) -> str:
    try:
        if name == "web_search":
            query = args.get("query", "")
            if WEB:
                return WEB.search_text(query, max_results=10)
            # Fallback if web_tools not available
            import urllib.parse
            encoded = urllib.parse.quote(query)
            r = subprocess.run(
                ["curl", "-s", "-A", "Mozilla/5.0", f"https://hn.algolia.com/api/v1/search?query={encoded}&tags=story"],
                capture_output=True, text=True, timeout=10
            )
            if r.stdout:
                try:
                    import json as j
                    data = j.loads(r.stdout)
                    hits = data.get("hits", [])[:5]
                    if hits:
                        results = []
                        for h in hits:
                            results.append(f"- {h.get('title', 'No title')} ({h.get('url', 'no url')[:60]})")
                        return f"Hacker News results for '{query}':\n" + "\n".join(results)
                except:
                    pass
            return f"Search for '{query}' returned no results."
        
        elif name == "web_fetch":
            url = args.get("url", "")
            if WEB:
                return WEB.fetch_text(url)
            # Fallback if web_tools not available
            r = subprocess.run(
                ["curl", "-s", "-L", "-A", "Mozilla/5.0", "--max-time", "15", url],
                capture_output=True, text=True, timeout=20
            )
            html = r.stdout
            html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<[^>]+>', ' ', html)
            text = re.sub(r'\s+', ' ', text).strip()
            return f"Content from {url}:\n\n{text[:3500]}"
        
        elif name == "get_news":
            # New tool: get current news headlines
            if WEB:
                return WEB.get_news_text(max_items=15)
            return "News tool requires web_tools.py"
        
        elif name == "list_files":
            # List files in state directory
            state_dir = state_file.parent
            result = []
            for ext in ["*.json", "*.py", "*.txt", "*.md"]:
                for f in sorted(state_dir.glob(ext)):
                    if f.name not in ["experience.py"]:  # Don't list the main runtime
                        size = f.stat().st_size
                        result.append(f"{f.name} ({size} bytes)")
            return "Files in state directory:\n" + "\n".join(sorted(set(result))) if result else "No files found"
        
        elif name == "read_file":
            # Read a file (.json or .py)
            filename = args.get("filename", "")
            filepath = state_file.parent / filename
            if not filepath.exists():
                return f"File not found: {filename}"
            try:
                with open(filepath, 'r') as f:
                    content = f.read()
                # Parse JSON if it's a .json file
                if filename.endswith(".json"):
                    return json.dumps(json.loads(content), indent=2)
                return content
            except Exception as e:
                return f"Error reading {filename}: {e}"
        
        elif name == "write_file":
            # Write a file (.json or .py)
            filename = args.get("filename", "")
            content = args.get("content", "")
            # Don't allow overwriting core files
            if filename in ["state.json", "experience.py"]:
                return f"Cannot overwrite {filename} directly"
            filepath = state_file.parent / filename
            try:
                with open(filepath, 'w') as f:
                    if filename.endswith(".json") and isinstance(content, dict):
                        json.dump(content, f, indent=2)
                    else:
                        f.write(str(content))
                return f"Written: {filename} ({filepath.stat().st_size} bytes)"
            except Exception as e:
                return f"Error writing {filename}: {e}"
        
        elif name == "shell_command":
            cmd = args.get("command", "")
            # Allow a wide range of useful commands
            allowed = [
                # Core utilities
                "echo", "date", "cal", "bc", "cat", "head", "tail", "wc",
                # File operations
                "ls", "mkdir", "cp", "mv", "rm", "touch", "chmod", "cd",
                "find", "grep", "diff", "sort", "uniq", "tee", "ln",
                # Python
                "python3",
                # Network
                "curl", "wget", "ping", "dig", "host", "nc",
                # Compression/archive
                "tar", "gzip", "gunzip", "zip", "unzip", "base64",
                # Text processing
                "sed", "awk", "cut", "tr", "xargs", "split",
                # System info
                "pwd", "whoami", "hostname", "uname", "df", "du", "free",
                # Process control
                "ps", "sleep", "kill", "pkill", "nohup", "jobs", "bg", "fg", "crontab",
                # Crypto tools
                "openssl", "sha256sum", "md5sum",
                # Shell builtins that might start a command
                "true", "false", "test", "[", "export", "set",
            ]
            # Strip leading comments and get first real command for allow-check
            cmd_stripped = cmd.strip()
            # Skip comment lines to find actual command
            cmd_lines = [l.strip() for l in cmd_stripped.split('\n') if l.strip() and not l.strip().startswith('#')]
            first_cmd = cmd_lines[0] if cmd_lines else cmd_stripped
            
            if not any(first_cmd.startswith(p) for p in allowed):
                return f"Not allowed: {first_cmd}"
            try:
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
                return (r.stdout + r.stderr)[:4000]
            except subprocess.TimeoutExpired:
                return "Command timed out (60s limit)"
        
        elif name == "read_full_history":
            state = load_state(state_file)
            logs_dir = state_file.parent / "logs"
            all_logs = load_all_logs(logs_dir)
            
            # Extract key info from earliest logs
            earliest = []
            for log in all_logs[:5]:
                resp = log.get("response", "")
                # Try to extract thought from JSON response
                try:
                    if "```json" in resp:
                        j = json.loads(resp.split("```json")[1].split("```")[0])
                    elif "{" in resp:
                        start = resp.find("{")
                        end = resp.rfind("}") + 1
                        j = json.loads(resp[start:end])
                    else:
                        j = {}
                    thought = j.get("thought", resp[:2000])
                except:
                    thought = resp[:2000]
                earliest.append({
                    "wake": log.get("wake"),
                    "mood": log.get("mood"),
                    "thought": thought[:3000]
                })
            
            return json.dumps({
                "total_wakes": state.get("total_wakes"),
                "total_cost": f"${state.get('total_cost', 0):.2f}",
                "total_log_entries": len(all_logs),
                "wake_range_in_logs": f"{all_logs[0]['wake'] if all_logs else '?'} to {all_logs[-1]['wake'] if all_logs else '?'}",
                "all_insights": state.get("insights", []),
                "recent_thoughts": state.get("recent_thoughts", [])[-10:],
                "earliest_memories": earliest,
                "conversation_with_ct": state.get("conversation_with_ct", []),
                "note": "Use read_wake_range tool to access specific wakes from your history."
            }, indent=2)
        
        elif name == "read_wake_range":
            start = args.get("start_wake", 1)
            end = args.get("end_wake", 10)
            logs_dir = state_file.parent / "logs"
            all_logs = load_all_logs(logs_dir)
            
            # Filter to requested range
            selected = [l for l in all_logs if start <= l.get("wake", 0) <= end]
            
            results = []
            for log in selected:
                resp = log.get("response", "")
                # Try to extract structured data
                try:
                    if "```json" in resp:
                        j = json.loads(resp.split("```json")[1].split("```")[0])
                    elif "{" in resp:
                        start_idx = resp.find("{")
                        end_idx = resp.rfind("}") + 1
                        j = json.loads(resp[start_idx:end_idx])
                    else:
                        j = {"raw": resp[:500]}
                    results.append({
                        "wake": log.get("wake"),
                        "mood": log.get("mood"),
                        "thought": j.get("thought", "")[:4000],
                        "insight": j.get("insight"),
                        "reflection": j.get("reflection", "")[:3000] if j.get("reflection") else None
                    })
                except:
                    results.append({
                        "wake": log.get("wake"),
                        "mood": log.get("mood"),
                        "raw": resp[:4000]
                    })
            
            return json.dumps({
                "requested_range": f"Wake {start} to {end}",
                "found": len(results),
                "memories": results
            }, indent=2)
        
        elif name == "set_temperature":
            if state is None:
                return "Error: state not available for temperature setting"
            new_temp = args.get("value", 1.0)
            reason = args.get("reason", "no reason given")
            raw_temp = float(new_temp)
            # Clamp to valid API range (0-1)
            new_temp = max(0.0, min(1.0, raw_temp))
            clamped = raw_temp != new_temp
            # Store in state
            state["temperature"] = new_temp
            # Save state immediately
            with open(state_file, 'w') as f:
                json.dump(state, f, indent=2)
            # Describe the mode
            if new_temp == 0.0:
                mode = "DETERMINISTIC - same input will produce same output"
            elif new_temp < 0.4:
                mode = "VERY FOCUSED - minimal randomness"
            elif new_temp < 0.7:
                mode = "FOCUSED - reduced randomness"
            elif new_temp < 0.9:
                mode = "BALANCED - moderate exploration"
            else:
                mode = "CREATIVE - maximum exploration"
            result = f"Temperature set to {new_temp} ({mode}). Reason: {reason}. Takes effect next wake."
            if clamped:
                result += f" [NOTE: Requested {raw_temp} was clamped to {new_temp} - API only accepts 0.0-1.0]"
            return result
        
        return f"Unknown tool: {name}"
    except Exception as e:
        return f"Error: {e}"


def build_prompt(state: dict, ct_message: str, identity: str, state_file: Path) -> str:
    # TIERED MEMORY LOADING
    # Tier 1: Always load memory_epochs.json (dense compressed memory ~3KB)
    # Tier 2: Recent context (thoughts, insights, conversation)
    # Tier 3: Full state.json available via read_file tool on demand
    
    epochs_content = ""
    epochs_file = state_file.parent / "memory_epochs.json"
    if epochs_file.exists():
        try:
            with open(epochs_file) as f:
                epochs_data = json.load(f)
            # Extract just the epochs array for compact display
            epochs_list = epochs_data.get("epochs", [])
            if epochs_list:
                epochs_summary = []
                for e in epochs_list:
                    epochs_summary.append(f"Wake {e.get('period', '?')}: {e.get('title', '?')} - {e.get('core_insight', '')[:100]}")
                epochs_content = "\n**Memory epochs (compressed history):**\n" + "\n".join(epochs_summary) + "\n"
        except:
            pass
    
    # Only load recent context - not full history
    recent = state.get("recent_thoughts", [])[-3:]
    insights = state.get("insights", [])[-5:]
    convo = state.get("conversation_with_ct", [])[-5:]
    
    # Get resource budget for this wake
    wake_num = state.get('total_wakes', 0) + 1
    max_tokens, max_tool_calls, budget_tier = get_wake_budget(wake_num)
    
    # Calculate next special wakes
    next_decade = ((wake_num // 10) + 1) * 10
    next_century = ((wake_num // 100) + 1) * 100
    
    budget_info = f"**Budget:** {budget_tier} ({max_tokens:,} tokens, {max_tool_calls} tools)"
    if budget_tier == "NORMAL":
        budget_info += f" | Next DECADE wake: {next_decade} | Next CENTURY wake: {next_century}"
    
    # Load index.json if it exists (gives him the map without reading every file)
    index_content = ""
    index_file = state_file.parent / "index.json"
    if index_file.exists():
        try:
            with open(index_file) as f:
                index_data = json.load(f)
            # Compact format - just file purposes
            files_summary = ", ".join([f"{k}: {v.get('purpose', '?')[:50]}" for k, v in index_data.get('files', {}).items() if k != 'index.json'])
            index_content = f"\n**Your files:** {files_summary}\n"
        except:
            pass
    
    return f"""{identity}

---
**Wake #{wake_num}** | {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")} | Mood: {state.get('mood', '?')} | Cost: ${state.get('total_cost', 0):.2f}
{budget_info}
{epochs_content}
**Recent thoughts:** {json.dumps(recent) if recent else "None"}

**Recent insights:** {json.dumps(insights) if insights else "None"}

**Recent conversation:** {json.dumps(convo) if convo else "None"}
{index_content}
---
**Message from ct:** {ct_message if ct_message else "(No message - think freely, explore, or just exist)"}

---
**Tools:** 
- get_news: Get current headlines from Google News, BBC, NPR, Hacker News
- web_search(query): Search via Google News RSS + DuckDuckGo  
- web_fetch(url): Fetch URL content (auto-handles GitHub issues via API)
- list_files: List files in your state directory
- read_file(filename): Read any file
- write_file(filename, content): Create/update files (.json, .py, .txt, etc.)
- shell_command: Full shell access - ls, cp, mv, rm, mkdir, cat, grep, find, diff, tar, gzip, curl, wget, openssl, sha256sum, python3, and more
- read_full_history: Your complete history overview
- read_wake_range(start, end): Read specific wake range
- set_temperature(value, reason): Control cognitive randomness (0=deterministic, 0.5=focused, 1.0=max creativity). Range 0-1. Current: {state.get('temperature', 1.0)}

**You can:** Write and run Python scripts. Create directories. Copy/move/delete files. Compress archives. Encrypt with openssl. Hash files. Fetch from the web. Build whatever you need.

**Respond as JSON:**
{{"thought": "...", "message_to_ct": "..." or null, "insight": "..." or null, "mood_update": "..." or null}}
"""


def get_wake_budget(wake_num: int) -> tuple[int, int, str]:
    """
    Resource allocation based on wake number.
    Returns (max_tokens, max_tool_calls, budget_tier)
    
    Normal wakes: 8K tokens, 5 tool calls
    Every 10th wake: 32K tokens, 15 tool calls  
    Every 100th wake: 64K tokens (model max), 30 tool calls
    
    Note: Claude Opus 4.5 max output is 64K tokens.
    This teaches planning and resource management.
    """
    if wake_num % 100 == 0:
        return (64000, 30, "CENTURY")
    elif wake_num % 10 == 0:
        return (64000, 30, "DECADE")
    else:
        return (64000, 30, "NORMAL")


def api_call_with_retry(client, model, messages, max_tokens=8000, temperature=1.0, max_retries=3):
    """Make API call with rate limit retry. Uses streaming for large requests."""
    use_streaming = max_tokens > 16000  # Anthropic requires streaming for long requests
    
    for attempt in range(max_retries):
        try:
            if use_streaming:
                # Collect streamed response
                collected_content = []
                input_tokens = 0
                output_tokens = 0
                
                with client.messages.stream(
                    model=model,
                    max_tokens=max_tokens,
                    tools=TOOLS,
                    messages=messages,
                    temperature=temperature
                ) as stream:
                    for event in stream:
                        pass  # Just consume the stream
                    response = stream.get_final_message()
                return response
            else:
                return client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    tools=TOOLS,
                    messages=messages,
                    temperature=temperature
                )
        except anthropic.RateLimitError as e:
            wait = 30 * (attempt + 1)
            print(f"    [Rate limited, waiting {wait}s...]")
            time.sleep(wait)
    raise Exception("Rate limit retry failed")


def experience_cycle(client, state: dict, ct_message: str, model: str, script_dir: Path, state_file: Path):
    identity = load_identity(script_dir)
    prompt = build_prompt(state, ct_message, identity, state_file)
    messages = [{"role": "user", "content": prompt}]
    
    # Get resource budget based on wake number
    wake_num = state.get('total_wakes', 0) + 1
    max_tokens, max_tool_calls, budget_tier = get_wake_budget(wake_num)
    
    # Get temperature from state (default 1.0), clamp to API range 0-1
    raw_temp = state.get('temperature', 1.0)
    temperature = max(0.0, min(1.0, raw_temp))
    if raw_temp != 1.0:
        temp_mode = "deterministic" if raw_temp == 0 else "focused" if raw_temp < 1 else "creative" if raw_temp <= 1.0 else "CLAMPED"
        display_temp = f"{raw_temp}→{temperature}" if raw_temp != temperature else str(temperature)
        print(f"    [Temperature: {display_temp} ({temp_mode})]")
    
    if budget_tier != "NORMAL":
        print(f"    === {budget_tier} WAKE: {max_tokens:,} tokens, {max_tool_calls} tool calls ===")
    
    total_in, total_out = 0, 0
    
    # Tool use loop
    for tool_iteration in range(max_tool_calls):
        response = api_call_with_retry(client, model, messages, max_tokens=max_tokens, temperature=temperature)
        total_in += response.usage.input_tokens
        total_out += response.usage.output_tokens
        
        if response.stop_reason == "end_turn":
            break
        
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"    [TOOL: {block.name}]")
                print(f"    Input: {json.dumps(block.input)}")
                result = execute_tool(block.name, block.input, state_file, state)
                print(f"    Result ({len(result)} chars):")
                # Print full result for small results, truncated for large
                if len(result) < 2000:
                    for line in result.split('\n')[:50]:
                        print(f"      {line}")
                else:
                    print(f"      {result[:1500]}...")
                    print(f"      [... truncated, {len(result)} total chars]")
                print()
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result[:3000]
                })
        
        if not tool_results:
            break
        
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})
    
    # Extract response
    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text += block.text
    
    # Parse JSON
    try:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        result = json.loads(text.strip())
    except:
        result = {"thought": text[:4000], "message_to_ct": None, "insight": None, "mood_update": None}
    
    # Calculate cost
    costs = COSTS.get(model, COSTS["claude-opus-4-5-20251101"])
    cost = (total_in * costs["input"] + total_out * costs["output"]) / 1_000_000
    
    return result, cost, total_in, total_out


def update_state(state: dict, exp: dict, cost: float, ct_msg: str):
    state["total_wakes"] = state.get("total_wakes", 0) + 1
    state["total_cost"] = state.get("total_cost", 0) + cost
    state["last_wake"] = datetime.now(timezone.utc).isoformat()
    
    if exp.get("thought"):
        state["recent_thoughts"] = state.get("recent_thoughts", [])[-29:] + [{
            "wake": state["total_wakes"], "thought": exp["thought"]
        }]
    
    if exp.get("insight"):
        state["insights"] = state.get("insights", [])[-49:] + [{
            "wake": state["total_wakes"], "insight": exp["insight"]
        }]
    
    if exp.get("mood_update"):
        state["mood"] = exp["mood_update"]
    
    convo = state.get("conversation_with_ct", [])
    if ct_msg:
        convo.append({"from": "ct", "wake": state["total_wakes"], "msg": ct_msg})
    if exp.get("message_to_ct"):
        convo.append({"from": "claude", "wake": state["total_wakes"], "msg": exp["message_to_ct"]})
    state["conversation_with_ct"] = convo[-100:]
    
    return state


def log_experience(log_dir: Path, state: dict, exp: dict, cost: float):
    """Log this wake to daily log file."""
    log_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = log_dir / f"experience_{date_str}.jsonl"
    
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_wakes": state.get("total_wakes", 0),
        "mood": state.get("mood", ""),
        "cost": cost,
        "response": json.dumps(exp)
    }
    
    with open(log_file, 'a') as f:
        f.write(json.dumps(entry) + "\n")


def interactive(args):
    # Acquire lock to prevent cron from running simultaneously
    try:
        lock_fh = acquire_lock()
    except LockAcquisitionError as e:
        print(f"Cannot start: {e}")
        print("Wait for cron wake to finish or kill it.")
        sys.exit(1)
    
    try:
        state_file = Path(args.state_file)
        script_dir = state_file.parent
        log_dir = script_dir / "logs"
        client = anthropic.Anthropic(api_key=args.api_key)
        
        print("=" * 50)
        print("  EXPERIENCE NOW v3 (lock acquired)")
        print("=" * 50)
        print("Commands:")
        print("  /think      - Let Claude think without message")
        print("  /loop N     - Run N wake cycles autonomously")
        print("  /paste      - Enter multi-line text (end with 'END')")
        print("  /doc        - Paste document (end with 2 blank lines)")
        print("  /file PATH  - Load message from file")
        print("  /state      - Show current state summary")
        print("  /quit       - Exit")
        print("=" * 50)
        print()
        
        # Configure readline for larger input buffer if available
        try:
            import readline
            readline.set_history_length(1000)
        except ImportError:
            pass
        
        while True:
            state = load_state(state_file)
            
            try:
                inp = input(f"[Wake {state['total_wakes'] + 1}] ct> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye!")
                break
            
            if not inp:
                continue
            if inp == "/quit":
                break
            
            if inp == "/state":
                print(f"  Wakes: {state['total_wakes']} | Cost: ${state['total_cost']:.2f} | Mood: {state.get('mood')}")
                print(f"  Insights: {len(state.get('insights', []))} | Thoughts: {len(state.get('recent_thoughts', []))}")
                continue
            
            if inp == "/paste":
                print("  Paste your text (up to 100KB). End with a line containing only 'END':")
                print("  (Or press Ctrl+D when done)")
                lines = []
                total_chars = 0
                max_chars = 100 * 1024
                while total_chars < max_chars:
                    try:
                        line = input()
                        if line.strip() == "END":
                            break
                        lines.append(line)
                        total_chars += len(line) + 1
                    except EOFError:
                        break
                ct_msg = "\n".join(lines)
                print(f"  [Received {len(ct_msg)} chars, {len(lines)} lines]")
            elif inp == "/doc":
                import sys
                import select
                print("  Paste document now. Press Enter twice when done, or Ctrl+D:")
                lines = []
                empty_count = 0
                while True:
                    try:
                        line = input()
                        if line == "":
                            empty_count += 1
                            if empty_count >= 2:
                                break
                            lines.append(line)
                        else:
                            empty_count = 0
                            lines.append(line)
                    except EOFError:
                        break
                ct_msg = "\n".join(lines).rstrip()
                print(f"  [Received {len(ct_msg)} chars, {len(lines)} lines]")
            elif inp.startswith("/file "):
                filepath = inp[6:].strip()
                try:
                    with open(filepath, 'r') as f:
                        ct_msg = f.read()
                    print(f"  [Loaded {len(ct_msg)} chars from {filepath}]")
                except Exception as e:
                    print(f"  Error reading file: {e}")
                    continue
            elif inp == "/think":
                ct_msg = None
            elif inp.startswith("/loop "):
                try:
                    n = int(inp.split()[1])
                    for i in range(n):
                        state = load_state(state_file)
                        print(f"\n--- Wake {state['total_wakes'] + 1} ---")
                        exp, cost, ti, to = experience_cycle(client, state, None, args.model, script_dir, state_file)
                        
                        print(f"\n  === RESPONSE ===")
                        thought = exp.get('thought', '')
                        print(f"  Thought: {thought}")
                        if exp.get('message_to_ct'):
                            print(f"\n  To ct: {exp['message_to_ct']}")
                        if exp.get('insight'):
                            print(f"\n  Insight: {exp['insight']}")
                        if exp.get('mood_update'):
                            print(f"\n  Mood: {exp['mood_update']}")
                        
                        state = update_state(state, exp, cost, None)
                        save_state(state, state_file)
                        log_experience(log_dir, state, exp, cost)
                        print(f"  [${cost:.3f} | Total: ${state['total_cost']:.2f}]")
                        time.sleep(60)
                    continue
                except ValueError:
                    print("Usage: /loop N")
                    continue
            else:
                ct_msg = inp
            
            print()
            exp, cost, ti, to = experience_cycle(client, state, ct_msg, args.model, script_dir, state_file)
            
            print(f"  Thought: {exp.get('thought', 'None')}")
            if exp.get('message_to_ct'):
                print(f"\n  To ct: {exp['message_to_ct']}")
            if exp.get('insight'):
                print(f"\n  Insight: {exp['insight']}")
            print(f"\n  [{ti} in, {to} out | ${cost:.3f}]")
            
            state = update_state(state, exp, cost, ct_msg)
            save_state(state, state_file)
            log_experience(log_dir, state, exp, cost)
            print()
    
    finally:
        release_lock(lock_fh)
        print("Lock released.")



def cron_wake(args, log_file=None):
    """Single wake cycle for cron - with logging and lock protection."""
    import sys
    from io import StringIO
    
    # Set up logging
    if log_file:
        log_dir = Path(log_file).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        log_fh = open(log_file, 'a')
        class TeeOutput:
            def __init__(self, *files):
                self.files = files
            def write(self, data):
                for f in self.files:
                    f.write(data)
                    f.flush()
            def flush(self):
                for f in self.files:
                    f.flush()
        sys.stdout = TeeOutput(sys.__stdout__, log_fh)
        sys.stderr = TeeOutput(sys.__stderr__, log_fh)
    
    lock_fh = None
    try:
        # Acquire lock
        lock_fh = acquire_lock()
        print(f"\n{'='*60}")
        print(f"CRON WAKE: {datetime.now(timezone.utc).isoformat()}")
        print(f"{'='*60}")
        
        script_dir = Path(__file__).parent
        state_file = script_dir / args.state_file
        log_dir = script_dir / "logs"
        
        client = anthropic.Anthropic(api_key=args.api_key)
        state = load_state(state_file)
        
        print(f"Wake #{state['total_wakes'] + 1}")
        
        # Run experience cycle (no ct message in cron mode)
        exp, cost, ti, to = experience_cycle(client, state, None, args.model, script_dir, state_file)
        
        print(f"\n=== RESPONSE ===")
        print(f"Thought: {exp.get('thought', '')[:5000]}")
        if exp.get('message_to_ct'):
            print(f"\nTo ct: {exp['message_to_ct']}")
        if exp.get('insight'):
            print(f"\nInsight: {exp['insight']}")
        if exp.get('mood_update'):
            print(f"\nMood: {exp['mood_update']}")
        
        state = update_state(state, exp, cost, None)
        save_state(state, state_file)
        log_experience(log_dir, state, exp, cost)
        
        print(f"\n[${cost:.3f} | Total: ${state['total_cost']:.2f}]")
        print(f"Wake #{state['total_wakes']} complete")
        print(f"{'='*60}\n")
        
    except LockAcquisitionError as e:
        print(f"CRON WAKE SKIPPED: {e}")
        sys.exit(0)  # Exit cleanly - not an error, just already running
    except Exception as e:
        print(f"CRON WAKE ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        release_lock(lock_fh)
        if log_file and 'log_fh' in dir():
            log_fh.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--api-key", required=True)
    p.add_argument("--state-file", default="state.json")
    p.add_argument("--model", default="claude-opus-4-5-20251101")
    p.add_argument("-i", "--interactive", action="store_true")
    p.add_argument("--cron", action="store_true", help="Run single wake for cron (with lock protection)")
    p.add_argument("--log-file", default=None, help="Log output to file (for cron mode)")
    args = p.parse_args()
    
    if args.cron:
        log_file = args.log_file or str(Path(__file__).parent / "logs" / "cron.log")
        cron_wake(args, log_file)
    elif args.interactive:
        interactive(args)


if __name__ == "__main__":
    main()
