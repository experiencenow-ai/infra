"""
Tool Selector - Pattern matching, no AI needed.

Maps keywords → tool categories. Instant, free, deterministic.
"""

import re

# Core tools - always included
CORE_TOOLS = {"task_complete", "task_stuck", "task_start", "task_progress", "shell_command"}

# Tool categories with trigger patterns
TOOL_PATTERNS = {
    # Email
    "email": {
        "patterns": ["email", "mail", "inbox", "message", "send", "compose"],
        "tools": {"check_email", "send_email"}
    },
    # GitHub
    "github": {
        "patterns": ["github", "git", "commit", "pr", "pull request", "issue", "merge", "branch", "repo"],
        "tools": {"github_commit", "github_pr_create", "github_pr_merge", "github_issue_create", "github_status"}
    },
    # Memory
    "memory": {
        "patterns": ["memory", "remember", "recall", "forgot", "history", "past", "earlier", "before"],
        "tools": {"memory_store", "memory_recall", "memory_recent", "mark_significant", "search_history"}
    },
    # Library
    "library": {
        "patterns": ["library", "knowledge", "module", "learn", "document", "expertise"],
        "tools": {"library_search", "library_load", "library_propose", "library_list"}
    },
    # Web
    "web": {
        "patterns": ["search", "web", "google", "look up", "find info", "research"],
        "tools": {"web_search"}
    },
    # Files
    "files": {
        "patterns": ["file", "read", "write", "save", "create", "edit", "cat", "content"],
        "tools": {"read_file", "write_file"}
    },
    # Task management  
    "tasks": {
        "patterns": ["task", "goal", "todo", "queue", "pending", "active", "assign"],
        "tools": {"task_start", "task_complete", "task_stuck", "task_progress"}
    },
    # Code
    "code": {
        "patterns": ["code", "python", "script", "run", "execute", "compile", "test", "debug", "fix", "bug"],
        "tools": {"shell_command", "read_file", "write_file"}
    },
    # Communication
    "comm": {
        "patterns": ["citizen", "opus", "aria", "mira", "peer", "help", "request", "notify"],
        "tools": {"request_peer_help", "check_peer_requests", "send_email"}
    },
    # Experience/reflection
    "reflect": {
        "patterns": ["experience", "reflect", "insight", "learn", "significant", "important"],
        "tools": {"mark_significant", "create_experience", "memory_store"}
    }
}


def select_tools(task_description: str, all_tools: list, max_tools: int = 15) -> list:
    """
    Select relevant tools using pattern matching.
    
    Zero API calls. Instant. Deterministic.
    """
    if len(all_tools) <= max_tools:
        return all_tools
    
    # Lowercase for matching
    text = task_description.lower()
    
    # Find matching categories
    matched_tools = set(CORE_TOOLS)
    matched_categories = []
    
    for category, data in TOOL_PATTERNS.items():
        for pattern in data["patterns"]:
            if pattern in text:
                matched_tools.update(data["tools"])
                matched_categories.append(category)
                break
    
    # If nothing matched, include common defaults
    if len(matched_tools) == len(CORE_TOOLS):
        matched_tools.update({"check_email", "memory_recent", "read_file", "write_file"})
    
    # Build result from all_tools that match names
    tool_names = {t.get("name") for t in all_tools}
    matched_tools = matched_tools & tool_names  # Only include tools that exist
    
    result = [t for t in all_tools if t.get("name") in matched_tools]
    
    # If still under budget, add more common tools
    if len(result) < max_tools:
        common = ["web_search", "memory_recall", "library_search", "check_email"]
        for name in common:
            if len(result) >= max_tools:
                break
            if name not in matched_tools and name in tool_names:
                for t in all_tools:
                    if t.get("name") == name:
                        result.append(t)
                        matched_tools.add(name)
                        break
    
    cats = ",".join(matched_categories[:3]) if matched_categories else "default"
    print(f"  [TOOLS] Pattern matched {len(result)}/{len(all_tools)} ({cats})")
    
    return result


def select_tools_for_wake(wake_type: str, focus: str, all_tools: list) -> list:
    """Select tools for a wake type."""
    # Combine wake type and focus for matching
    task_desc = f"{wake_type} {focus or 'general'}"
    return select_tools(task_desc, all_tools)
