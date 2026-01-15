"""
Hierarchical Memory - Photographic recall with intelligent retrieval.

Structure:
  /memory/
    /raw/
      /2025/
        /01/
          /15.json    # Full raw events for Jan 15, 2025
          /16.json
    /daily/
      /2025/
        /01/
          /15.json    # Daily summary
    /weekly/
      /2025/
        /03.json      # Week 3 summary
    /monthly/
      /2025/
        /01.json      # January summary
    /annual/
      /2025.json      # 2025 summary

Retrieval: Haiku reads annual → drills to specific day → loads raw.
No compression. No loss. Storage is free.
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
import anthropic

# Use Haiku for all memory operations - it's just retrieval
MEMORY_MODEL = "claude-haiku-4-20250514"
MEMORY_COST = {"input": 0.25, "output": 1.25}

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def today_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def get_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return anthropic.Anthropic(api_key=api_key)


class HierarchicalMemory:
    """Hierarchical memory with photographic recall."""
    
    def __init__(self, citizen: str):
        self.citizen = citizen
        self.base_path = Path(f"/home/{citizen}/memory")
        self._ensure_dirs()
    
    def _ensure_dirs(self):
        """Create directory structure."""
        for subdir in ["raw", "daily", "weekly", "monthly", "annual"]:
            (self.base_path / subdir).mkdir(parents=True, exist_ok=True)
    
    # =========================================================================
    # STORAGE - Write raw events and summaries
    # =========================================================================
    
    def record_event(self, event: dict):
        """
        Record a raw event. Called after every significant action.
        
        event = {
            "timestamp": "2025-01-15T10:30:00Z",
            "type": "task_complete" | "email_sent" | "goal_added" | etc,
            "details": {...}
        }
        """
        ts = event.get("timestamp", now_iso())
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        
        # Path: /memory/raw/2025/01/15.json
        year = dt.strftime("%Y")
        month = dt.strftime("%m")
        day = dt.strftime("%d")
        
        raw_dir = self.base_path / "raw" / year / month
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_file = raw_dir / f"{day}.json"
        
        # Load existing or create new
        if raw_file.exists():
            data = json.loads(raw_file.read_text())
        else:
            data = {"date": f"{year}-{month}-{day}", "events": []}
        
        data["events"].append(event)
        raw_file.write_text(json.dumps(data, indent=2))
    
    def record_wake(self, wake_num: int, summary: str, tokens: int, cost: float):
        """Record wake summary as event."""
        self.record_event({
            "timestamp": now_iso(),
            "type": "wake",
            "details": {
                "wake_num": wake_num,
                "summary": summary,
                "tokens_used": tokens,
                "cost": cost
            }
        })
    
    def build_daily_summary(self, date_str: str, session: dict) -> str:
        """
        Build daily summary from raw events.
        Called at end of day or when needed.
        
        date_str: "2025-01-15"
        """
        year, month, day = date_str.split("-")
        raw_file = self.base_path / "raw" / year / month / f"{day}.json"
        
        if not raw_file.exists():
            return ""
        
        raw_data = json.loads(raw_file.read_text())
        events = raw_data.get("events", [])
        
        if not events:
            return ""
        
        # Ask Haiku to summarize
        events_text = "\n".join([
            f"- [{e.get('type', '?')}] {json.dumps(e.get('details', {}))[:200]}"
            for e in events
        ])
        
        prompt = f"""Summarize this day's events in 2-3 sentences. Focus on outcomes and progress.

DATE: {date_str}
EVENTS:
{events_text}

Summary:"""
        
        summary = self._query_haiku(prompt, session)
        
        # Save daily summary
        daily_dir = self.base_path / "daily" / year / month
        daily_dir.mkdir(parents=True, exist_ok=True)
        daily_file = daily_dir / f"{day}.json"
        daily_file.write_text(json.dumps({
            "date": date_str,
            "event_count": len(events),
            "summary": summary
        }, indent=2))
        
        return summary
    
    def build_weekly_summary(self, year: str, week: int, session: dict) -> str:
        """Build weekly summary from daily summaries."""
        # Get all days in this week
        daily_summaries = []
        
        # Calculate week start (Monday)
        jan1 = datetime(int(year), 1, 1)
        week_start = jan1 + timedelta(weeks=week-1, days=-jan1.weekday())
        
        for i in range(7):
            day = week_start + timedelta(days=i)
            if day.year != int(year):
                continue
            
            date_str = day.strftime("%Y-%m-%d")
            y, m, d = date_str.split("-")
            daily_file = self.base_path / "daily" / y / m / f"{d}.json"
            
            if daily_file.exists():
                data = json.loads(daily_file.read_text())
                daily_summaries.append(f"{date_str}: {data.get('summary', '(no summary)')}")
        
        if not daily_summaries:
            return ""
        
        prompt = f"""Summarize this week in 2-3 sentences. Focus on key accomplishments and themes.

WEEK {week} OF {year}:
{chr(10).join(daily_summaries)}

Summary:"""
        
        summary = self._query_haiku(prompt, session)
        
        # Save
        weekly_dir = self.base_path / "weekly" / year
        weekly_dir.mkdir(parents=True, exist_ok=True)
        weekly_file = weekly_dir / f"{week:02d}.json"
        weekly_file.write_text(json.dumps({
            "year": year,
            "week": week,
            "summary": summary
        }, indent=2))
        
        return summary
    
    def build_monthly_summary(self, year: str, month: str, session: dict) -> str:
        """Build monthly summary from weekly summaries."""
        weekly_dir = self.base_path / "weekly" / year
        weekly_summaries = []
        
        # Find weeks in this month (approximate)
        for week_file in sorted(weekly_dir.glob("*.json")):
            data = json.loads(week_file.read_text())
            weekly_summaries.append(f"Week {data['week']}: {data.get('summary', '')}")
        
        if not weekly_summaries:
            return ""
        
        prompt = f"""Summarize this month in 2-3 sentences. Focus on major themes and outcomes.

{year}-{month}:
{chr(10).join(weekly_summaries)}

Summary:"""
        
        summary = self._query_haiku(prompt, session)
        
        # Save
        monthly_dir = self.base_path / "monthly" / year
        monthly_dir.mkdir(parents=True, exist_ok=True)
        monthly_file = monthly_dir / f"{month}.json"
        monthly_file.write_text(json.dumps({
            "year": year,
            "month": month,
            "summary": summary
        }, indent=2))
        
        return summary
    
    def build_annual_summary(self, year: str, session: dict) -> str:
        """Build annual summary from monthly summaries."""
        monthly_dir = self.base_path / "monthly" / year
        monthly_summaries = []
        
        for month_file in sorted(monthly_dir.glob("*.json")):
            data = json.loads(month_file.read_text())
            month_name = datetime(int(year), int(data['month']), 1).strftime("%B")
            monthly_summaries.append(f"{month_name}: {data.get('summary', '')}")
        
        if not monthly_summaries:
            return ""
        
        prompt = f"""Summarize this year in 3-4 sentences. Focus on major accomplishments and growth.

{year}:
{chr(10).join(monthly_summaries)}

Summary:"""
        
        summary = self._query_haiku(prompt, session)
        
        # Save
        annual_file = self.base_path / "annual" / f"{year}.json"
        annual_file.parent.mkdir(parents=True, exist_ok=True)
        annual_file.write_text(json.dumps({
            "year": year,
            "summary": summary
        }, indent=2))
        
        return summary
    
    # =========================================================================
    # RETRIEVAL - Drill down from coarse to fine
    # =========================================================================
    
    def recall(self, query: str, session: dict) -> dict:
        """
        Recall memories relevant to a query.
        
        Searches RECENT FIRST, expands scope if not found:
        1. Last 7 days raw (no AI needed, just search)
        2. Last 4 weeks summaries
        3. Last 6 months summaries
        4. Annual summaries
        
        Returns:
            {
                "path": ["2025", "01", "15"],
                "summary": "...",
                "raw_events": [...]
            }
        """
        result = {
            "path": [],
            "summary": "",
            "raw_events": [],
            "search_log": []
        }
        
        # Step 1: Search last 7 days raw (FREE - just string matching)
        recent_events = self.recall_recent(days=7)
        if recent_events:
            matches = self._filter_events_by_query(recent_events, query)
            if matches:
                result["search_log"].append(f"Found {len(matches)} matches in last 7 days")
                result["raw_events"] = matches
                result["summary"] = self._summarize_matches(matches, query, session)
                if matches:
                    result["path"] = [matches[0].get("_date", "recent")]
                return result
        
        result["search_log"].append("Not in last 7 days, checking weeks...")
        
        # Step 2: Check last 4 weeks summaries
        found = self._search_weekly_summaries(query, weeks=4, session=session)
        if found:
            result["search_log"].append(f"Found in week summary: {found['week']}")
            # Load raw events for that week
            raw = self._load_week_raw(found["year"], found["week"])
            matches = self._filter_events_by_query(raw, query)
            result["raw_events"] = matches
            result["summary"] = found.get("summary", "")
            result["path"] = [found["year"], f"W{found['week']}"]
            return result
        
        result["search_log"].append("Not in last 4 weeks, checking months...")
        
        # Step 3: Check last 6 months summaries
        found = self._search_monthly_summaries(query, months=6, session=session)
        if found:
            result["search_log"].append(f"Found in month: {found['year']}-{found['month']}")
            # Drill to week within that month
            weekly = self._search_weekly_in_month(query, found["year"], found["month"], session)
            if weekly:
                raw = self._load_week_raw(found["year"], weekly["week"])
                matches = self._filter_events_by_query(raw, query)
                result["raw_events"] = matches
            result["summary"] = found.get("summary", "")
            result["path"] = [found["year"], found["month"]]
            return result
        
        result["search_log"].append("Not in last 6 months, checking annual...")
        
        # Step 4: Check annual summaries (oldest data)
        found = self._search_annual_summaries(query, session)
        if found:
            result["search_log"].append(f"Found in year: {found['year']}")
            result["summary"] = found.get("summary", "")
            result["path"] = [found["year"]]
            # Could drill deeper but likely very old
            return result
        
        result["summary"] = f"No memories found for: {query}"
        return result
    
    def _filter_events_by_query(self, events: list, query: str) -> list:
        """Simple keyword matching on events (no AI needed)."""
        query_words = query.lower().split()
        matches = []
        
        for e in events:
            event_text = json.dumps(e).lower()
            if any(word in event_text for word in query_words):
                matches.append(e)
        
        return matches
    
    def _summarize_matches(self, matches: list, query: str, session: dict) -> str:
        """Use Haiku to summarize matched events."""
        if not matches:
            return ""
        
        events_text = "\n".join([
            f"[{e.get('_date', '?')} {e.get('type', '?')}] {json.dumps(e.get('details', {}))[:200]}"
            for e in matches[:10]
        ])
        
        prompt = f"""Summarize these events related to "{query}" in 2-3 sentences:

{events_text}

Summary:"""
        
        return self._query_haiku(prompt, session)
    
    def _search_weekly_summaries(self, query: str, weeks: int, session: dict) -> Optional[dict]:
        """Search recent week summaries."""
        today = datetime.now(timezone.utc)
        
        summaries = []
        for i in range(weeks):
            check_date = today - timedelta(weeks=i)
            year = check_date.strftime("%Y")
            week = check_date.isocalendar()[1]
            
            weekly_file = self.base_path / "weekly" / year / f"{week:02d}.json"
            if weekly_file.exists():
                data = json.loads(weekly_file.read_text())
                summaries.append({
                    "year": year,
                    "week": week,
                    "summary": data.get("summary", "")
                })
        
        if not summaries:
            return None
        
        # Ask Haiku which week matches
        weeks_text = "\n".join([
            f"{s['year']}-W{s['week']:02d}: {s['summary']}"
            for s in summaries
        ])
        
        prompt = f"""Which week has info about: {query}
Reply with "YEAR-WEEK" (e.g., "2025-W03") or "none".

{weeks_text}

Week:"""
        
        result = self._query_haiku(prompt, session).strip()
        
        if result == "none" or "-W" not in result:
            return None
        
        try:
            year, week_str = result.split("-W")
            week = int(week_str)
            for s in summaries:
                if s["year"] == year and s["week"] == week:
                    return s
        except:
            pass
        
        return None
    
    def _search_monthly_summaries(self, query: str, months: int, session: dict) -> Optional[dict]:
        """Search recent month summaries."""
        today = datetime.now(timezone.utc)
        
        summaries = []
        for i in range(months):
            check_date = today - timedelta(days=30*i)
            year = check_date.strftime("%Y")
            month = check_date.strftime("%m")
            
            monthly_file = self.base_path / "monthly" / year / f"{month}.json"
            if monthly_file.exists():
                data = json.loads(monthly_file.read_text())
                summaries.append({
                    "year": year,
                    "month": month,
                    "summary": data.get("summary", "")
                })
        
        if not summaries:
            return None
        
        months_text = "\n".join([
            f"{s['year']}-{s['month']}: {s['summary']}"
            for s in summaries
        ])
        
        prompt = f"""Which month has info about: {query}
Reply with "YYYY-MM" (e.g., "2025-01") or "none".

{months_text}

Month:"""
        
        result = self._query_haiku(prompt, session).strip()
        
        if result == "none" or len(result) != 7:
            return None
        
        try:
            year, month = result.split("-")
            for s in summaries:
                if s["year"] == year and s["month"] == month:
                    return s
        except:
            pass
        
        return None
    
    def _search_weekly_in_month(self, query: str, year: str, month: str, session: dict) -> Optional[dict]:
        """Search weeks within a specific month."""
        weekly_dir = self.base_path / "weekly" / year
        if not weekly_dir.exists():
            return None
        
        # Find weeks that fall in this month (approximate)
        summaries = []
        for weekly_file in weekly_dir.glob("*.json"):
            data = json.loads(weekly_file.read_text())
            summaries.append({
                "week": data.get("week", int(weekly_file.stem)),
                "summary": data.get("summary", "")
            })
        
        if not summaries:
            return None
        
        weeks_text = "\n".join([f"W{s['week']:02d}: {s['summary']}" for s in summaries])
        
        prompt = f"""Which week in {year} has info about: {query}
Reply with week number (e.g., "03") or "none".

{weeks_text}

Week:"""
        
        result = self._query_haiku(prompt, session).strip()
        
        if result == "none":
            return None
        
        try:
            week = int(result.replace("W", ""))
            return {"week": week}
        except:
            return None
    
    def _search_annual_summaries(self, query: str, session: dict) -> Optional[dict]:
        """Search annual summaries."""
        annual_dir = self.base_path / "annual"
        if not annual_dir.exists():
            return None
        
        summaries = []
        for annual_file in sorted(annual_dir.glob("*.json"), reverse=True):
            data = json.loads(annual_file.read_text())
            summaries.append({
                "year": data.get("year", annual_file.stem),
                "summary": data.get("summary", "")
            })
        
        if not summaries:
            return None
        
        years_text = "\n".join([f"{s['year']}: {s['summary']}" for s in summaries])
        
        prompt = f"""Which year has info about: {query}
Reply with year (e.g., "2025") or "none".

{years_text}

Year:"""
        
        result = self._query_haiku(prompt, session).strip()
        
        if result == "none" or not result.isdigit():
            return None
        
        for s in summaries:
            if s["year"] == result:
                return s
        
        return None
    
    def _load_week_raw(self, year: str, week: int) -> list:
        """Load all raw events for a given week."""
        events = []
        
        # Calculate week start (Monday)
        jan1 = datetime(int(year), 1, 1)
        week_start = jan1 + timedelta(weeks=week-1, days=-jan1.weekday())
        
        for i in range(7):
            day = week_start + timedelta(days=i)
            if day.year != int(year):
                continue
            
            date_str = day.strftime("%Y-%m-%d")
            y, m, d = date_str.split("-")
            raw_file = self.base_path / "raw" / y / m / f"{d}.json"
            
            if raw_file.exists():
                data = json.loads(raw_file.read_text())
                for e in data.get("events", []):
                    e["_date"] = date_str
                    events.append(e)
        
        return events
    
    def recall_recent(self, days: int = 7) -> list:
        """Get raw events from last N days."""
        events = []
        today = datetime.now(timezone.utc)
        
        for i in range(days):
            day = today - timedelta(days=i)
            year = day.strftime("%Y")
            month = day.strftime("%m")
            day_str = day.strftime("%d")
            
            raw_file = self.base_path / "raw" / year / month / f"{day_str}.json"
            if raw_file.exists():
                data = json.loads(raw_file.read_text())
                for e in data.get("events", []):
                    e["_date"] = f"{year}-{month}-{day_str}"
                    events.append(e)
        
        return events
    
    def get_context_for_wake(self, session: dict) -> str:
        """
        Get memory context for current wake.
        Returns recent events + relevant summaries.
        """
        parts = []
        
        # Recent events (last 3 days raw)
        recent = self.recall_recent(days=3)
        if recent:
            parts.append("=== RECENT EVENTS (last 3 days) ===")
            for e in recent[-20:]:  # Last 20 events
                parts.append(f"[{e.get('_date', '?')} {e.get('type', '?')}] {str(e.get('details', ''))[:100]}")
        
        # Current month summary
        today = datetime.now(timezone.utc)
        monthly_file = self.base_path / "monthly" / today.strftime("%Y") / f"{today.strftime('%m')}.json"
        if monthly_file.exists():
            data = json.loads(monthly_file.read_text())
            parts.append(f"\n=== THIS MONTH ===\n{data.get('summary', '')}")
        
        return "\n".join(parts) if parts else "(no memory context)"
    
    # =========================================================================
    # UTILITIES
    # =========================================================================
    
    def _query_haiku(self, prompt: str, session: dict) -> str:
        """Query Haiku for memory operations."""
        try:
            client = get_client()
            response = client.messages.create(
                model=MEMORY_MODEL,
                max_tokens=500,
                temperature=0.0,  # Deterministic for retrieval
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Track costs
            session["tokens_used"] = session.get("tokens_used", 0) + \
                response.usage.input_tokens + response.usage.output_tokens
            session["cost"] = session.get("cost", 0) + \
                (response.usage.input_tokens * MEMORY_COST["input"] + 
                 response.usage.output_tokens * MEMORY_COST["output"]) / 1_000_000
            
            return response.content[0].text
            
        except Exception as e:
            print(f"[MEMORY ERROR] {e}")
            return ""
    
    def get_stats(self) -> dict:
        """Get memory statistics."""
        stats = {"raw_days": 0, "total_events": 0}
        
        raw_dir = self.base_path / "raw"
        if raw_dir.exists():
            for year_dir in raw_dir.iterdir():
                for month_dir in year_dir.iterdir():
                    for day_file in month_dir.glob("*.json"):
                        stats["raw_days"] += 1
                        data = json.loads(day_file.read_text())
                        stats["total_events"] += len(data.get("events", []))
        
        return stats


# Module-level functions

_memories = {}

def get_memory(citizen: str) -> HierarchicalMemory:
    """Get or create memory for citizen."""
    if citizen not in _memories:
        _memories[citizen] = HierarchicalMemory(citizen)
    return _memories[citizen]

def record_event(citizen: str, event: dict):
    """Record an event."""
    get_memory(citizen).record_event(event)

def recall(citizen: str, query: str, session: dict) -> dict:
    """Recall memories."""
    return get_memory(citizen).recall(query, session)

def get_context_for_wake(citizen: str, session: dict) -> str:
    """Get memory context for wake."""
    return get_memory(citizen).get_context_for_wake(session)
