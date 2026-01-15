"""
Library Auto-Search - Search existing modules by keywords.

NO HARDCODED DOMAINS. NO PRE-SEEDED ANSWERS.

Flow:
1. Task comes in
2. Extract keywords from task
3. Search Library modules for keyword matches
4. If found → inject into context
5. If NOT found → AI should research (web_search) and create module after

The Library starts EMPTY. It grows from AI learning.
"""

import json
import re
from pathlib import Path
from typing import Optional

LIBRARY_ROOT = Path("/home/shared/library")
LIBRARY_MODULES = LIBRARY_ROOT / "modules"


def extract_keywords(text: str) -> list:
    """Extract meaningful keywords from text for search."""
    # Remove common words
    stop_words = {
        "a", "an", "the", "is", "are", "was", "were", "be", "been",
        "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "must", "can", "to", "of",
        "in", "for", "on", "with", "at", "by", "from", "as", "into",
        "through", "during", "before", "after", "above", "below",
        "between", "under", "again", "further", "then", "once",
        "here", "there", "when", "where", "why", "how", "all", "each",
        "few", "more", "most", "other", "some", "such", "no", "nor",
        "not", "only", "own", "same", "so", "than", "too", "very",
        "just", "and", "but", "if", "or", "because", "until", "while",
        "about", "against", "between", "into", "through", "during",
        "write", "create", "make", "build", "implement", "develop",
        "need", "want", "please", "help", "me", "my", "i", "you",
        "program", "code", "file", "that", "this", "it", "which"
    }
    
    # Tokenize and filter
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    keywords = [w for w in words if w not in stop_words]
    
    # Also extract multi-word phrases that might be important
    # e.g., "binary search", "linked list"
    phrases = re.findall(r'\b[a-zA-Z]+\s+[a-zA-Z]+\b', text.lower())
    
    return list(set(keywords + [p.replace(" ", "_") for p in phrases]))


def search_library(keywords: list, max_results: int = 3) -> list:
    """
    Search Library modules by keywords.
    Returns modules that match any keyword.
    """
    if not LIBRARY_MODULES.exists():
        return []
    
    results = []
    
    for module_file in LIBRARY_MODULES.glob("*.json"):
        try:
            module = json.loads(module_file.read_text())
            module_text = json.dumps(module).lower()
            
            # Count keyword matches
            matches = sum(1 for kw in keywords if kw in module_text)
            
            if matches > 0:
                results.append({
                    "name": module.get("name", module_file.stem),
                    "matches": matches,
                    "description": module.get("description", "")[:100],
                    "content": module
                })
        except:
            continue
    
    # Sort by match count
    results.sort(key=lambda x: -x["matches"])
    
    return results[:max_results]


def search_and_inject(task: str, max_modules: int = 2) -> dict:
    """
    Search Library for relevant modules and prepare context injection.
    
    Returns:
        {
            "keywords": [...],
            "modules_found": [...],
            "context_injection": "..." or None,
            "should_research": True/False
        }
    """
    result = {
        "keywords": [],
        "modules_found": [],
        "context_injection": None,
        "should_research": False
    }
    
    # Extract keywords
    keywords = extract_keywords(task)
    result["keywords"] = keywords[:10]  # Limit
    
    if not keywords:
        return result
    
    # Search Library
    found = search_library(keywords, max_results=max_modules)
    
    if found:
        result["modules_found"] = [m["name"] for m in found]
        
        # Build injection
        parts = ["\n\n=== RELEVANT KNOWLEDGE (from Library) ==="]
        for m in found:
            parts.append(format_module(m["content"]))
        
        result["context_injection"] = "\n---\n".join(parts)
    else:
        # No modules found - AI should consider researching
        result["should_research"] = True
    
    return result


def format_module(module: dict) -> str:
    """Format module for context injection."""
    parts = [f"### {module.get('name', 'unknown')}"]
    
    if module.get("description"):
        parts.append(module["description"])
    
    content = module.get("content", {})
    if isinstance(content, dict):
        # Show key sections
        for key, val in list(content.items())[:5]:
            if isinstance(val, str) and len(val) < 500:
                parts.append(f"**{key}:** {val}")
            elif isinstance(val, list):
                items = ", ".join(str(v)[:50] for v in val[:5])
                parts.append(f"**{key}:** {items}")
    elif isinstance(content, str):
        parts.append(content[:1000])
    
    return "\n".join(parts)


def create_module_from_learnings(
    name: str,
    domain: str,
    description: str,
    content: dict,
    author: str
) -> str:
    """
    Create a new Library module from AI learnings.
    
    This is called AFTER the AI has researched and learned something.
    The module goes into pending/ for review.
    """
    LIBRARY_MODULES.mkdir(parents=True, exist_ok=True)
    pending_dir = LIBRARY_ROOT / "pending"
    pending_dir.mkdir(exist_ok=True)
    
    # Generate PR ID
    existing = list(pending_dir.glob("pr_*.json"))
    pr_num = len(existing) + 1
    pr_id = f"pr_{pr_num:03d}"
    
    module_data = {
        "name": name,
        "domain": domain,
        "description": description,
        "content": content,
        "version": 1,
        "created_by": author,
        "created_from": "learning"
    }
    
    pr = {
        "id": pr_id,
        "type": "new",
        "module_name": name,
        "author": author,
        "module_data": module_data,
        "reviews": {},
        "status": "pending"
    }
    
    pr_file = pending_dir / f"{pr_id}.json"
    pr_file.write_text(json.dumps(pr, indent=2))
    
    return f"MODULE_PR_CREATED: {pr_id} - {name}\nNeeds review before merge."


def get_research_prompt(task: str, keywords: list) -> str:
    """
    Generate a prompt suggesting the AI research this topic.
    Called when no Library modules match.
    """
    return f"""
NO LIBRARY MODULES FOUND for keywords: {keywords[:5]}

This means no one has captured knowledge about this topic yet.

SUGGESTED APPROACH:
1. Use web_search to research the topic
2. Learn what you need to complete the task
3. After completing the task, capture your learnings:
   - Call library_create with what you learned
   - This helps future tasks on similar topics

Keywords to research: {', '.join(keywords[:5])}
"""
