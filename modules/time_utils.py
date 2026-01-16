"""
Time utilities - DRY solution for timestamp generation.

This module provides shared time/date functions to eliminate duplication
across the codebase.
"""

from datetime import datetime, timezone


def now_iso():
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def now_timestamp():
    """Return current UTC time as Unix timestamp (float)."""
    return datetime.now(timezone.utc).timestamp()


def today_str():
    """Return current UTC date as YYYY-MM-DD string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
