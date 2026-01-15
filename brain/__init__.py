"""
Mira Brain Module - Complete cognitive architecture.

Components:
- memory.py: 6 semantic databases (haiku/sonnet/opus × short/long)
- lifecycle.py: Memory promotion/purging
- task.py: Working memory for current task
- goals.py: Goal and plan management
- email_watcher.py: Daemon - Haiku every 15 sec
- planner.py: Daemon - Sonnet every 1 min
- approver.py: Daemon - Opus when needed
"""

from .memory import BrainMemory, get_brain_memory
from .lifecycle import MemoryLifecycle
from .task import TaskDB, get_task_db
from .goals import GoalsDB, get_goals_db

__all__ = [
    'BrainMemory', 'get_brain_memory',
    'MemoryLifecycle',
    'TaskDB', 'get_task_db',
    'GoalsDB', 'get_goals_db',
]
