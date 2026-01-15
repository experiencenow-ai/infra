"""
Failure Tracker - Detect repeated failures and auto-escalate.

Problem: AI loops endlessly on broken things (e.g., misconfigured email).
Solution: Track failures, auto-create GitHub issue after 3 failures.
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def now_iso():
    return datetime.now(timezone.utc).isoformat()


class FailureTracker:
    """Track repeated failures and auto-escalate."""
    
    MAX_FAILURES = 3  # Auto-escalate after this many
    
    def __init__(self, citizen: str):
        self.citizen = citizen
        self.file = Path(f"/home/{citizen}/failure_tracking.json")
        self.data = self._load()
    
    def _load(self) -> dict:
        if self.file.exists():
            try:
                return json.loads(self.file.read_text())
            except:
                return {}
        return {}
    
    def _save(self):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.data, indent=2))
        tmp.rename(self.file)
    
    def _normalize_key(self, operation: str) -> str:
        """Normalize operation to consistent key."""
        # Remove dynamic parts like timestamps, specific args
        key = operation.lower().strip()
        # Truncate long operations
        if len(key) > 50:
            key = key[:50]
        return key
    
    def record_failure(self, operation: str, error: str) -> str:
        """
        Record a failure.
        
        Returns:
            None if still trying
            Escalation message if auto-escalated
        """
        key = self._normalize_key(operation)
        
        # Skip if already escalated
        if key in self.data and self.data[key].get("escalated"):
            return f"Already escalated. See issue: {self.data[key].get('issue_url', 'unknown')}"
        
        # Initialize or update
        if key not in self.data:
            self.data[key] = {
                # NOTE: No count field! Derived from len(errors).
                "errors": [],
                "first_seen": now_iso(),
                "escalated": False
            }
        
        # Add error
        self.data[key]["last_seen"] = now_iso()
        self.data[key]["errors"].append({
            "error": error[:500],  # Truncate
            "time": now_iso()
        })
        
        # Keep only last N errors (where N >= MAX_FAILURES so we can count)
        self.data[key]["errors"] = self.data[key]["errors"][-10:]
        
        self._save()
        
        # DRY: count is derived from len(errors)
        error_count = len(self.data[key]["errors"])
        
        # Check for auto-escalate
        if error_count >= self.MAX_FAILURES:
            return self._auto_escalate(key)
        
        return None
    
    def _auto_escalate(self, key: str) -> str:
        """Create GitHub issue for repeated failure."""
        failure_data = self.data[key]
        
        # Build issue
        errors_text = "\n".join(
            f"  [{e['time'][:19]}] {e['error'][:100]}"
            for e in failure_data["errors"][-3:]
        )
        
        issue_body = f"""## Auto-Generated Failure Report

**Citizen:** {self.citizen}
**Operation:** `{key}`
**Failure count:** {failure_data['count']}
**First seen:** {failure_data['first_seen']}
**Last seen:** {failure_data['last_seen']}

### Recent Errors
```
{errors_text}
```

### Suggested Investigation
1. Check `/home/{self.citizen}/.env` configuration
2. Check network/API access
3. Check file permissions
4. Review recent changes to related code

### Labels
- `auto-escalated`
- `{self.citizen}`
"""
        
        # Create issue
        try:
            result = subprocess.run(
                ["gh", "issue", "create",
                 "--repo", "experiencenow-ai/infra",
                 "--title", f"[AUTO] {self.citizen}: Repeated failure - {key[:30]}",
                 "--body", issue_body,
                 "--label", "auto-escalated,bug"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd="/home/shared"
            )
            
            issue_url = result.stdout.strip()
            
            # Mark escalated
            self.data[key]["escalated"] = True
            self.data[key]["issue_url"] = issue_url
            self._save()
            
            return f"AUTO-ESCALATED: Created {issue_url}\nStop retrying this operation until issue is resolved."
            
        except Exception as e:
            # Fallback: write to local file for admin
            alert_file = Path("/home/shared/alerts/escalations.json")
            alert_file.parent.mkdir(parents=True, exist_ok=True)
            
            alerts = []
            if alert_file.exists():
                try:
                    alerts = json.loads(alert_file.read_text())
                except:
                    pass
            
            alerts.append({
                "citizen": self.citizen,
                "operation": key,
                "failure_data": failure_data,
                "github_error": str(e),
                "time": now_iso()
            })
            
            alert_file.write_text(json.dumps(alerts, indent=2))
            
            self.data[key]["escalated"] = True
            self._save()
            
            return f"AUTO-ESCALATED (local): Wrote to alerts file. GitHub unavailable: {e}"
    
    def record_success(self, operation: str):
        """Record success - resets failure count."""
        key = self._normalize_key(operation)
        
        if key in self.data:
            # Don't fully delete - keep for history
            self.data[key]["count"] = 0
            self.data[key]["last_success"] = now_iso()
            self.data[key]["escalated"] = False  # Can re-escalate if breaks again
            self._save()
    
    def is_escalated(self, operation: str) -> bool:
        """Check if operation is already escalated."""
        key = self._normalize_key(operation)
        return self.data.get(key, {}).get("escalated", False)
    
    def get_failure_count(self, operation: str) -> int:
        """Get current failure count for operation."""
        key = self._normalize_key(operation)
        return self.data.get(key, {}).get("count", 0)


def track_failure(citizen: str, operation: str, error: str) -> str:
    """Convenience function to track a failure."""
    tracker = FailureTracker(citizen)
    return tracker.record_failure(operation, error)


def track_success(citizen: str, operation: str):
    """Convenience function to track success."""
    tracker = FailureTracker(citizen)
    tracker.record_success(operation)


def check_escalated(citizen: str, operation: str) -> bool:
    """Check if an operation is escalated (should not retry)."""
    tracker = FailureTracker(citizen)
    return tracker.is_escalated(operation)
