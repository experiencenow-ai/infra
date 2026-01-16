"""
Background Tasks - Replaces cron with in-process task scheduling.

Instead of external cron jobs, background tasks run INSIDE the experience loop:
1. Check what's due based on elapsed time
2. Run due tasks sequentially  
3. Then do the wake

This makes the system:
- Self-contained (no external dependencies)
- Portable (can run on web)
- Predictable (serialized execution)
- Debuggable (all in one place)

Task Schedule (from v1 cron):
- heartbeat: every 5 minutes (system health check)
- price_monitor: every 15 minutes (market data)
- email_check: every 1 hour (backup email scan)
- news_scan: every 4 hours (news aggregation)
- dream_generate: every 6 hours (local LLM dreams)
- memory_summary: every 6 hours (compress experiences)
- offsite_backup: every 24 hours (backup to remote)
"""

import json
import subprocess
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Callable
from .time_utils import now_iso



def now_ts():
    return datetime.now(timezone.utc).timestamp()


# Task definitions with intervals in seconds
BACKGROUND_TASKS = {
    "heartbeat": {
        "interval": 5 * 60,          # 5 minutes
        "description": "System health check",
        "priority": 1,               # Run first
        "max_runtime": 30,           # 30 seconds max
    },
    "price_monitor": {
        "interval": 15 * 60,         # 15 minutes
        "description": "Market price feed",
        "priority": 2,
        "max_runtime": 60,
    },
    "blockchain_check": {
        "interval": 60 * 60,         # 1 hour
        "description": "Monitor watched blockchain addresses (async)",
        "priority": 2,               # High priority, low runtime
        "max_runtime": 120,          # 2 min max (rate limited)
        "async": True,               # Doesn't block wake
    },
    "email_check": {
        "interval": 60 * 60,         # 1 hour
        "description": "Backup email scan",
        "priority": 3,
        "max_runtime": 120,
    },
    "news_scan": {
        "interval": 4 * 60 * 60,     # 4 hours
        "description": "News aggregation",
        "priority": 4,
        "max_runtime": 300,
    },
    "dream_generate": {
        "interval": 6 * 60 * 60,     # 6 hours
        "description": "Local LLM dream generation",
        "priority": 5,
        "max_runtime": 600,
    },
    "memory_summary": {
        "interval": 6 * 60 * 60,     # 6 hours
        "description": "Compress experiences to summaries",
        "priority": 6,
        "max_runtime": 300,
    },
    "offsite_backup": {
        "interval": 24 * 60 * 60,    # 24 hours
        "description": "Backup to remote storage",
        "priority": 7,
        "max_runtime": 600,
    },
}


class BackgroundScheduler:
    """Manages background task scheduling and execution."""
    
    def __init__(self, citizen: str):
        self.citizen = citizen
        self.citizen_home = Path(f"/home/{citizen}")
        self.state_file = self.citizen_home / "background_tasks.json"
        self.state = self._load_state()
        self.handlers = {}  # Task name -> handler function
    
    def _load_state(self) -> dict:
        """Load task state (last run times)."""
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except:
                pass
        return {"last_run": {}, "run_counts": {}, "errors": {}}
    
    def _save_state(self):
        """Save task state."""
        self.state_file.write_text(json.dumps(self.state, indent=2))
    
    def register_handler(self, task_name: str, handler: Callable):
        """Register a handler function for a task."""
        self.handlers[task_name] = handler
    
    def get_due_tasks(self) -> list:
        """Get list of tasks that are due to run, sorted by priority."""
        now = now_ts()
        due = []
        for task_name, config in BACKGROUND_TASKS.items():
            last_run = self.state["last_run"].get(task_name, 0)
            if now - last_run >= config["interval"]:
                due.append((config["priority"], task_name, config))
        due.sort(key=lambda x: x[0])  # Sort by priority
        return [(name, config) for _, name, config in due]
    
    def run_task(self, task_name: str, config: dict) -> dict:
        """Run a single background task."""
        print(f"  [BG] Running {task_name}: {config['description']}")
        start_time = now_ts()
        result = {"success": False, "output": "", "duration": 0}
        try:
            if task_name in self.handlers:
                # Use registered handler
                output = self.handlers[task_name](self.citizen)
                result["success"] = True
                result["output"] = str(output)[:500]
            else:
                # Default: try to run script
                script = self._find_script(task_name)
                if script:
                    proc = subprocess.run(
                        ["python3", str(script)],
                        capture_output=True,
                        text=True,
                        timeout=config.get("max_runtime", 300),
                        cwd=str(self.citizen_home),
                        env={**os.environ, "CITIZEN": self.citizen}
                    )
                    result["success"] = proc.returncode == 0
                    result["output"] = (proc.stdout + proc.stderr)[:500]
                else:
                    result["output"] = f"No handler or script for {task_name}"
        except subprocess.TimeoutExpired:
            result["output"] = f"Task timed out after {config.get('max_runtime', 300)}s"
        except Exception as e:
            result["output"] = str(e)
        result["duration"] = now_ts() - start_time
        # Update state
        self.state["last_run"][task_name] = now_ts()
        self.state["run_counts"][task_name] = self.state["run_counts"].get(task_name, 0) + 1
        if not result["success"]:
            self.state["errors"][task_name] = {
                "time": now_iso(),
                "error": result["output"]
            }
        self._save_state()
        status = "OK" if result["success"] else "FAIL"
        print(f"  [BG] {task_name}: {status} ({result['duration']:.1f}s)")
        return result
    
    def _find_script(self, task_name: str) -> Optional[Path]:
        """Find script for a task."""
        # Check various locations
        candidates = [
            self.citizen_home / "scripts" / f"{task_name}.py",
            self.citizen_home / "body" / "specialists" / f"{task_name}.py",
            Path(f"/home/shared/baseline/scripts/{task_name}.py"),
        ]
        for path in candidates:
            if path.exists():
                return path
        return None
    
    def run_due_tasks(self, max_tasks: int = 3) -> list:
        """Run all due tasks up to max_tasks. Returns results."""
        due = self.get_due_tasks()
        if not due:
            return []
        print(f"\n[BACKGROUND] {len(due)} tasks due, running up to {max_tasks}")
        results = []
        for task_name, config in due[:max_tasks]:
            result = self.run_task(task_name, config)
            results.append((task_name, result))
        return results
    
    def get_status(self) -> str:
        """Get human-readable status of all tasks."""
        now = now_ts()
        lines = ["=== BACKGROUND TASKS ===", ""]
        for task_name, config in sorted(BACKGROUND_TASKS.items(), key=lambda x: x[1]["priority"]):
            last_run = self.state["last_run"].get(task_name, 0)
            if last_run == 0:
                ago = "never"
                next_in = "now"
            else:
                ago_sec = now - last_run
                ago = _format_duration(ago_sec)
                next_sec = config["interval"] - ago_sec
                next_in = _format_duration(max(0, next_sec)) if next_sec > 0 else "now"
            count = self.state["run_counts"].get(task_name, 0)
            error = self.state["errors"].get(task_name)
            status = "✗" if error else "✓"
            lines.append(f"  {status} {task_name}: ran {ago} ago, next in {next_in} ({count} runs)")
            if error:
                lines.append(f"      Last error: {error['error'][:60]}...")
        return "\n".join(lines)
    
    def force_run(self, task_name: str) -> dict:
        """Force run a task regardless of schedule."""
        if task_name not in BACKGROUND_TASKS:
            return {"success": False, "output": f"Unknown task: {task_name}"}
        config = BACKGROUND_TASKS[task_name]
        return self.run_task(task_name, config)
    
    def reset_task(self, task_name: str):
        """Reset a task's last run time (will run on next check)."""
        if task_name in self.state["last_run"]:
            del self.state["last_run"][task_name]
        if task_name in self.state["errors"]:
            del self.state["errors"][task_name]
        self._save_state()


def _format_duration(seconds: float) -> str:
    """Format duration in human-readable form."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds/60)}m"
    elif seconds < 86400:
        return f"{seconds/3600:.1f}h"
    else:
        return f"{seconds/86400:.1f}d"


# =============================================================================
# Default Task Handlers
# =============================================================================

def heartbeat_handler(citizen: str) -> str:
    """Check system health."""
    checks = []
    # Check disk space
    try:
        import shutil
        total, used, free = shutil.disk_usage("/")
        pct_used = (used / total) * 100
        checks.append(f"Disk: {pct_used:.1f}% used")
        if pct_used > 90:
            checks.append("WARNING: Disk space low!")
    except:
        pass
    # Check memory
    try:
        with open("/proc/meminfo") as f:
            lines = f.readlines()
        mem_total = int([l for l in lines if "MemTotal" in l][0].split()[1])
        mem_avail = int([l for l in lines if "MemAvailable" in l][0].split()[1])
        pct_used = ((mem_total - mem_avail) / mem_total) * 100
        checks.append(f"Memory: {pct_used:.1f}% used")
    except:
        pass
    # Check if other citizens are alive (via metadata)
    for peer in ["opus", "mira", "aria"]:
        if peer == citizen:
            continue
        meta_file = Path(f"/home/{peer}/metadata.json")
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text())
                last_wake = meta.get("last_wake")
                if last_wake:
                    last_dt = datetime.fromisoformat(last_wake.replace("Z", "+00:00"))
                    ago = (datetime.now(timezone.utc) - last_dt).total_seconds()
                    if ago > 3600:  # More than 1 hour
                        checks.append(f"{peer}: last wake {_format_duration(ago)} ago")
            except:
                pass
    return "\n".join(checks) if checks else "All systems nominal"


def email_check_handler(citizen: str) -> str:
    """Backup email check - returns 'URGENT' if ct@ email found."""
    try:
        # Import here to avoid circular imports
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        import email_client
        emails = email_client.check_email(citizen, unread_only=True)
        if emails:
            # Check for emails from ct (the creator) - these need immediate response
            urgent = [e for e in emails if "ct@" in e.get("from", "").lower() 
                     or "URGENT" in e.get("subject", "").upper()
                     or "HELP" in e.get("subject", "").upper()]
            
            # Create tasks for important emails
            if urgent:
                tasks_dir = Path(f"/home/{citizen}/tasks/queue")  # Use queue, not pending
                tasks_dir.mkdir(parents=True, exist_ok=True)
                for e in urgent[:3]:
                    task_file = tasks_dir / f"email_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
                    task = {
                        "type": "process_email",
                        "description": f"Process email: {e.get('subject', 'no subject')}",
                        "email": e,
                        "created": now_iso(),
                        "priority": "urgent" if "ct@" in e.get("from", "").lower() else "high"
                    }
                    task_file.write_text(json.dumps(task, indent=2))
                
                # Signal urgent wake needed
                return f"URGENT:{len(urgent)} emails from ct or urgent"
            
            return f"Checked {len(emails)} emails, none urgent"
        return "No new emails"
    except Exception as e:
        return f"Email check failed: {e}"


def check_urgent_email(citizen: str) -> bool:
    """
    Quick check if there's urgent email from ct.
    Called between wakes to trigger immediate response.
    Returns True if immediate wake needed.
    """
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        import email_client
        
        # Quick check - just peek at unread
        emails = email_client.check_email(citizen, unread_only=True, limit=10)
        if emails:
            for e in emails:
                sender = e.get("from", "").lower()
                if "ct@" in sender:
                    return True
        return False
    except:
        return False


def memory_summary_handler(citizen: str) -> str:
    """Generate memory summaries (daily/weekly)."""
    try:
        # Import memory module
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        import memory
        mem = memory.HierarchicalMemory(citizen)
        # Build daily summary for yesterday
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        mem.build_daily_summary(yesterday.strftime("%Y-%m-%d"))
        return f"Built daily summary for {yesterday.strftime('%Y-%m-%d')}"
    except Exception as e:
        return f"Memory summary failed: {e}"


def dream_generate_handler(citizen: str) -> str:
    """Generate dreams using local LLM (free!)."""
    # This would call local Ollama/llama.cpp
    # For now, just record that dreaming should happen
    dreams_file = Path(f"/home/{citizen}/contexts/dreams.json")
    if dreams_file.exists():
        try:
            dreams = json.loads(dreams_file.read_text())
            # Add a placeholder dream prompt
            dreams["messages"].append({
                "role": "system",
                "content": f"[Dream prompt generated at {now_iso()}] - Process recent experiences and generate insights",
                "processed": False
            })
            dreams["last_modified"] = now_iso()
            dreams_file.write_text(json.dumps(dreams, indent=2))
            return "Dream prompt added for next reflection wake"
        except:
            pass
    return "No dreams context to update"


def blockchain_check_handler(citizen: str) -> str:
    """
    Check watched blockchain addresses for activity.
    
    This runs async - just queues alerts for the AI to review later.
    Rate limited to avoid hitting API limits.
    """
    try:
        from blockchain import BlockchainMonitor
        
        monitor = BlockchainMonitor(citizen)
        watch_list = monitor.config.get("addresses", {})
        
        if not watch_list:
            return "No addresses to monitor"
        
        # Check addresses (rate limited internally)
        alerts = []
        checked = 0
        for address, info in list(watch_list.items())[:10]:  # Max 10 per run
            try:
                result = monitor.check_address(address)
                if result.get("alerts"):
                    alerts.extend(result["alerts"])
                checked += 1
            except Exception as e:
                print(f"  [BLOCKCHAIN] Error checking {address[:10]}...: {e}")
        
        if alerts:
            # Save alerts for AI to review
            alerts_file = Path(f"/home/{citizen}/blockchain_alerts.json")
            existing = []
            if alerts_file.exists():
                try:
                    existing = json.loads(alerts_file.read_text())
                except:
                    pass
            existing.extend(alerts)
            existing = existing[-100:]  # Keep last 100
            alerts_file.write_text(json.dumps(existing, indent=2))
            return f"ALERTS: {len(alerts)} new blockchain events (checked {checked} addresses)"
        
        return f"No activity (checked {checked} addresses)"
    except ImportError:
        return "Blockchain module not available"
    except Exception as e:
        return f"Blockchain check error: {e}"


# Register default handlers
def get_scheduler(citizen: str) -> BackgroundScheduler:
    """Get a scheduler with default handlers registered."""
    scheduler = BackgroundScheduler(citizen)
    scheduler.register_handler("heartbeat", heartbeat_handler)
    scheduler.register_handler("email_check", email_check_handler)
    scheduler.register_handler("memory_summary", memory_summary_handler)
    scheduler.register_handler("dream_generate", dream_generate_handler)
    scheduler.register_handler("blockchain_check", blockchain_check_handler)
    return scheduler
