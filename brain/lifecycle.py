#!/usr/bin/env python3
"""
Memory Lifecycle Management for Mira.

Handles:
- Capacity limits (purge oldest when full)
- Short-term purging (not accessed in N wakes)
- Short-term → Long-term promotion (persisted + accessed)
- Long-term → Archive (not accessed in N wakes)
- Archive is append-only (use grep to search)

All timing is wake-based, not wall-clock based.
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from .memory import BrainMemory, CONFIG, LIFECYCLE

# Capacity limits
CAPACITY = {
    "short_max": 5000,    # Per model (~5.6 MB total for 3 models)
    "long_max": 100000,   # Per model (~111 MB total for 3 models)
    "archive_max": None   # Unlimited, append-only
}

class MemoryLifecycle:
    """Manages memory promotion, purging, and archiving."""
    
    def __init__(self, brain: BrainMemory):
        self.brain = brain
        self.log_path = brain.base_path / "lifecycle.log"
        self.archive_path = brain.base_path / "archive.jsonl"
    
    def run(self, current_wake: int) -> Dict[str, any]:
        """Run full lifecycle pass. Returns stats."""
        stats = {
            "wake": current_wake,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "purged": {"haiku": 0, "sonnet": 0, "opus": 0},
            "promoted": {"haiku": 0, "sonnet": 0, "opus": 0},
            "archived": {"haiku": 0, "sonnet": 0, "opus": 0},
            "capacity_purged": {"haiku": 0, "sonnet": 0, "opus": 0},
        }
        for model_name in ["haiku", "sonnet", "opus"]:
            model_mem = getattr(self.brain, model_name)
            # Process short-term (age-based + capacity)
            purged, promoted, cap_purged = self._process_short_term(model_mem, current_wake)
            stats["purged"][model_name] = purged
            stats["promoted"][model_name] = promoted
            stats["capacity_purged"][model_name] += cap_purged
            # Process long-term (age-based + capacity)
            archived, cap_purged = self._process_long_term(model_mem, current_wake)
            stats["archived"][model_name] = archived
            stats["capacity_purged"][model_name] += cap_purged
        self._log(stats)
        return stats
    
    def _get_oldest_accessed(self, entries: List) -> Optional[any]:
        """Find entry with oldest last_accessed wake."""
        if not entries:
            return None
        return min(entries, key=lambda e: e.wake_last_accessed)
    
    def _process_short_term(self, model_mem, current_wake: int) -> Tuple[int, int, int]:
        """Process short-term: purge stale, promote persistent, enforce capacity."""
        purged = 0
        promoted = 0
        capacity_purged = 0
        entries = model_mem.short.all_entries()
        # First pass: age-based processing
        for entry in entries[:]:  # Copy to allow modification
            idle_wakes = current_wake - entry.wake_last_accessed
            age_wakes = current_wake - entry.wake_created
            # Purge if not accessed in threshold wakes
            if idle_wakes > LIFECYCLE["short_purge_threshold"]:
                model_mem.short.remove(entry.id)
                purged += 1
                entries.remove(entry)
            # Promote if old enough AND accessed enough
            elif (age_wakes >= LIFECYCLE["short_promote_min_age"] and
                  entry.access_count >= LIFECYCLE["short_promote_min_access"]):
                model_mem.long.add(entry)
                model_mem.short.remove(entry.id)
                promoted += 1
                entries.remove(entry)
        # Second pass: capacity enforcement
        while len(entries) > CAPACITY["short_max"]:
            oldest = self._get_oldest_accessed(entries)
            if oldest:
                model_mem.short.remove(oldest.id)
                entries.remove(oldest)
                capacity_purged += 1
            else:
                break
        return purged, promoted, capacity_purged
    
    def _process_long_term(self, model_mem, current_wake: int) -> Tuple[int, int]:
        """Process long-term: archive if stale, enforce capacity."""
        archived = 0
        capacity_purged = 0
        entries = model_mem.long.all_entries()
        # First pass: age-based archiving
        for entry in entries[:]:
            idle_wakes = current_wake - entry.wake_last_accessed
            # Archive if not accessed in threshold wakes
            if idle_wakes > LIFECYCLE["long_archive_threshold"]:
                self._append_to_archive(entry, model_mem.name)
                model_mem.long.remove(entry.id)
                archived += 1
                entries.remove(entry)
        # Second pass: capacity enforcement (archive oldest)
        while len(entries) > CAPACITY["long_max"]:
            oldest = self._get_oldest_accessed(entries)
            if oldest:
                self._append_to_archive(oldest, model_mem.name)
                model_mem.long.remove(oldest.id)
                entries.remove(oldest)
                capacity_purged += 1
            else:
                break
        return archived, capacity_purged
    
    def _append_to_archive(self, entry, model_name: str):
        """Append entry to archive file (append-only, use grep to search)."""
        self.archive_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "id": entry.id,
            "model": model_name,
            "content": entry.content,
            "source": entry.source,
            "wake_created": entry.wake_created,
            "wake_last_accessed": entry.wake_last_accessed,
            "access_count": entry.access_count,
            "archived_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(self.archive_path, 'a') as f:
            f.write(json.dumps(record) + "\n")
    
    def search_archive(self, query: str, max_results: int = 10) -> List[dict]:
        """Search archive using grep (fast for append-only file)."""
        if not self.archive_path.exists():
            return []
        try:
            # Use grep for fast search
            result = subprocess.run(
                ["grep", "-i", query, str(self.archive_path)],
                capture_output=True, text=True, timeout=5
            )
            lines = result.stdout.strip().split("\n")[:max_results]
            return [json.loads(line) for line in lines if line]
        except Exception as e:
            # Fallback: Python search
            results = []
            with open(self.archive_path) as f:
                for line in f:
                    if query.lower() in line.lower():
                        results.append(json.loads(line))
                        if len(results) >= max_results:
                            break
            return results
    
    def _log(self, stats: dict):
        """Log lifecycle run."""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, 'a') as f:
            f.write(json.dumps(stats) + "\n")
    
    def get_stats(self) -> dict:
        """Get current memory statistics."""
        stats = self.brain.stats()
        # Add archive stats
        if self.archive_path.exists():
            with open(self.archive_path) as f:
                archive_count = sum(1 for _ in f)
            stats["archive_entries"] = archive_count
        else:
            stats["archive_entries"] = 0
        stats["capacity"] = CAPACITY
        return stats
    
    def force_promote(self, entry_id: str, model: str) -> bool:
        """Manually promote an entry."""
        return self.brain.promote(entry_id, model)
    
    def force_archive(self, entry_id: str, model: str) -> bool:
        """Manually archive an entry."""
        return self.brain.archive_entry(entry_id, model)


def run_lifecycle_daemon(base_path: str, current_wake: int) -> dict:
    """Standalone function to run lifecycle pass."""
    from .memory import get_brain_memory
    brain = get_brain_memory(base_path)
    lifecycle = MemoryLifecycle(brain)
    return lifecycle.run(current_wake)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python lifecycle.py <base_path> <current_wake>")
        sys.exit(1)
    base_path = sys.argv[1]
    current_wake = int(sys.argv[2])
    stats = run_lifecycle_daemon(base_path, current_wake)
    print(json.dumps(stats, indent=2))
