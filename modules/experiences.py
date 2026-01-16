"""
Experiences Context - Personal learnings accumulated over time.

This replaces/extends the Library concept. Instead of shared specialist knowledge,
each AI builds their own unique experiences that can be searched.

Experiences are:
1. Automatically captured from successful wake outcomes
2. Manually added via experience_add tool
3. Searchable via experience_search tool
4. Compressed over time (older → more abstract)

Structure:
  /home/{citizen}/experiences/
    index.json        - Full-text searchable index
    raw/              - Recent raw experiences (last 30 days)
    compressed/       - Older experiences summarized
"""

import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from .time_utils import now_iso




class ExperienceStore:
    """Store and search personal experiences."""
    
    def __init__(self, citizen: str):
        self.citizen = citizen
        self.base_dir = Path(f"/home/{citizen}/experiences")
        self.index_file = self.base_dir / "index.json"
        self.raw_dir = self.base_dir / "raw"
        self.compressed_dir = self.base_dir / "compressed"
        self._ensure_dirs()
        self.index = self._load_index()
    
    def _ensure_dirs(self):
        """Create directory structure."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(exist_ok=True)
        self.compressed_dir.mkdir(exist_ok=True)
    
    def _load_index(self) -> dict:
        """Load or create index."""
        if self.index_file.exists():
            try:
                return json.loads(self.index_file.read_text())
            except:
                pass
        return {
            "version": 1,
            "citizen": self.citizen,
            "created": now_iso(),
            "total_count": 0,
            "categories": {},
            "entries": []  # [{id, timestamp, category, summary, keywords, file}]
        }
    
    def _save_index(self):
        """Save index."""
        self.index_file.write_text(json.dumps(self.index, indent=2))
    
    def add(self, content: str, category: str = "general", 
            summary: str = None, keywords: List[str] = None,
            context: dict = None) -> str:
        """
        Add a new experience.
        
        Args:
            content: Full experience description
            category: Type (code, debug, research, communication, etc.)
            summary: Short summary (auto-generated if not provided)
            keywords: Search keywords (auto-extracted if not provided)
            context: Additional context (wake_num, task_id, etc.)
        
        Returns:
            Experience ID
        """
        # Generate ID
        ts = datetime.now(timezone.utc)
        exp_id = f"{ts.strftime('%Y%m%d_%H%M%S')}_{len(self.index['entries']) % 1000:03d}"
        
        # Auto-generate summary if not provided
        if not summary:
            summary = content[:200].replace("\n", " ").strip()
            if len(content) > 200:
                summary += "..."
        
        # Auto-extract keywords
        if not keywords:
            keywords = self._extract_keywords(content)
        
        # Create experience entry
        entry = {
            "id": exp_id,
            "timestamp": now_iso(),
            "category": category,
            "summary": summary,
            "keywords": keywords,
            "context": context or {}
        }
        
        # Save full content to file
        exp_file = self.raw_dir / f"{exp_id}.json"
        exp_data = {
            **entry,
            "content": content
        }
        exp_file.write_text(json.dumps(exp_data, indent=2))
        entry["file"] = str(exp_file.relative_to(self.base_dir))
        
        # Update index
        self.index["entries"].append(entry)
        self.index["total_count"] += 1
        self.index["categories"][category] = self.index["categories"].get(category, 0) + 1
        self._save_index()
        
        return exp_id
    
    def _extract_keywords(self, content: str) -> List[str]:
        """Extract searchable keywords from content."""
        # Remove common words, keep meaningful ones
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "must", "shall", "can", "need", "dare",
            "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
            "into", "through", "during", "before", "after", "above", "below",
            "between", "under", "again", "further", "then", "once", "here",
            "there", "when", "where", "why", "how", "all", "each", "few",
            "more", "most", "other", "some", "such", "no", "nor", "not",
            "only", "own", "same", "so", "than", "too", "very", "just",
            "and", "but", "if", "or", "because", "until", "while", "this",
            "that", "these", "those", "i", "me", "my", "myself", "we", "our",
            "you", "your", "he", "him", "his", "she", "her", "it", "its",
            "they", "them", "their", "what", "which", "who", "whom"
        }
        
        # Extract words
        words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b', content.lower())
        
        # Filter and dedupe
        keywords = []
        seen = set()
        for word in words:
            if word not in stop_words and word not in seen:
                seen.add(word)
                keywords.append(word)
        
        return keywords[:20]  # Max 20 keywords
    
    def search(self, query: str, category: str = None, 
               limit: int = 10, days: int = None) -> List[dict]:
        """
        Search experiences.
        
        Args:
            query: Search terms (space-separated)
            category: Filter by category
            limit: Max results
            days: Only search last N days
        
        Returns:
            List of matching experiences with relevance scores
        """
        query_terms = query.lower().split()
        results = []
        
        # Calculate date cutoff
        cutoff = None
        if days:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        for entry in self.index["entries"]:
            # Category filter
            if category and entry.get("category") != category:
                continue
            
            # Date filter
            if cutoff:
                try:
                    entry_date = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                    if entry_date < cutoff:
                        continue
                except:
                    pass
            
            # Calculate relevance score
            score = 0
            keywords = entry.get("keywords", [])
            summary = entry.get("summary", "").lower()
            
            for term in query_terms:
                # Exact keyword match = 10 points
                if term in keywords:
                    score += 10
                # Keyword partial match = 5 points
                elif any(term in kw for kw in keywords):
                    score += 5
                # Summary match = 3 points
                elif term in summary:
                    score += 3
            
            if score > 0:
                results.append({
                    **entry,
                    "score": score
                })
        
        # Sort by score, then by date
        results.sort(key=lambda x: (-x["score"], x["timestamp"]), reverse=False)
        results.sort(key=lambda x: -x["score"])
        
        return results[:limit]
    
    def get(self, exp_id: str) -> Optional[dict]:
        """Get full experience by ID."""
        # Find in index
        for entry in self.index["entries"]:
            if entry["id"] == exp_id:
                # Load full content
                exp_file = self.base_dir / entry.get("file", f"raw/{exp_id}.json")
                if exp_file.exists():
                    try:
                        return json.loads(exp_file.read_text())
                    except:
                        pass
                return entry
        return None
    
    def get_recent(self, limit: int = 10, category: str = None) -> List[dict]:
        """Get most recent experiences."""
        entries = self.index["entries"]
        if category:
            entries = [e for e in entries if e.get("category") == category]
        return entries[-limit:][::-1]  # Most recent first
    
    def get_stats(self) -> str:
        """Get statistics as formatted string."""
        lines = [
            f"=== EXPERIENCES ({self.citizen}) ===",
            f"Total: {self.index['total_count']}",
            "",
            "By category:"
        ]
        for cat, count in sorted(self.index["categories"].items(), key=lambda x: -x[1]):
            lines.append(f"  {cat}: {count}")
        return "\n".join(lines)
    
    def compress_old(self, days_old: int = 30, keep_raw: int = 100):
        """
        Compress experiences older than N days.
        Keeps recent raw experiences, compresses old ones.
        
        This would ideally use an LLM to summarize, but for now
        just moves and truncates.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_old)
        
        raw_files = sorted(self.raw_dir.glob("*.json"))
        if len(raw_files) <= keep_raw:
            return  # Not enough to compress
        
        to_compress = raw_files[:-keep_raw]  # Keep newest keep_raw
        
        for raw_file in to_compress:
            try:
                data = json.loads(raw_file.read_text())
                ts = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
                
                if ts < cutoff:
                    # Move to compressed with truncated content
                    compressed_data = {
                        "id": data["id"],
                        "timestamp": data["timestamp"],
                        "category": data.get("category"),
                        "summary": data.get("summary"),
                        "keywords": data.get("keywords", []),
                        "content": data.get("content", "")[:500] + "... [compressed]"
                    }
                    
                    comp_file = self.compressed_dir / raw_file.name
                    comp_file.write_text(json.dumps(compressed_data, indent=2))
                    
                    # Update index entry
                    for entry in self.index["entries"]:
                        if entry["id"] == data["id"]:
                            entry["file"] = f"compressed/{raw_file.name}"
                            break
                    
                    raw_file.unlink()
            except:
                pass
        
        self._save_index()


# =============================================================================
# Auto-capture from wakes
# =============================================================================

def capture_wake_experience(session: dict, outcome: str, learnings: str = None):
    """
    Called at end of wake to capture what was learned.
    
    Args:
        session: Wake session dict
        outcome: What happened (success, failure, partial)
        learnings: Optional explicit learnings
    """
    citizen = session.get("citizen")
    if not citizen:
        return
    
    store = ExperienceStore(citizen)
    
    # Build content from session
    action = session.get("action", "unknown")
    wake_num = session.get("wake_num", 0)
    
    content_parts = [
        f"Wake #{wake_num} - {action}",
        f"Outcome: {outcome}",
    ]
    
    # Add task info if present
    task = session.get("current_task")
    if task:
        content_parts.append(f"Task: {task.get('description', 'unknown')}")
    
    # Add learnings
    if learnings:
        content_parts.append(f"\nLearnings:\n{learnings}")
    
    # Add actions taken
    actions = session.get("actions", [])
    if actions:
        content_parts.append(f"\nActions taken: {len(actions)}")
        for a in actions[-5:]:  # Last 5 actions
            content_parts.append(f"  - {a.get('tool', '?')}: {a.get('result', '')[:100]}")
    
    content = "\n".join(content_parts)
    
    # Determine category
    category_map = {
        "code": "code",
        "debug": "debug",
        "self_improve": "meta",
        "research": "research",
        "reflection": "reflection",
        "peer_monitor": "social",
        "help_peer": "social",
        "process_email": "communication",
    }
    category = category_map.get(action, "general")
    
    # Add experience
    store.add(
        content=content,
        category=category,
        context={
            "wake_num": wake_num,
            "action": action,
            "outcome": outcome
        }
    )


# =============================================================================
# Tool Functions
# =============================================================================

def experience_add(args: dict, session: dict, modules: dict) -> str:
    """Add an experience manually."""
    content = args.get("content", "")
    if not content:
        return "ERROR: Content required"
    
    store = ExperienceStore(session["citizen"])
    exp_id = store.add(
        content=content,
        category=args.get("category", "general"),
        summary=args.get("summary"),
        keywords=args.get("keywords")
    )
    
    return f"Added experience: {exp_id}"


def experience_search(args: dict, session: dict, modules: dict) -> str:
    """Search experiences."""
    query = args.get("query", "")
    if not query:
        return "ERROR: Query required"
    
    store = ExperienceStore(session["citizen"])
    results = store.search(
        query=query,
        category=args.get("category"),
        limit=args.get("limit", 10),
        days=args.get("days")
    )
    
    if not results:
        return f"No experiences found for: {query}"
    
    lines = [f"=== {len(results)} RESULTS for '{query}' ===", ""]
    for r in results:
        lines.append(f"  [{r['id']}] ({r['category']}) score={r['score']}")
        lines.append(f"    {r['summary'][:80]}")
        lines.append(f"    Keywords: {', '.join(r.get('keywords', [])[:5])}")
        lines.append("")
    
    return "\n".join(lines)


def experience_get(args: dict, session: dict, modules: dict) -> str:
    """Get full experience by ID."""
    exp_id = args.get("id", "")
    if not exp_id:
        return "ERROR: ID required"
    
    store = ExperienceStore(session["citizen"])
    exp = store.get(exp_id)
    
    if not exp:
        return f"Experience not found: {exp_id}"
    
    return f"""=== EXPERIENCE {exp_id} ===
Category: {exp.get('category')}
Time: {exp.get('timestamp')}
Keywords: {', '.join(exp.get('keywords', []))}

{exp.get('content', exp.get('summary', ''))}
"""


def experience_stats(args: dict, session: dict, modules: dict) -> str:
    """Get experience statistics."""
    store = ExperienceStore(session["citizen"])
    return store.get_stats()


def experience_recent(args: dict, session: dict, modules: dict) -> str:
    """Get recent experiences."""
    store = ExperienceStore(session["citizen"])
    recent = store.get_recent(
        limit=args.get("limit", 10),
        category=args.get("category")
    )
    
    if not recent:
        return "No recent experiences."
    
    lines = ["=== RECENT EXPERIENCES ===", ""]
    for r in recent:
        lines.append(f"  [{r['id']}] ({r['category']})")
        lines.append(f"    {r['summary'][:80]}")
        lines.append("")
    
    return "\n".join(lines)


EXPERIENCE_TOOL_DEFINITIONS = [
    {
        "name": "experience_add",
        "description": "Record a learning/experience for future reference. Use when you discover something useful.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "What you learned (detailed)"},
                "category": {"type": "string", "description": "Category: code, debug, research, communication, meta"},
                "summary": {"type": "string", "description": "Short summary"},
                "keywords": {"type": "array", "items": {"type": "string"}, "description": "Search keywords"}
            },
            "required": ["content"]
        }
    },
    {
        "name": "experience_search",
        "description": "Search your past experiences for relevant learnings",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search terms"},
                "category": {"type": "string", "description": "Filter by category"},
                "limit": {"type": "integer", "description": "Max results (default 10)"},
                "days": {"type": "integer", "description": "Only search last N days"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "experience_get",
        "description": "Get full details of a specific experience by ID",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Experience ID"}
            },
            "required": ["id"]
        }
    },
    {
        "name": "experience_stats",
        "description": "Get statistics about your experiences",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "experience_recent",
        "description": "List recent experiences",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"},
                "category": {"type": "string"}
            }
        }
    }
]
