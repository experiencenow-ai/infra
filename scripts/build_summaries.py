#!/usr/bin/env python3
"""
Build Memory Summaries

Run daily/weekly/monthly to build hierarchical summaries from raw data.

Usage:
    ./build_summaries.py --daily              # Build yesterday's summary
    ./build_summaries.py --daily --date 2025-01-15
    ./build_summaries.py --weekly             # Build last week's summary
    ./build_summaries.py --monthly            # Build last month's summary
    ./build_summaries.py --all                # Build all missing summaries
"""

import argparse
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add modules to path
SCRIPT_DIR = Path(__file__).parent.parent
MODULES_DIR = SCRIPT_DIR / "modules"
sys.path.insert(0, str(MODULES_DIR))

def load_env(citizen: str):
    """Load environment variables from citizen's .env file."""
    env_file = Path(f"/home/{citizen}/.env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip().strip('"\'')

def build_daily(citizen: str, date_str: str):
    """Build daily summary for a specific date."""
    import memory
    
    # Create minimal session for tracking
    session = {"tokens_used": 0, "cost": 0}
    
    mem = memory.get_memory(citizen)
    summary = mem.build_daily_summary(date_str, session)
    
    if summary:
        print(f"  [{citizen}] {date_str}: {summary[:60]}...")
    else:
        print(f"  [{citizen}] {date_str}: (no events)")
    
    return session

def build_weekly(citizen: str, year: str, week: int):
    """Build weekly summary."""
    import memory
    
    session = {"tokens_used": 0, "cost": 0}
    
    mem = memory.get_memory(citizen)
    summary = mem.build_weekly_summary(year, week, session)
    
    if summary:
        print(f"  [{citizen}] {year}-W{week:02d}: {summary[:60]}...")
    else:
        print(f"  [{citizen}] {year}-W{week:02d}: (no data)")
    
    return session

def build_monthly(citizen: str, year: str, month: str):
    """Build monthly summary."""
    import memory
    
    session = {"tokens_used": 0, "cost": 0}
    
    mem = memory.get_memory(citizen)
    summary = mem.build_monthly_summary(year, month, session)
    
    if summary:
        print(f"  [{citizen}] {year}-{month}: {summary[:60]}...")
    else:
        print(f"  [{citizen}] {year}-{month}: (no data)")
    
    return session

def build_annual(citizen: str, year: str):
    """Build annual summary."""
    import memory
    
    session = {"tokens_used": 0, "cost": 0}
    
    mem = memory.get_memory(citizen)
    summary = mem.build_annual_summary(year, session)
    
    if summary:
        print(f"  [{citizen}] {year}: {summary[:60]}...")
    else:
        print(f"  [{citizen}] {year}: (no data)")
    
    return session

def main():
    parser = argparse.ArgumentParser(description="Build memory summaries")
    parser.add_argument("--daily", action="store_true", help="Build daily summary")
    parser.add_argument("--weekly", action="store_true", help="Build weekly summary")
    parser.add_argument("--monthly", action="store_true", help="Build monthly summary")
    parser.add_argument("--annual", action="store_true", help="Build annual summary")
    parser.add_argument("--all", action="store_true", help="Build all missing summaries")
    parser.add_argument("--date", help="Specific date (YYYY-MM-DD)")
    parser.add_argument("--citizen", help="Specific citizen (default: all)")
    args = parser.parse_args()
    
    citizens = [args.citizen] if args.citizen else ["opus", "mira", "aria"]
    
    # Load env from first citizen with API key
    for c in citizens:
        load_env(c)
        if os.environ.get("ANTHROPIC_API_KEY"):
            break
    
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[ERROR] No ANTHROPIC_API_KEY found")
        sys.exit(1)
    
    total_tokens = 0
    total_cost = 0
    
    today = datetime.now(timezone.utc)
    
    if args.daily:
        if args.date:
            date_str = args.date
        else:
            # Yesterday
            yesterday = today - timedelta(days=1)
            date_str = yesterday.strftime("%Y-%m-%d")
        
        print(f"Building daily summaries for {date_str}...")
        for citizen in citizens:
            session = build_daily(citizen, date_str)
            total_tokens += session["tokens_used"]
            total_cost += session["cost"]
    
    if args.weekly:
        # Last week
        last_week = today - timedelta(weeks=1)
        year = last_week.strftime("%Y")
        week = last_week.isocalendar()[1]
        
        print(f"Building weekly summaries for {year}-W{week:02d}...")
        for citizen in citizens:
            session = build_weekly(citizen, year, week)
            total_tokens += session["tokens_used"]
            total_cost += session["cost"]
    
    if args.monthly:
        # Last month
        first_of_month = today.replace(day=1)
        last_month = first_of_month - timedelta(days=1)
        year = last_month.strftime("%Y")
        month = last_month.strftime("%m")
        
        print(f"Building monthly summaries for {year}-{month}...")
        for citizen in citizens:
            session = build_monthly(citizen, year, month)
            total_tokens += session["tokens_used"]
            total_cost += session["cost"]
    
    if args.annual:
        # Last year (or current if we're in January)
        if today.month == 1:
            year = str(today.year - 1)
        else:
            year = str(today.year)
        
        print(f"Building annual summaries for {year}...")
        for citizen in citizens:
            session = build_annual(citizen, year)
            total_tokens += session["tokens_used"]
            total_cost += session["cost"]
    
    if args.all:
        print("Building all missing summaries...")
        # TODO: Scan for missing summaries and build them
        print("  (not yet implemented)")
    
    print(f"\nTotal: {total_tokens:,} tokens, ${total_cost:.4f}")

if __name__ == "__main__":
    main()
