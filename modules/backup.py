"""
Cross-Backup System - Citizens back each other up.

Rules:
1. During PEER_MONITOR wake: backup the peer being monitored
2. During REFLECTION wake: backup self
3. Backups stored in /home/{citizen}/backups/{target}/

This creates redundancy - each citizen's data exists in 3 places:
- Their own home
- Backed up by 2 other citizens

Backup includes:
- contexts/
- metadata.json
- config.json
- experiences/index.json
- blockchain_watch.json (if exists)
"""

import json
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

def now_iso():
    return datetime.now(timezone.utc).isoformat()


CITIZENS = ["opus", "mira", "aria"]

# What to backup
BACKUP_ITEMS = [
    "contexts",           # All context files
    "metadata.json",      # Wake counts, costs
    "config.json",        # Configuration (not .env!)
    "blockchain_watch.json",  # Watch list
    "experiences/index.json", # Experience index
    "background_tasks.json",  # Task scheduler state
]

# What NOT to backup (sensitive)
EXCLUDE_PATTERNS = [
    ".env",               # API keys!
    "*.log",              # Logs
    "logs/*",             # Log directory
    "cache/*",            # Cache
    "__pycache__",        # Python cache
    "*.pyc",              # Compiled Python
]


class BackupManager:
    """Manage citizen backups."""
    
    def __init__(self, citizen: str):
        self.citizen = citizen
        self.home = Path(f"/home/{citizen}")
        self.backup_dir = self.home / "backups"
        self.backup_dir.mkdir(exist_ok=True)
    
    def backup_peer(self, peer: str) -> dict:
        """
        Backup a peer's data.
        Called during peer_monitor wake.
        
        Returns:
            {"success": bool, "message": str, "size_kb": int}
        """
        if peer == self.citizen:
            return {"success": False, "message": "Cannot backup self with backup_peer"}
        
        if peer not in CITIZENS:
            return {"success": False, "message": f"Unknown peer: {peer}"}
        
        peer_home = Path(f"/home/{peer}")
        if not peer_home.exists():
            return {"success": False, "message": f"Peer home not found: {peer_home}"}
        
        # Create peer backup directory
        peer_backup_dir = self.backup_dir / peer
        peer_backup_dir.mkdir(exist_ok=True)
        
        # Generate backup filename
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_file = peer_backup_dir / f"{peer}_{ts}.tar.gz"
        
        try:
            return self._create_backup(peer_home, backup_file, peer)
        except Exception as e:
            return {"success": False, "message": f"Backup failed: {e}"}
    
    def backup_self(self) -> dict:
        """
        Backup own data.
        Called during reflection wake.
        
        Returns:
            {"success": bool, "message": str, "size_kb": int}
        """
        # Create self backup directory
        self_backup_dir = self.backup_dir / self.citizen
        self_backup_dir.mkdir(exist_ok=True)
        
        # Generate backup filename
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_file = self_backup_dir / f"{self.citizen}_{ts}.tar.gz"
        
        try:
            return self._create_backup(self.home, backup_file, self.citizen)
        except Exception as e:
            return {"success": False, "message": f"Backup failed: {e}"}
    
    def _create_backup(self, source_dir: Path, backup_file: Path, target: str) -> dict:
        """Create tar.gz backup of specified items."""
        
        with tarfile.open(backup_file, "w:gz") as tar:
            for item in BACKUP_ITEMS:
                item_path = source_dir / item
                if item_path.exists():
                    # Add to archive with relative path
                    arcname = f"{target}/{item}"
                    tar.add(item_path, arcname=arcname)
        
        # Get size
        size_kb = backup_file.stat().st_size // 1024
        
        # Cleanup old backups (keep last 5)
        self._cleanup_old_backups(backup_file.parent, keep=5)
        
        return {
            "success": True,
            "message": f"Backed up {target} to {backup_file.name}",
            "file": str(backup_file),
            "size_kb": size_kb
        }
    
    def _cleanup_old_backups(self, backup_dir: Path, keep: int = 5):
        """Remove old backups, keeping most recent N."""
        backups = sorted(backup_dir.glob("*.tar.gz"))
        if len(backups) > keep:
            for old in backups[:-keep]:
                old.unlink()
    
    def list_backups(self, target: str = None) -> List[dict]:
        """List available backups."""
        results = []
        
        dirs = [self.backup_dir / target] if target else list(self.backup_dir.iterdir())
        
        for d in dirs:
            if d.is_dir():
                for backup_file in sorted(d.glob("*.tar.gz")):
                    results.append({
                        "target": d.name,
                        "file": backup_file.name,
                        "size_kb": backup_file.stat().st_size // 1024,
                        "time": datetime.fromtimestamp(backup_file.stat().st_mtime).isoformat()
                    })
        
        return results
    
    def restore(self, target: str, backup_name: str = None) -> dict:
        """
        Restore a backup.
        If backup_name not specified, uses most recent.
        
        WARNING: This overwrites existing data!
        """
        backup_dir = self.backup_dir / target
        if not backup_dir.exists():
            return {"success": False, "message": f"No backups for {target}"}
        
        # Find backup file
        if backup_name:
            backup_file = backup_dir / backup_name
        else:
            backups = sorted(backup_dir.glob("*.tar.gz"))
            if not backups:
                return {"success": False, "message": f"No backups found for {target}"}
            backup_file = backups[-1]  # Most recent
        
        if not backup_file.exists():
            return {"success": False, "message": f"Backup not found: {backup_file}"}
        
        # Determine restore target
        target_dir = Path(f"/home/{target}")
        if not target_dir.exists():
            return {"success": False, "message": f"Target directory not found: {target_dir}"}
        
        try:
            # Extract backup
            with tarfile.open(backup_file, "r:gz") as tar:
                # Extract to temp location first
                temp_dir = Path(f"/tmp/restore_{target}")
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
                tar.extractall(temp_dir)
                
                # Copy files to target
                extracted = temp_dir / target
                if extracted.exists():
                    for item in extracted.iterdir():
                        dest = target_dir / item.name
                        if item.is_dir():
                            if dest.exists():
                                shutil.rmtree(dest)
                            shutil.copytree(item, dest)
                        else:
                            shutil.copy2(item, dest)
                
                # Cleanup
                shutil.rmtree(temp_dir)
            
            return {
                "success": True,
                "message": f"Restored {target} from {backup_file.name}",
                "file": str(backup_file)
            }
        except Exception as e:
            return {"success": False, "message": f"Restore failed: {e}"}
    
    def get_backup_status(self) -> str:
        """Get formatted backup status."""
        lines = ["=== BACKUP STATUS ===", ""]
        
        # List backups by target
        for target in CITIZENS:
            target_dir = self.backup_dir / target
            if target_dir.exists():
                backups = sorted(target_dir.glob("*.tar.gz"))
                if backups:
                    latest = backups[-1]
                    age = datetime.now() - datetime.fromtimestamp(latest.stat().st_mtime)
                    age_str = f"{age.days}d {age.seconds//3600}h" if age.days else f"{age.seconds//3600}h"
                    lines.append(f"  {target}: {len(backups)} backups, latest {age_str} ago")
                else:
                    lines.append(f"  {target}: no backups")
            else:
                lines.append(f"  {target}: no backup dir")
        
        return "\n".join(lines)


# =============================================================================
# Integration with wakes
# =============================================================================

def backup_peer_in_monitor(session: dict, peer: str) -> str:
    """Called during peer_monitor wake to backup peer."""
    manager = BackupManager(session["citizen"])
    result = manager.backup_peer(peer)
    
    if result["success"]:
        return f"✓ Backed up {peer}: {result['size_kb']}KB"
    else:
        return f"✗ Backup failed: {result['message']}"


def backup_self_in_reflection(session: dict) -> str:
    """Called during reflection wake to backup self."""
    manager = BackupManager(session["citizen"])
    result = manager.backup_self()
    
    if result["success"]:
        return f"✓ Self backup: {result['size_kb']}KB"
    else:
        return f"✗ Self backup failed: {result['message']}"


# =============================================================================
# Tool Functions
# =============================================================================

def backup_peer_tool(args: dict, session: dict, modules: dict) -> str:
    """Backup a peer's data."""
    peer = args.get("peer", "")
    if not peer:
        return "ERROR: Peer name required"
    
    manager = BackupManager(session["citizen"])
    result = manager.backup_peer(peer)
    
    return result["message"]


def backup_self_tool(args: dict, session: dict, modules: dict) -> str:
    """Backup own data."""
    manager = BackupManager(session["citizen"])
    result = manager.backup_self()
    
    return result["message"]


def backup_list_tool(args: dict, session: dict, modules: dict) -> str:
    """List available backups."""
    manager = BackupManager(session["citizen"])
    backups = manager.list_backups(args.get("target"))
    
    if not backups:
        return "No backups found."
    
    lines = ["=== BACKUPS ==="]
    current_target = None
    for b in backups:
        if b["target"] != current_target:
            current_target = b["target"]
            lines.append(f"\n{current_target}:")
        lines.append(f"  {b['file']} ({b['size_kb']}KB)")
    
    return "\n".join(lines)


def backup_status_tool(args: dict, session: dict, modules: dict) -> str:
    """Get backup status."""
    manager = BackupManager(session["citizen"])
    return manager.get_backup_status()


BACKUP_TOOL_DEFINITIONS = [
    {
        "name": "backup_peer",
        "description": "Backup a peer's data (for redundancy)",
        "input_schema": {
            "type": "object",
            "properties": {
                "peer": {"type": "string", "description": "Peer name to backup"}
            },
            "required": ["peer"]
        }
    },
    {
        "name": "backup_self",
        "description": "Backup your own data",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "backup_list",
        "description": "List available backups",
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Filter by target (optional)"}
            }
        }
    },
    {
        "name": "backup_status",
        "description": "Show backup status for all citizens",
        "input_schema": {"type": "object", "properties": {}}
    }
]
