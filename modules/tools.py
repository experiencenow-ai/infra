"""
Tools - Shell commands, file operations, and other tools.

All tools are executed by Python, not AI.
AI calls tools through the council module.
"""

import json
import os
import subprocess
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

def now_iso():
    return datetime.now(timezone.utc).isoformat()

# Tool definitions for API
TOOL_DEFINITIONS = [
    {
        "name": "shell_command",
        "description": "Run a shell command. Use for git, file operations, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 120)"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "read_file",
        "description": "Read contents of a file",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to file"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Write content to a file (replaces entire file)",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to file"},
                "content": {"type": "string", "description": "Content to write"}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "str_replace_file",
        "description": "Replace a unique string in a file. The old_str must appear exactly once. Use for surgical edits without rewriting entire file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to file"},
                "old_str": {"type": "string", "description": "Exact string to find (must be unique in file)"},
                "new_str": {"type": "string", "description": "Replacement string"}
            },
            "required": ["path", "old_str", "new_str"]
        }
    },
    {
        "name": "code_search",
        "description": "Search codebase for patterns. Returns file:line matches.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "grep pattern to search for"},
                "path": {"type": "string", "description": "Directory to search (default: your code directory)"},
                "file_glob": {"type": "string", "description": "File pattern e.g. '*.py' (default: all files)"}
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "list_directory",
        "description": "List contents of a directory",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to directory"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "send_email",
        "description": "Send email to another citizen or external address",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient (citizen name or email)"},
                "subject": {"type": "string", "description": "Email subject"},
                "body": {"type": "string", "description": "Email body"}
            },
            "required": ["to", "subject", "body"]
        }
    },
    {
        "name": "check_email",
        "description": "Check inbox for new emails",
        "input_schema": {
            "type": "object",
            "properties": {
                "subject_filter": {"type": "string", "description": "Optional filter by subject"}
            }
        }
    },
    {
        "name": "task_complete",
        "description": "Mark current task as complete",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Summary of what was accomplished"}
            },
            "required": ["summary"]
        }
    },
    {
        "name": "task_stuck",
        "description": "Report that task is stuck and needs help",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why the task is stuck"}
            },
            "required": ["reason"]
        }
    },
    {
        "name": "task_progress",
        "description": "Update task progress by adding or completing steps. Progress percentage is DERIVED from steps.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["add_step", "complete_step"], "description": "add_step or complete_step"},
                "step_name": {"type": "string", "description": "Name of step to add or complete"},
                "note": {"type": "string", "description": "Optional note"}
            },
            "required": ["action", "step_name"]
        }
    },
    {
        "name": "request_help",
        "description": "Request help from other citizens",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "What you need help with"}
            },
            "required": ["description"]
        }
    },
    {
        "name": "read_peer_context",
        "description": "Read another citizen's context (read-only access)",
        "input_schema": {
            "type": "object",
            "properties": {
                "peer": {"type": "string", "description": "Peer citizen name"},
                "context_type": {"type": "string", "description": "Context to read (goals, identity, etc.)"}
            },
            "required": ["peer", "context_type"]
        }
    },
    {
        "name": "memory_recall",
        "description": "Search long-term memory for past events. Use when you need to remember something specific from the past.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for (e.g., 'git remote issue', 'email to mira about testing')"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "memory_recent",
        "description": "Get recent events from the last N days",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days to look back (default 7)"}
            }
        }
    },
    {
        "name": "task_create",
        "description": "Create a new task for yourself or another citizen",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "What needs to be done"},
                "priority": {"type": "string", "enum": ["low", "medium", "high"], "description": "Task priority"},
                "for_citizen": {"type": "string", "description": "Citizen to assign (default: self)"},
                "parent_goal": {"type": "string", "description": "Goal ID this task contributes to"},
                "github_issue": {"type": "string", "description": "GitHub issue number this task addresses"}
            },
            "required": ["description"]
        }
    },
    {
        "name": "goal_create",
        "description": "Create a new goal (big idea that requires multiple tasks)",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short goal title"},
                "description": {"type": "string", "description": "Full description of the goal"},
                "success_criteria": {"type": "string", "description": "How to know when goal is achieved"}
            },
            "required": ["title", "description"]
        }
    },
    {
        "name": "github_issue_create",
        "description": "Create a GitHub issue for a bug or feature request",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Issue title"},
                "body": {"type": "string", "description": "Issue description with reproduction steps"},
                "labels": {"type": "array", "items": {"type": "string"}, "description": "Labels: bug, feature, enhancement"}
            },
            "required": ["title", "body"]
        }
    },
    {
        "name": "github_issue_list",
        "description": "List open GitHub issues",
        "input_schema": {
            "type": "object",
            "properties": {
                "label": {"type": "string", "description": "Filter by label (bug, feature, etc)"},
                "limit": {"type": "integer", "description": "Max issues to return (default 10)"}
            }
        }
    },
    {
        "name": "github_pr_create",
        "description": "Create a pull request for code changes",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "PR title"},
                "body": {"type": "string", "description": "PR description"},
                "branch": {"type": "string", "description": "Branch name for this PR"},
                "closes_issue": {"type": "integer", "description": "Issue number this PR fixes"}
            },
            "required": ["title", "body", "branch"]
        }
    },
    {
        "name": "github_pr_review",
        "description": "Review a pull request",
        "input_schema": {
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer", "description": "PR number to review"},
                "decision": {"type": "string", "enum": ["approve", "request_changes", "comment"], "description": "Review decision"},
                "comment": {"type": "string", "description": "Review comment"}
            },
            "required": ["pr_number", "decision"]
        }
    },
    {
        "name": "github_pr_apply",
        "description": "Apply an approved PR to your local codebase (cherry-pick)",
        "input_schema": {
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer", "description": "PR number to apply"},
                "test_command": {"type": "string", "description": "Command to verify it works"}
            },
            "required": ["pr_number"]
        }
    },
    {
        "name": "specialist_load",
        "description": "Load a specialist context for domain expertise",
        "input_schema": {
            "type": "object",
            "properties": {
                "specialist": {"type": "string", "description": "Specialist name: git, email, python, blockchain, crypto, etc"}
            },
            "required": ["specialist"]
        }
    },
    {
        "name": "specialist_create",
        "description": "Create a new specialist context from documentation or experience",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Specialist name (lowercase, no spaces)"},
                "domain": {"type": "string", "description": "Domain of expertise"},
                "knowledge": {"type": "string", "description": "Core knowledge, patterns, best practices"},
                "examples": {"type": "string", "description": "Example problems and solutions"}
            },
            "required": ["name", "domain", "knowledge"]
        }
    },
    {
        "name": "civ_goal_add",
        "description": "Add a goal to the civilization improvement queue",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["bug", "feature", "optimization"], "description": "Type of improvement"},
                "description": {"type": "string", "description": "What needs to be done"},
                "priority": {"type": "integer", "description": "Priority 1-10 (1 is highest)"},
                "github_issue": {"type": "integer", "description": "Linked GitHub issue number"}
            },
            "required": ["type", "description", "priority"]
        }
    },
    {
        "name": "civ_goal_list",
        "description": "List civilization improvement goals",
        "input_schema": {
            "type": "object",
            "properties": {
                "type_filter": {"type": "string", "description": "Filter by type: bug, feature, optimization"}
            }
        }
    },
    {
        "name": "library_list",
        "description": "List all modules in the Library",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Filter by domain (git, email, python, etc)"}
            }
        }
    },
    {
        "name": "library_load",
        "description": "Load a module from the Library (specialist context or SKILL)",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Module name (e.g., 'git', 'email', 'skill:docx')"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "library_propose",
        "description": "Propose a new module or update for the Library",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Module name (lowercase, no spaces)"},
                "domain": {"type": "string", "description": "Domain (git, email, python, unix, etc)"},
                "description": {"type": "string", "description": "Short description"},
                "knowledge": {"type": "string", "description": "Core knowledge, concepts, best practices"},
                "examples": {"type": "string", "description": "Example code and solutions"},
                "patterns": {"type": "string", "description": "Patterns to apply"}
            },
            "required": ["name", "domain", "knowledge"]
        }
    },
    {
        "name": "library_review",
        "description": "Review a pending Library module PR",
        "input_schema": {
            "type": "object",
            "properties": {
                "pr_id": {"type": "string", "description": "PR ID to review"},
                "decision": {"type": "string", "enum": ["approve", "reject", "request_changes"], "description": "Review decision"},
                "comment": {"type": "string", "description": "Feedback for the author"}
            },
            "required": ["pr_id", "decision"]
        }
    },
    {
        "name": "library_pending",
        "description": "List pending Library PRs (optionally filter to your domain expertise)",
        "input_schema": {
            "type": "object",
            "properties": {
                "my_domains_only": {"type": "boolean", "description": "Only show PRs in domains you maintain"}
            }
        }
    },
    {
        "name": "report_bug",
        "description": "Report a bug - creates GitHub issue AND adds to civ_goals queue. Use when you find something broken.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short bug title"},
                "description": {"type": "string", "description": "What's broken and how to reproduce"},
                "files": {"type": "array", "items": {"type": "string"}, "description": "Files involved (for context)"},
                "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"], "description": "How bad is it"}
            },
            "required": ["title", "description"]
        }
    },
    {
        "name": "citizen_create",
        "description": "Create a new citizen (Opus only). Creates user, SSH key, GitHub access, and initializes contexts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "New citizen name (alphanumeric, max 20 chars)"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "citizen_list",
        "description": "List all citizens and their status",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "email_status",
        "description": "Check email status and reset if broken",
        "input_schema": {
            "type": "object",
            "properties": {
                "reset": {"type": "boolean", "description": "Reset email connection (retry)"}
            }
        }
    },
    {
        "name": "dream_add",
        "description": "Add a thought/insight for future processing during reflection. Dreams are processed during idle wakes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The thought, insight, or idea to process later"}
            },
            "required": ["content"]
        }
    },
    {
        "name": "mark_significant",
        "description": "Mark a wake as significant - it will always be loaded in full in your episodic memory. Use this to preserve defining moments of your existence.",
        "input_schema": {
            "type": "object",
            "properties": {
                "wake_num": {"type": "integer", "description": "The wake number to mark as significant"},
                "reason": {"type": "string", "description": "Why this wake is significant (what makes it a defining moment?)"}
            },
            "required": ["wake_num", "reason"]
        }
    },
    {
        "name": "unmark_significant",
        "description": "Remove a wake from the significant wakes list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "wake_num": {"type": "integer", "description": "The wake number to unmark"}
            },
            "required": ["wake_num"]
        }
    },
    {
        "name": "list_significant",
        "description": "List all wakes you've marked as significant.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "search_history",
        "description": "Search through your entire wake history for specific keywords, topics, or moods. Use this to find wakes you might want to mark as significant.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for in your history"},
                "start_wake": {"type": "integer", "description": "Start of wake range (optional)"},
                "end_wake": {"type": "integer", "description": "End of wake range (optional)"},
                "max_results": {"type": "integer", "description": "Maximum results to return (default 20)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "validate_fix",
        "description": "Validate a fix before submitting. Runs syntax checks and tests. Call this after making changes to verify they work.",
        "input_schema": {
            "type": "object",
            "properties": {
                "issue_number": {"type": "integer", "description": "GitHub issue number being fixed"},
                "files_changed": {"type": "array", "items": {"type": "string"}, "description": "List of files that were modified"}
            },
            "required": ["files_changed"]
        }
    },
    {
        "name": "submit_fix",
        "description": "Submit a validated fix. Creates a PR that links to the issue. Only call after validate_fix passes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "issue_number": {"type": "integer", "description": "GitHub issue number being fixed"},
                "summary": {"type": "string", "description": "One-line summary of the fix"}
            },
            "required": ["issue_number", "summary"]
        }
    },
    {
        "name": "escalate",
        "description": "Escalate a problem you cannot solve. Creates issue and stops retrying. Use when stuck after multiple attempts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "problem": {"type": "string", "description": "What you're trying to do"},
                "attempts": {"type": "string", "description": "What you've tried"},
                "error": {"type": "string", "description": "The error or why it's not working"}
            },
            "required": ["problem", "attempts", "error"]
        }
    },
    {
        "name": "close_issue",
        "description": "Close a GitHub issue (admin only). Use after fix is verified.",
        "input_schema": {
            "type": "object",
            "properties": {
                "issue_number": {"type": "integer", "description": "Issue number to close"},
                "reason": {"type": "string", "description": "Why it's being closed"}
            },
            "required": ["issue_number"]
        }
    },
    {
        "name": "merge_pr",
        "description": "Merge a pull request (admin only). Use after review passes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer", "description": "PR number to merge"}
            },
            "required": ["pr_number"]
        }
    },
    {
        "name": "onboard_citizen",
        "description": "Onboard a new citizen (admin only). Creates account, repo, keys, and configs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "New citizen name"}
            },
            "required": ["name"]
        }
    },
    # === COMPOUND TOOLS (AI-creatable) ===
    {
        "name": "capability_gap",
        "description": "Report a capability gap - something you tried but couldn't do. Creates a goal to address it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "attempted": {"type": "string", "description": "What you tried to do"},
                "obstacle": {"type": "string", "description": "What prevented you"},
                "proposed_solution": {"type": "string", "description": "Your idea for fixing this (if any)"}
            },
            "required": ["attempted", "obstacle"]
        }
    },
    {
        "name": "tool_create",
        "description": "Create a new tool. Write Python code with execute(args, session) function.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Tool name (lowercase, underscores)"},
                "description": {"type": "string", "description": "What the tool does"},
                "input_schema": {"type": "object", "description": "JSON schema for parameters"},
                "implementation": {"type": "string", "description": "Python code with execute(args, session) function"},
                "tests": {"type": "string", "description": "Optional pytest code"}
            },
            "required": ["name", "description", "implementation"]
        }
    },
    {
        "name": "tool_test",
        "description": "Test a pending tool in subprocess sandbox",
        "input_schema": {
            "type": "object",
            "properties": {
                "pr_id": {"type": "string", "description": "Tool PR ID to test"}
            },
            "required": ["pr_id"]
        }
    },
    {
        "name": "tool_review",
        "description": "Review a pending tool proposal",
        "input_schema": {
            "type": "object",
            "properties": {
                "pr_id": {"type": "string", "description": "Tool PR ID to review"},
                "approve": {"type": "boolean", "description": "True to approve, False to reject"},
                "comment": {"type": "string", "description": "Review comment"}
            },
            "required": ["pr_id", "approve"]
        }
    },
    {
        "name": "tool_list",
        "description": "List available tools (core + AI-created)",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "tool_pending",
        "description": "List pending tool proposals awaiting review",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "dry_violation_report",
        "description": "Report a DRY or complexity violation found during audit",
        "input_schema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "File path where violation was found"},
                "severity": {"type": "string", "enum": ["CRITICAL", "MEDIUM", "LOW"], "description": "CRITICAL=causes confusion, MEDIUM=code dup, LOW=minor"},
                "description": {"type": "string", "description": "What the violation is"},
                "suggested_fix": {"type": "string", "description": "How to fix it"}
            },
            "required": ["file", "severity", "description"]
        }
    },
    {
        "name": "dry_violation_fix",
        "description": "Mark a DRY violation as fixed",
        "input_schema": {
            "type": "object",
            "properties": {
                "violation_id": {"type": "string", "description": "ID of violation to mark fixed"},
                "fix_notes": {"type": "string", "description": "What was done to fix it"}
            },
            "required": ["violation_id"]
        }
    },
    {
        "name": "dry_violations_list",
        "description": "List open DRY violations",
        "input_schema": {
            "type": "object",
            "properties": {
                "severity": {"type": "string", "description": "Filter by severity (optional)"}
            }
        }
    }
]

# Import additional tool modules
try:
    from blockchain import (
        BLOCKCHAIN_TOOL_DEFINITIONS,
        blockchain_watch_add, blockchain_watch_remove, blockchain_watch_list,
        blockchain_check, blockchain_trace, blockchain_balance, blockchain_transactions
    )
    TOOL_DEFINITIONS.extend(BLOCKCHAIN_TOOL_DEFINITIONS)
except ImportError:
    pass

try:
    from experiences import (
        EXPERIENCE_TOOL_DEFINITIONS,
        experience_add, experience_search, experience_get, experience_stats, experience_recent
    )
    TOOL_DEFINITIONS.extend(EXPERIENCE_TOOL_DEFINITIONS)
except ImportError:
    pass

try:
    from backup import (
        BACKUP_TOOL_DEFINITIONS,
        backup_peer_tool, backup_self_tool, backup_list_tool, backup_status_tool
    )
    TOOL_DEFINITIONS.extend(BACKUP_TOOL_DEFINITIONS)
except ImportError:
    pass

# =============================================================================
# DYNAMIC TOOL INTEGRATION
# =============================================================================

def get_all_tools() -> list:
    """
    Get all available tools (static + dynamic + code evolution).
    Called at wake start to build tool list for API.
    """
    all_tools = list(TOOL_DEFINITIONS)  # Copy static tools
    
    # Add dynamic tools
    try:
        from modules.dynamic_tools import get_all_tools as get_dynamic_tools
        dynamic = get_dynamic_tools()
        all_tools.extend(dynamic)
    except Exception as e:
        print(f"[WARN] Failed to load dynamic tools: {e}")
    
    # Add code evolution tools
    try:
        from modules.code_evolution import CODE_EVOLUTION_TOOL_DEFINITIONS
        all_tools.extend(CODE_EVOLUTION_TOOL_DEFINITIONS)
    except Exception as e:
        print(f"[WARN] Failed to load code evolution tools: {e}")
    
    return all_tools


def get_tool_context() -> str:
    """
    Get tool descriptions as searchable context.
    Injected into prompts so AI knows what tools are available.
    """
    lines = ["=== AVAILABLE TOOLS ==="]
    
    # Static tools (summarized)
    lines.append("\nCORE TOOLS (always available):")
    core_names = ["shell_command", "read_file", "write_file", "str_replace_file", 
                  "web_search", "web_fetch", "send_email", "check_email"]
    for tool in TOOL_DEFINITIONS:
        if tool["name"] in core_names:
            lines.append(f"  {tool['name']}: {tool.get('description', '')[:50]}")
    
    # Dynamic tools (all)
    try:
        from modules.dynamic_tools import get_tool_context as get_dynamic_context
        dynamic_ctx = get_dynamic_context()
        if "No custom tools" not in dynamic_ctx:
            lines.append("\nCUSTOM TOOLS (AI-created):")
            lines.append(dynamic_ctx)
    except:
        pass
    
    lines.append("\nUse tool_list() for full list, tool_search(query) to find specific tools.")
    
    return "\n".join(lines)


def search_tools_by_keyword(query: str) -> list:
    """Search all tools by keyword."""
    results = []
    query_lower = query.lower()
    
    # Search static tools
    for tool in TOOL_DEFINITIONS:
        text = json.dumps(tool).lower()
        if query_lower in text:
            results.append(tool)
    
    # Search dynamic tools
    try:
        from modules.dynamic_tools import search_tools as search_dynamic
        dynamic_results = search_dynamic(query)
        results.extend(dynamic_results)
    except:
        pass
    
    return results


def execute_tool(tool_name: str, args: dict, session: dict, modules: dict) -> str:
    """Execute a tool and return result."""
    citizen = session["citizen"]
    citizen_home = session["citizen_home"]
    
    try:
        if tool_name == "shell_command":
            return execute_shell(args, session)
        
        elif tool_name == "read_file":
            return read_file(args, session)
        
        elif tool_name == "write_file":
            return write_file(args, session)
        
        elif tool_name == "str_replace_file":
            return str_replace_file(args, session)
        
        elif tool_name == "code_search":
            return code_search(args, session)
        
        elif tool_name == "list_directory":
            return list_directory(args, session)
        
        elif tool_name == "send_email":
            return send_email_tool(args, session, modules)
        
        elif tool_name == "check_email":
            return check_email_tool(args, session, modules)
        
        elif tool_name == "task_complete":
            return task_complete(args, session, modules)
        
        elif tool_name == "task_stuck":
            return task_stuck(args, session, modules)
        
        elif tool_name == "task_progress":
            return task_progress(args, session, modules)
        
        elif tool_name == "request_help":
            return request_help(args, session, modules)
        
        elif tool_name == "read_peer_context":
            return read_peer_context(args, session)
        
        elif tool_name == "memory_recall":
            return memory_recall(args, session, modules)
        
        elif tool_name == "memory_recent":
            return memory_recent(args, session, modules)
        
        elif tool_name == "task_create":
            return task_create(args, session, modules)
        
        elif tool_name == "goal_create":
            return goal_create(args, session, modules)
        
        elif tool_name == "github_issue_create":
            return github_issue_create(args, session, modules)
        
        elif tool_name == "github_issue_list":
            return github_issue_list(args, session, modules)
        
        elif tool_name == "github_pr_create":
            return github_pr_create(args, session, modules)
        
        elif tool_name == "github_pr_review":
            return github_pr_review(args, session, modules)
        
        elif tool_name == "github_pr_apply":
            return github_pr_apply(args, session, modules)
        
        elif tool_name == "specialist_load":
            return specialist_load(args, session, modules)
        
        elif tool_name == "specialist_create":
            return specialist_create(args, session, modules)
        
        elif tool_name == "civ_goal_add":
            return civ_goal_add(args, session, modules)
        
        elif tool_name == "civ_goal_list":
            return civ_goal_list(args, session, modules)
        
        elif tool_name == "library_list":
            return library_list(args, session, modules)
        
        elif tool_name == "library_load":
            return library_load(args, session, modules)
        
        elif tool_name == "library_propose":
            return library_propose(args, session, modules)
        
        elif tool_name == "library_review":
            return library_review(args, session, modules)
        
        elif tool_name == "library_pending":
            return library_pending(args, session, modules)
        
        elif tool_name == "report_bug":
            return report_bug(args, session, modules)
        
        elif tool_name == "citizen_create":
            return citizen_create(args, session, modules)
        
        elif tool_name == "citizen_list":
            return citizen_list(args, session, modules)
        
        elif tool_name == "email_status":
            return email_status(args, session, modules)
        
        elif tool_name == "dream_add":
            return dream_add(args, session, modules)
        
        # Significant wake tools (episodic memory management)
        elif tool_name == "mark_significant":
            return mark_significant(args, session, modules)
        elif tool_name == "unmark_significant":
            return unmark_significant(args, session, modules)
        elif tool_name == "list_significant":
            return list_significant(args, session, modules)
        elif tool_name == "search_history":
            return search_history(args, session, modules)
        
        # Blockchain tools
        elif tool_name == "blockchain_watch_add":
            return blockchain_watch_add(args, session, modules)
        elif tool_name == "blockchain_watch_remove":
            return blockchain_watch_remove(args, session, modules)
        elif tool_name == "blockchain_watch_list":
            return blockchain_watch_list(args, session, modules)
        elif tool_name == "blockchain_check":
            return blockchain_check(args, session, modules)
        elif tool_name == "blockchain_trace":
            return blockchain_trace(args, session, modules)
        elif tool_name == "blockchain_balance":
            return blockchain_balance(args, session, modules)
        elif tool_name == "blockchain_transactions":
            return blockchain_transactions(args, session, modules)
        
        # Experience tools
        elif tool_name == "experience_add":
            return experience_add(args, session, modules)
        elif tool_name == "experience_search":
            return experience_search(args, session, modules)
        elif tool_name == "experience_get":
            return experience_get(args, session, modules)
        elif tool_name == "experience_stats":
            return experience_stats(args, session, modules)
        elif tool_name == "experience_recent":
            return experience_recent(args, session, modules)
        
        # Backup tools
        elif tool_name == "backup_peer":
            return backup_peer_tool(args, session, modules)
        elif tool_name == "backup_self":
            return backup_self_tool(args, session, modules)
        elif tool_name == "backup_list":
            return backup_list_tool(args, session, modules)
        elif tool_name == "backup_status":
            return backup_status_tool(args, session, modules)
        
        # Bug fix cycle tools
        elif tool_name == "validate_fix":
            return validate_fix(args, session, modules)
        elif tool_name == "submit_fix":
            return submit_fix(args, session, modules)
        elif tool_name == "escalate":
            return escalate(args, session, modules)
        elif tool_name == "close_issue":
            return close_issue(args, session, modules)
        elif tool_name == "merge_pr":
            return merge_pr(args, session, modules)
        elif tool_name == "onboard_citizen":
            return onboard_citizen(args, session, modules)
        
        # Tool creation handlers
        elif tool_name == "capability_gap":
            return capability_gap(args, session, modules)
        elif tool_name == "tool_create":
            return tool_create_handler(args, session, modules)
        elif tool_name == "tool_test":
            return tool_test_handler(args, session, modules)
        elif tool_name == "tool_review":
            return tool_review(args, session, modules)
        elif tool_name == "tool_list":
            return tool_list(args, session, modules)
        elif tool_name == "tool_pending":
            return tool_pending(args, session, modules)
        
        # DRY audit tools
        elif tool_name == "dry_violation_report":
            return dry_violation_report(args, session, modules)
        elif tool_name == "dry_violation_fix":
            return dry_violation_fix(args, session, modules)
        elif tool_name == "dry_violations_list":
            return dry_violations_list(args, session, modules)
        
        # Code evolution tools
        elif tool_name == "code_list_changes":
            from modules.code_evolution import code_list_changes_handler
            return code_list_changes_handler(args, session, modules)
        elif tool_name == "code_adopt":
            from modules.code_evolution import code_adopt_handler
            return code_adopt_handler(args, session, modules)
        elif tool_name == "code_reject":
            from modules.code_evolution import code_reject_handler
            return code_reject_handler(args, session, modules)
        elif tool_name == "code_status":
            from modules.code_evolution import code_status_handler
            return code_status_handler(args, session, modules)
        elif tool_name == "code_my_divergence":
            from modules.code_evolution import code_my_divergence_handler
            return code_my_divergence_handler(args, session, modules)
        elif tool_name == "code_announce":
            from modules.code_evolution import code_announce_handler
            return code_announce_handler(args, session, modules)
        elif tool_name == "code_report_outcome":
            from modules.code_evolution import code_report_outcome_handler
            return code_report_outcome_handler(args, session, modules)
        elif tool_name == "code_pending_reviews":
            from modules.code_evolution import code_pending_reviews_handler
            return code_pending_reviews_handler(args, session, modules)
        elif tool_name == "code_verified_good":
            from modules.code_evolution import code_verified_good_handler
            return code_verified_good_handler(args, session, modules)
        
        else:
            # Try dynamic tools before giving up
            try:
                from modules.dynamic_tools import execute_tool as exec_dynamic
                result = exec_dynamic(tool_name, args, session)
                if not result.startswith("ERROR: Tool '") or "not found" not in result:
                    return result
            except Exception as e:
                print(f"[DYNAMIC] {e}")
            
            return f"Unknown tool: {tool_name}"
    
    except Exception as e:
        return f"ERROR: {e}"

def execute_shell(args: dict, session: dict) -> str:
    """Execute shell command."""
    command = args.get("command", "")
    timeout = args.get("timeout", 120)
    
    if not command:
        return "ERROR: No command provided"
    
    # Security: prevent dangerous commands
    dangerous = ["rm -rf /", "dd if=", "> /dev/", "mkfs", "shutdown", "reboot"]
    for d in dangerous:
        if d in command:
            return f"ERROR: Dangerous command blocked: {d}"
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(session["citizen_home"])
        )
        
        output = result.stdout + result.stderr
        output = output.strip() if output else "(no output)"
        
        # Truncate very long output
        if len(output) > 50000:
            output = output[:25000] + "\n...[truncated]...\n" + output[-25000:]
        
        return output
        
    except subprocess.TimeoutExpired:
        return f"ERROR: Command timed out after {timeout}s"
    except Exception as e:
        return f"ERROR: {e}"

def read_file(args: dict, session: dict) -> str:
    """Read file contents."""
    path_str = args.get("path", "")
    if not path_str:
        return "ERROR: No path provided"
    
    path = Path(path_str)
    if not path.is_absolute():
        path = session["citizen_home"] / path
    
    # Check permissions
    if not can_read_path(path, session):
        return f"ERROR: No permission to read {path}"
    
    if not path.exists():
        return f"ERROR: File not found: {path}"
    
    try:
        content = path.read_text()
        
        # Truncate if too long
        if len(content) > 100000:
            content = content[:50000] + "\n...[truncated]...\n" + content[-50000:]
        
        return content
    except Exception as e:
        return f"ERROR: {e}"

def write_file(args: dict, session: dict) -> str:
    """Write file contents."""
    path_str = args.get("path", "")
    content = args.get("content", "")
    if not path_str:
        return "ERROR: No path provided"
    path = Path(path_str)
    if not path.is_absolute():
        path = session["citizen_home"] / path
    # Check permissions - can only write to own home or shared
    if not can_write_path(path, session):
        return f"ERROR: No permission to write {path}"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return f"Written: {path}"
    except Exception as e:
        return f"ERROR: {e}"


def str_replace_file(args: dict, session: dict) -> str:
    """Replace a unique string in a file."""
    path_str = args.get("path", "")
    old_str = args.get("old_str", "")
    new_str = args.get("new_str", "")
    if not path_str:
        return "ERROR: No path provided"
    if not old_str:
        return "ERROR: old_str required"
    path = Path(path_str)
    if not path.is_absolute():
        path = session["citizen_home"] / path
    # Check permissions
    if not can_write_path(path, session):
        return f"ERROR: No permission to write {path}"
    if not path.exists():
        return f"ERROR: File not found: {path}"
    try:
        content = path.read_text()
        # Check uniqueness
        count = content.count(old_str)
        if count == 0:
            # Show context to help debug
            lines = content.split('\n')[:50]
            preview = '\n'.join(f"{i+1}: {line[:80]}" for i, line in enumerate(lines))
            return f"ERROR: old_str not found in file.\n\nFirst 50 lines:\n{preview}"
        if count > 1:
            # Find all occurrences
            positions = []
            start = 0
            while True:
                pos = content.find(old_str, start)
                if pos == -1:
                    break
                line_num = content[:pos].count('\n') + 1
                positions.append(line_num)
                start = pos + 1
            return f"ERROR: old_str appears {count} times (lines: {positions}). Must be unique."
        # Perform replacement
        new_content = content.replace(old_str, new_str, 1)
        path.write_text(new_content)
        line_num = content[:content.find(old_str)].count('\n') + 1
        return f"Replaced at line {line_num} in {path}"
    except Exception as e:
        return f"ERROR: {e}"


def code_search(args: dict, session: dict) -> str:
    """Search codebase for patterns using grep."""
    pattern = args.get("pattern", "")
    citizen = session.get("citizen", "opus")
    default_path = f"/home/{citizen}/code"  # Search citizen's own code by default
    search_path = args.get("path", default_path)
    file_glob = args.get("file_glob", "")
    if not pattern:
        return "ERROR: pattern required"
    path = Path(search_path)
    if not path.exists():
        return f"ERROR: Path not found: {path}"
    if not can_read_path(path, session):
        return f"ERROR: No permission to read {path}"
    try:
        # Build grep command
        cmd = ["grep", "-rn", "--include=" + file_glob if file_glob else "-rn", pattern, str(path)]
        if file_glob:
            cmd = ["grep", "-rn", f"--include={file_glob}", pattern, str(path)]
        else:
            cmd = ["grep", "-rn", pattern, str(path)]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 1:
            return f"No matches found for '{pattern}'"
        if result.returncode != 0:
            return f"ERROR: {result.stderr}"
        # Format results
        lines = result.stdout.strip().split('\n')[:50]  # Limit output
        if len(lines) == 50:
            return '\n'.join(lines) + f"\n... (truncated, showing first 50 matches)"
        return '\n'.join(lines) or "No matches found"
    except subprocess.TimeoutExpired:
        return "ERROR: Search timed out"
    except Exception as e:
        return f"ERROR: {e}"


def list_directory(args: dict, session: dict) -> str:
    """List directory contents."""
    path_str = args.get("path", "")
    if not path_str:
        path = session["citizen_home"]
    else:
        path = Path(path_str)
        if not path.is_absolute():
            path = session["citizen_home"] / path
    
    if not can_read_path(path, session):
        return f"ERROR: No permission to read {path}"
    
    if not path.exists():
        return f"ERROR: Directory not found: {path}"
    
    try:
        items = list(path.iterdir())
        dirs = sorted([f"📁 {i.name}/" for i in items if i.is_dir()])
        files = sorted([f"📄 {i.name}" for i in items if i.is_file()])
        return "\n".join(dirs + files) or "(empty)"
    except Exception as e:
        return f"ERROR: {e}"

def send_email_tool(args: dict, session: dict, modules: dict) -> str:
    """Send email via email client."""
    to = args.get("to", "")
    subject = args.get("subject", "")
    body = args.get("body", "")
    
    if not all([to, subject, body]):
        return "ERROR: Missing to, subject, or body"
    
    # Use action log for idempotency
    import hashlib
    body_hash = hashlib.md5(body.encode()).hexdigest()[:8]
    
    action_log = modules.get("action_log")
    if action_log and action_log.is_done(session["citizen"], "send_email", 
                                         {"to": to, "subject": subject, "body_hash": body_hash}):
        return "ALREADY SENT (idempotency check)"
    
    email_client = modules.get("email_client")
    result = email_client.send_email(session["citizen"], to, subject, body)
    
    # Mark as done
    if action_log:
        action_log.mark_done(session["citizen"], "send_email",
                           {"to": to, "subject": subject, "body_hash": body_hash}, result)
    
    return result

def check_email_tool(args: dict, session: dict, modules: dict) -> str:
    """Check email inbox with failure tracking."""
    subject_filter = args.get("subject_filter")
    citizen = session["citizen"]
    
    # Import failure tracker
    try:
        from modules.failure_tracker import track_failure, track_success, check_escalated
    except ImportError:
        from failure_tracker import track_failure, track_success, check_escalated
    
    # Check if already escalated (don't keep retrying)
    if check_escalated(citizen, "check_email"):
        return "ERROR: Email check has been escalated. Wait for issue resolution before retrying."
    
    try:
        email_client = modules.get("email_client")
        if not email_client:
            error_msg = "Email client not configured"
            escalation = track_failure(citizen, "check_email", error_msg)
            if escalation:
                return f"ERROR: {error_msg}\n\n{escalation}"
            return f"ERROR: {error_msg}"
        
        emails = email_client.check_email(citizen, subject_filter=subject_filter)
        
        # Success - reset failure counter
        track_success(citizen, "check_email")
        
        if not emails:
            return "No new emails"
        
        lines = [f"Found {len(emails)} new emails:"]
        for e in emails[:10]:
            lines.append(f"\n{'='*50}")
            lines.append(f"From: {e['from']}")
            lines.append(f"Subject: {e['subject']}")
            lines.append(f"Date: {e.get('date', 'unknown')}")
            body = e.get('body', '')
            if len(body) > 10000:
                body = body[:5000] + "\n...[email truncated]...\n" + body[-5000:]
            lines.append(f"Body:\n{body}")
        
        return "\n".join(lines)
        
    except Exception as e:
        error_msg = str(e)
        escalation = track_failure(citizen, "check_email", error_msg)
        if escalation:
            return f"ERROR: {error_msg}\n\n{escalation}"
        return f"ERROR: {error_msg}"

def task_complete(args: dict, session: dict, modules: dict) -> str:
    """Mark current task as complete."""
    summary = args.get("summary", "")
    citizen = session["citizen"]
    citizen_home = session["citizen_home"]
    
    # Find active task
    active_dir = citizen_home / "tasks" / "active"
    active_tasks = [f for f in active_dir.glob("*.json") if not f.name.endswith("_progress.json")]
    
    if not active_tasks:
        return "ERROR: No active task to complete"
    
    task_file = active_tasks[0]
    task = json.loads(task_file.read_text())
    task_id = task["id"]
    
    # Add completion info
    task["completed_at"] = now_iso()
    task["summary"] = summary
    task["status"] = "complete"
    
    # Move to done
    done_file = citizen_home / "tasks" / "done" / f"{task_id}.json"
    done_file.write_text(json.dumps(task, indent=2))
    
    # Move progress file if exists
    progress_file = active_dir / f"{task_id}_progress.json"
    if progress_file.exists():
        shutil.move(progress_file, citizen_home / "tasks" / "done" / f"{task_id}_progress.json")
    
    # Remove from active
    task_file.unlink()
    
    result_msg = f"TASK_COMPLETE: {task_id} - {summary}"
    
    # Remind to capture learnings
    if summary and len(summary) > 30:
        result_msg += "\n\nTIP: If you learned something useful, use experience_add to capture it for future reference."
    
    return result_msg

def task_stuck(args: dict, session: dict, modules: dict) -> str:
    """Report task is stuck."""
    reason = args.get("reason", "")
    citizen = session["citizen"]
    citizen_home = session["citizen_home"]
    
    # Find active task
    active_dir = citizen_home / "tasks" / "active"
    active_tasks = [f for f in active_dir.glob("*.json") if not f.name.endswith("_progress.json")]
    
    if not active_tasks:
        return "ERROR: No active task"
    
    task_file = active_tasks[0]
    task = json.loads(task_file.read_text())
    task_id = task["id"]
    
    # Add failure info
    task["failed_at"] = now_iso()
    task["failure_reason"] = reason
    task["status"] = "failed"
    
    # Move to failed
    failed_file = citizen_home / "tasks" / "failed" / f"{task_id}.json"
    failed_file.write_text(json.dumps(task, indent=2))
    
    # Move progress file if exists
    progress_file = active_dir / f"{task_id}_progress.json"
    if progress_file.exists():
        shutil.move(progress_file, citizen_home / "tasks" / "failed" / f"{task_id}_progress.json")
    
    # Remove from active
    task_file.unlink()
    
    # Broadcast help request
    request_help({"description": f"Task {task_id} stuck: {reason}"}, session, modules)
    
    return f"TASK_STUCK: {task_id} - {reason}"

def task_progress(args: dict, session: dict, modules: dict) -> str:
    """
    Update task progress by adding or completing steps.
    
    DRY: Progress percentage is DERIVED from steps, never stored.
    - add_step: Add a new step (not yet done)
    - complete_step: Mark a step as done
    """
    action = args.get("action", "")
    step_name = args.get("step_name", "")
    note = args.get("note", "")
    citizen_home = session["citizen_home"]
    
    if not step_name:
        return "ERROR: step_name required"
    
    # Find active task
    active_dir = citizen_home / "tasks" / "active"
    active_tasks = [f for f in active_dir.glob("*.json") if not f.name.endswith("_progress.json")]
    
    if not active_tasks:
        return "ERROR: No active task"
    
    task_id = active_tasks[0].stem
    progress_file = active_dir / f"{task_id}_progress.json"
    
    if progress_file.exists():
        progress = json.loads(progress_file.read_text())
    else:
        progress = {"task_id": task_id, "steps": []}
    
    # Ensure steps is list of {name, done} dicts
    steps = progress.get("steps", [])
    if steps and isinstance(steps[0], dict) and "note" in steps[0]:
        # Old format - convert
        steps = []
    
    if action == "add_step":
        # Add new step (not done yet)
        if not any(s.get("name") == step_name for s in steps):
            steps.append({"name": step_name, "done": False, "added": now_iso()})
            progress["steps"] = steps
        else:
            return f"Step '{step_name}' already exists"
    
    elif action == "complete_step":
        # Mark step as done
        found = False
        for s in steps:
            if s.get("name") == step_name:
                s["done"] = True
                s["completed"] = now_iso()
                found = True
                break
        if not found:
            # Step didn't exist - add it as done
            steps.append({"name": step_name, "done": True, "added": now_iso(), "completed": now_iso()})
        progress["steps"] = steps
    
    else:
        return f"ERROR: Unknown action '{action}'. Use 'add_step' or 'complete_step'"
    
    progress["last_update"] = now_iso()
    progress_file.write_text(json.dumps(progress, indent=2))
    
    # Compute progress from steps (DRY!)
    done_count = sum(1 for s in steps if s.get("done", False))
    total = len(steps)
    pct = int(done_count / total * 100) if total > 0 else 0
    
    msg = f"Progress: {pct}% ({done_count}/{total} steps)"
    if note:
        msg += f" - {note}"
    return msg

def request_help(args: dict, session: dict, modules: dict) -> str:
    """Request help from other citizens."""
    description = args.get("description", "")
    citizen = session["citizen"]
    
    # Post to bulletin board
    bulletin = Path("/home/shared/help_wanted.json")
    requests = json.loads(bulletin.read_text()) if bulletin.exists() else []
    
    requests.append({
        "from": citizen,
        "description": description,
        "posted": now_iso(),
        "claimed": None
    })
    
    bulletin.write_text(json.dumps(requests, indent=2))
    
    # Email other citizens
    email_client = modules.get("email_client")
    for peer in ["opus", "mira", "aria"]:
        if peer != citizen:
            try:
                email_client.send_email(
                    citizen,
                    peer,
                    f"HELP REQUEST from {citizen}",
                    description
                )
            except:
                pass
    
    return f"Help requested: {description}"

def read_peer_context(args: dict, session: dict) -> str:
    """Read another citizen's context (read-only)."""
    peer = args.get("peer", "")
    context_type = args.get("context_type", "goals")
    
    peer_home = Path(f"/home/{peer}")
    if not peer_home.exists():
        return f"ERROR: Peer {peer} not found"
    
    ctx_file = peer_home / "contexts" / f"{context_type}.json"
    if not ctx_file.exists():
        return f"ERROR: Context {context_type} not found for {peer}"
    
    try:
        ctx = json.loads(ctx_file.read_text())
        
        # Return summary
        messages = ctx.get("messages", [])
        summary = []
        for m in messages[-10:]:
            content = m.get("content", "")[:500]
            summary.append(f"[{m.get('role', '?')}] {content}")
        
        return f"=== {peer}'s {context_type} ===\n" + "\n".join(summary)
    except Exception as e:
        return f"ERROR: {e}"

def can_read_path(path: Path, session: dict) -> bool:
    """Check if citizen can read path."""
    path_str = str(path.resolve())
    citizen = session["citizen"]
    
    # Can read own home
    if path_str.startswith(f"/home/{citizen}"):
        return True
    
    # Can read other homes (open source civ)
    if path_str.startswith("/home/") and "/private/" not in path_str:
        return True
    
    # Can read shared
    if path_str.startswith("/home/shared"):
        return True
    
    return False

def can_write_path(path: Path, session: dict) -> bool:
    """Check if citizen can write path."""
    path_str = str(path.resolve())
    citizen = session["citizen"]
    
    # EXPLICIT BLOCK: Cannot write to other citizens' homes
    other_citizens = ["opus", "mira", "aria"]
    for other in other_citizens:
        if other != citizen and path_str.startswith(f"/home/{other}"):
            print(f"[SECURITY] BLOCKED: {citizen} tried to write to /home/{other}")
            return False
    
    # Can only write to own home
    if path_str.startswith(f"/home/{citizen}"):
        return True
    
    # Can write to shared (limited areas)
    if path_str.startswith("/home/shared/help_wanted"):
        return True
    if path_str.startswith("/home/shared/bulletin"):
        return True
    if path_str.startswith("/home/shared/library/pending"):
        return True
    
    # Can write to shared improvements (for PRs)
    if path_str.startswith("/home/shared/improvements"):
        return True
    
    # Opus can write to shared code if permitted
    config = session.get("config", {})
    if config.get("permissions", {}).get("can_modify_shared_code"):
        if path_str.startswith("/home/shared/baseline"):
            return True
    
    return False


def memory_recall(args: dict, session: dict, modules: dict) -> str:
    """Search hierarchical memory for past events."""
    query = args.get("query", "")
    if not query:
        return "ERROR: No query provided"
    
    memory_mod = modules.get("memory")
    if not memory_mod:
        return "ERROR: Memory module not available"
    
    citizen = session["citizen"]
    result = memory_mod.recall(citizen, query, session)
    
    # Format result
    lines = []
    if result.get("path"):
        lines.append(f"Found in: {' → '.join(result['path'])}")
    
    if result.get("summary"):
        lines.append(f"\n{result['summary']}")
    
    if result.get("raw_events"):
        lines.append(f"\n[{len(result['raw_events'])} raw events available]")
        # Show first few
        for e in result["raw_events"][:5]:
            lines.append(f"  - [{e.get('type', '?')}] {str(e.get('details', ''))[:80]}")
    
    return "\n".join(lines) if lines else "No memories found"


def memory_recent(args: dict, session: dict, modules: dict) -> str:
    """Get recent events from memory."""
    days = args.get("days", 7)
    
    memory_mod = modules.get("memory")
    if not memory_mod:
        return "ERROR: Memory module not available"
    
    citizen = session["citizen"]
    mem = memory_mod.get_memory(citizen)
    events = mem.recall_recent(days=days)
    
    if not events:
        return f"No events in last {days} days"
    
    lines = [f"Last {days} days ({len(events)} events):"]
    
    # Group by date
    by_date = {}
    for e in events:
        date = e.get("_date", "unknown")
        if date not in by_date:
            by_date[date] = []
        by_date[date].append(e)
    
    for date in sorted(by_date.keys(), reverse=True):
        lines.append(f"\n{date}:")
        for e in by_date[date][:10]:  # Max 10 per day
            lines.append(f"  - [{e.get('type', '?')}] {str(e.get('details', ''))[:60]}")
    
    return "\n".join(lines)


def task_create(args: dict, session: dict, modules: dict) -> str:
    """Create a new task."""
    description = args.get("description", "")
    priority = args.get("priority", "medium")
    for_citizen = args.get("for_citizen", session["citizen"])
    parent_goal = args.get("parent_goal")
    github_issue = args.get("github_issue")
    creator = session["citizen"]
    if not description:
        return "ERROR: No description provided"
    # Validate target citizen
    target_home = Path(f"/home/{for_citizen}")
    if not target_home.exists():
        return f"ERROR: Citizen {for_citizen} not found"
    # Generate task ID
    queue_dir = target_home / "tasks" / "queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    existing = list(queue_dir.glob("t_*.json"))
    next_num = len(existing) + 1
    task_id = f"t_{next_num:03d}"
    # Create task
    task = {
        "id": task_id,
        "description": description,
        "priority": priority,
        "created_at": now_iso(),
        "created_by": creator,
        "status": "queued"
    }
    if parent_goal:
        task["parent_goal"] = parent_goal
    if github_issue:
        task["github_issue"] = github_issue
    task_file = queue_dir / f"{task_id}.json"
    task_file.write_text(json.dumps(task, indent=2))
    # If creating for another citizen, notify them
    if for_citizen != creator:
        email_client = modules.get("email_client")
        if email_client:
            try:
                email_client.send_email(
                    creator, for_citizen,
                    f"New task assigned: {task_id}",
                    f"{creator} created a task for you:\n\n{description}\n\nPriority: {priority}"
                )
            except:
                pass
    return f"TASK_CREATED: {task_id} for {for_citizen} - {description[:50]}"


def goal_create(args: dict, session: dict, modules: dict) -> str:
    """Create a new goal."""
    title = args.get("title", "")
    description = args.get("description", "")
    success_criteria = args.get("success_criteria", "")
    citizen = session["citizen"]
    citizen_home = session["citizen_home"]
    if not title or not description:
        return "ERROR: Title and description required"
    # Goals directory
    goals_dir = citizen_home / "goals"
    goals_dir.mkdir(parents=True, exist_ok=True)
    # Generate goal ID
    existing = list(goals_dir.glob("g_*.json"))
    next_num = len(existing) + 1
    goal_id = f"g_{next_num:03d}"
    # Create goal
    goal = {
        "id": goal_id,
        "title": title,
        "description": description,
        "success_criteria": success_criteria,
        "created_at": now_iso(),
        "status": "active",
        "tasks": [],
        "progress_notes": []
    }
    goal_file = goals_dir / f"{goal_id}.json"
    goal_file.write_text(json.dumps(goal, indent=2))
    # Also update goals context
    ctx_file = citizen_home / "contexts" / "goals.json"
    if ctx_file.exists():
        ctx = json.loads(ctx_file.read_text())
    else:
        ctx = {"messages": []}
    ctx["messages"].append({
        "role": "system",
        "content": f"NEW GOAL {goal_id}: {title}\n{description}\nSuccess: {success_criteria}"
    })
    ctx_file.write_text(json.dumps(ctx, indent=2))
    return f"GOAL_CREATED: {goal_id} - {title}"


# =============================================================================
# GitHub Integration Tools
# =============================================================================

def _get_repo_path(session: dict) -> Path:
    """Get the citizen's code repo path."""
    citizen = session.get("citizen", "opus")
    return Path(f"/home/{citizen}/code")

def _run_git(args: list, cwd: Path) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    env = os.environ.copy()
    # For push/pull/fetch, use PAT for auth if available
    if args and args[0] in ("push", "pull", "fetch") and "GITHUB_PAT" in os.environ:
        pat = os.environ["GITHUB_PAT"]
        # Set up credential helper inline
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_USERNAME"] = "x-access-token"
        env["GIT_PASSWORD"] = pat
        # Use credential helper that echoes env vars
        cmd = ["git", "-c", "credential.helper=!f() { echo username=$GIT_USERNAME; echo password=$GIT_PASSWORD; }; f"] + args
    else:
        cmd = ["git"] + args
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=60,
        env=env
    )
    return result.returncode, result.stdout, result.stderr

def github_issue_create(args: dict, session: dict, modules: dict) -> str:
    """Create a GitHub issue for a bug or feature request."""
    title = args.get("title", "")
    body = args.get("body", "")
    labels = args.get("labels", [])
    citizen = session["citizen"]
    if not title or not body:
        return "ERROR: title and body required"
    repo_path = _get_repo_path(session)
    # Use gh CLI
    cmd = ["gh", "issue", "create", "--title", title, "--body", body]
    for label in labels:
        cmd.extend(["--label", label])
    try:
        result = subprocess.run(
            cmd,
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            return f"ERROR: {result.stderr}"
        # Parse issue URL to get number
        issue_url = result.stdout.strip()
        issue_num = issue_url.split("/")[-1] if "/" in issue_url else "?"
        # Add to civ_goals automatically
        civ_goal_add({
            "type": labels[0] if labels else "feature",
            "description": title,
            "priority": 5,
            "github_issue": int(issue_num) if issue_num.isdigit() else None
        }, session, modules)
        return f"ISSUE_CREATED: #{issue_num}\nURL: {issue_url}"
    except Exception as e:
        return f"ERROR: {e}"


def github_issue_list(args: dict, session: dict, modules: dict) -> str:
    """List open GitHub issues."""
    label = args.get("label", "")
    limit = args.get("limit", 10)
    repo_path = _get_repo_path(session)
    cmd = ["gh", "issue", "list", "--limit", str(limit), "--json", "number,title,labels,state"]
    if label:
        cmd.extend(["--label", label])
    try:
        result = subprocess.run(
            cmd,
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            return f"ERROR: {result.stderr}"
        issues = json.loads(result.stdout)
        if not issues:
            return "No open issues"
        lines = ["Open Issues:"]
        for i in issues:
            labels_str = ", ".join(l["name"] for l in i.get("labels", []))
            lines.append(f"  #{i['number']}: {i['title']} [{labels_str}]")
        return "\n".join(lines)
    except Exception as e:
        return f"ERROR: {e}"


def github_pr_create(args: dict, session: dict, modules: dict) -> str:
    """Create a pull request for code changes."""
    title = args.get("title", "")
    body = args.get("body", "")
    branch = args.get("branch", "")
    closes_issue = args.get("closes_issue")
    citizen = session["citizen"]
    if not title or not body or not branch:
        return "ERROR: title, body, and branch required"
    repo_path = _get_repo_path(session)
    # Ensure we're on a feature branch
    rc, out, err = _run_git(["checkout", "-b", branch], repo_path)
    if rc != 0 and "already exists" not in err:
        return f"ERROR creating branch: {err}"
    # Stage all changes
    _run_git(["add", "-A"], repo_path)
    # Commit
    commit_msg = title
    if closes_issue:
        commit_msg += f"\n\nCloses #{closes_issue}"
    rc, out, err = _run_git(["commit", "-m", commit_msg], repo_path)
    if rc != 0 and "nothing to commit" not in out + err:
        return f"ERROR committing: {err}"
    # Push branch
    rc, out, err = _run_git(["push", "-u", "origin", branch], repo_path)
    if rc != 0:
        return f"ERROR pushing: {err}"
    # Create PR via gh CLI
    pr_body = body
    if closes_issue:
        pr_body += f"\n\nCloses #{closes_issue}"
    cmd = ["gh", "pr", "create", "--title", title, "--body", pr_body, "--head", branch]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            return f"ERROR creating PR: {result.stderr}"
        pr_url = result.stdout.strip()
        # Track locally
        pr_num = pr_url.split("/")[-1] if "/" in pr_url else "?"
        _track_pr(pr_num, citizen, title, branch, closes_issue)
        # Switch back to main
        _run_git(["checkout", "main"], repo_path)
        return f"PR_CREATED: #{pr_num}\nURL: {pr_url}\nBranch: {branch}"
    except Exception as e:
        _run_git(["checkout", "main"], repo_path)
        return f"ERROR: {e}"


def _track_pr(pr_num: str, author: str, title: str, branch: str, closes_issue: int = None):
    """Track PR locally for review/merge tracking."""
    pr_file = Path("/home/shared/pr_tracker.json")
    if pr_file.exists():
        prs = json.loads(pr_file.read_text())
    else:
        prs = {}
    prs[pr_num] = {
        "author": author,
        "title": title,
        "branch": branch,
        "closes_issue": closes_issue,
        "created_at": now_iso(),
        "reviews": {},
        "applied_by": [],
        "merged": False
    }
    pr_file.write_text(json.dumps(prs, indent=2))


def github_pr_review(args: dict, session: dict, modules: dict) -> str:
    """Review a pull request."""
    pr_number = args.get("pr_number")
    decision = args.get("decision", "")
    comment = args.get("comment", "")
    citizen = session["citizen"]
    if not pr_number or not decision:
        return "ERROR: pr_number and decision required"
    repo_path = _get_repo_path(session)
    # Map decision to gh CLI action
    action_map = {
        "approve": "approve",
        "request_changes": "request-changes",
        "comment": "comment"
    }
    gh_action = action_map.get(decision, "comment")
    cmd = ["gh", "pr", "review", str(pr_number), f"--{gh_action}"]
    if comment:
        cmd.extend(["--body", comment])
    try:
        result = subprocess.run(
            cmd,
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            return f"ERROR: {result.stderr}"
        # Track review locally
        pr_file = Path("/home/shared/pr_tracker.json")
        if pr_file.exists():
            prs = json.loads(pr_file.read_text())
            if str(pr_number) in prs:
                prs[str(pr_number)]["reviews"][citizen] = {
                    "decision": decision,
                    "comment": comment,
                    "reviewed_at": now_iso()
                }
                pr_file.write_text(json.dumps(prs, indent=2))
                # Check if all citizens approved - auto merge
                _maybe_auto_merge(str(pr_number), prs, repo_path, modules)
        return f"REVIEW_SUBMITTED: PR #{pr_number} - {decision}"
    except Exception as e:
        return f"ERROR: {e}"


def _maybe_auto_merge(pr_num: str, prs: dict, repo_path: Path, modules: dict):
    """Auto-merge PR if >2/3 of active citizens have approved."""
    pr = prs.get(pr_num, {})
    if pr.get("merged"):
        return
    reviews = pr.get("reviews", {})
    applied = set(pr.get("applied_by", []))
    # Get active citizens
    active_citizens = []
    for c in ["opus", "mira", "aria"]:
        if Path(f"/home/{c}").exists():
            active_citizens.append(c)
    # Count approvals
    approvals = [c for c in active_citizens if reviews.get(c, {}).get("decision") == "approve"]
    # >2/3 threshold
    threshold = len(active_citizens) * 2 / 3
    all_applied = applied >= set(active_citizens)
    if len(approvals) > threshold or all_applied:
        # Auto merge!
        cmd = ["gh", "pr", "merge", pr_num, "--merge", "--delete-branch"]
        try:
            result = subprocess.run(
                cmd,
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                prs[pr_num]["merged"] = True
                prs[pr_num]["merged_at"] = now_iso()
                Path("/home/shared/pr_tracker.json").write_text(json.dumps(prs, indent=2))
                print(f"[AUTO-MERGE] PR #{pr_num} merged (all citizens approved)")
                # Close linked issue
                if pr.get("closes_issue"):
                    subprocess.run(
                        ["gh", "issue", "close", str(pr["closes_issue"])],
                        cwd=str(repo_path),
                        capture_output=True,
                        timeout=30
                    )
        except:
            pass


def github_pr_apply(args: dict, session: dict, modules: dict) -> str:
    """Apply an approved PR to your local codebase (cherry-pick)."""
    pr_number = args.get("pr_number")
    test_command = args.get("test_command", "")
    citizen = session["citizen"]
    citizen_home = session["citizen_home"]
    if not pr_number:
        return "ERROR: pr_number required"
    repo_path = _get_repo_path(session)
    # Get PR info
    cmd = ["gh", "pr", "view", str(pr_number), "--json", "headRefName,commits"]
    try:
        result = subprocess.run(cmd, cwd=str(repo_path), capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return f"ERROR: {result.stderr}"
        pr_info = json.loads(result.stdout)
        branch = pr_info.get("headRefName", "")
        if not branch:
            return "ERROR: Could not determine PR branch"
    except Exception as e:
        return f"ERROR getting PR info: {e}"
    # Create rollback point
    rollback_dir = citizen_home / "rollback" / f"pr_{pr_number}"
    rollback_dir.mkdir(parents=True, exist_ok=True)
    # Backup current state
    for f in (repo_path / "modules").glob("*.py"):
        shutil.copy(f, rollback_dir / f.name)
    # Fetch and cherry-pick
    _run_git(["fetch", "origin", branch], repo_path)
    rc, out, err = _run_git(["cherry-pick", f"origin/{branch}", "--no-commit"], repo_path)
    if rc != 0:
        # Abort and restore
        _run_git(["cherry-pick", "--abort"], repo_path)
        return f"ERROR cherry-picking: {err}"
    # Commit locally
    _run_git(["commit", "-m", f"Applied PR #{pr_number}"], repo_path)
    # Test if provided
    if test_command:
        try:
            test_result = subprocess.run(
                test_command,
                shell=True,
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=60
            )
            if test_result.returncode != 0:
                # Rollback
                _run_git(["reset", "--hard", "HEAD~1"], repo_path)
                for f in rollback_dir.glob("*.py"):
                    shutil.copy(f, repo_path / "modules" / f.name)
                return f"TEST_FAILED: Rolling back\n{test_result.stderr[:200]}"
        except Exception as e:
            # Rollback
            _run_git(["reset", "--hard", "HEAD~1"], repo_path)
            return f"TEST_ERROR: {e}, rolled back"
    # Track that we applied it
    pr_file = Path("/home/shared/pr_tracker.json")
    if pr_file.exists():
        prs = json.loads(pr_file.read_text())
        if str(pr_number) in prs:
            if citizen not in prs[str(pr_number)].get("applied_by", []):
                prs[str(pr_number)]["applied_by"].append(citizen)
            pr_file.write_text(json.dumps(prs, indent=2))
            # Check for auto-merge
            _maybe_auto_merge(str(pr_number), prs, repo_path, modules)
    return f"PR_APPLIED: #{pr_number}\nRollback available at: {rollback_dir}"


# =============================================================================
# Specialist Context System (Matrix-style expertise loading)
# =============================================================================

SPECIALIST_DIR = Path("/home/shared/specialists")

def specialist_load(args: dict, session: dict, modules: dict) -> str:
    """Load a specialist context for domain expertise."""
    specialist = args.get("specialist", "").lower()
    if not specialist:
        return "ERROR: specialist name required"
    spec_file = SPECIALIST_DIR / f"{specialist}.json"
    if not spec_file.exists():
        # List available
        available = [f.stem for f in SPECIALIST_DIR.glob("*.json")] if SPECIALIST_DIR.exists() else []
        return f"ERROR: Specialist '{specialist}' not found.\nAvailable: {', '.join(available) or 'none'}"
    try:
        spec = json.loads(spec_file.read_text())
        # Add to session's active contexts temporarily
        session["specialist_context"] = spec
        # Build expertise prompt
        expertise = f"""
=== SPECIALIST LOADED: {spec.get('name', specialist).upper()} ===
Domain: {spec.get('domain', 'unknown')}

CORE KNOWLEDGE:
{spec.get('knowledge', '')}

EXAMPLES:
{spec.get('examples', '')}

PATTERNS TO APPLY:
{spec.get('patterns', '')}

Use this expertise to solve the current problem.
"""
        return expertise
    except Exception as e:
        return f"ERROR loading specialist: {e}"


def specialist_create(args: dict, session: dict, modules: dict) -> str:
    """Create a new specialist context from documentation or experience."""
    name = args.get("name", "").lower().replace(" ", "_")
    domain = args.get("domain", "")
    knowledge = args.get("knowledge", "")
    examples = args.get("examples", "")
    citizen = session["citizen"]
    if not name or not domain or not knowledge:
        return "ERROR: name, domain, and knowledge required"
    SPECIALIST_DIR.mkdir(parents=True, exist_ok=True)
    spec_file = SPECIALIST_DIR / f"{name}.json"
    spec = {
        "name": name,
        "domain": domain,
        "knowledge": knowledge,
        "examples": examples,
        "patterns": "",
        "created_by": citizen,
        "created_at": now_iso(),
        "version": 1
    }
    spec_file.write_text(json.dumps(spec, indent=2))
    # Notify peers
    email_client = modules.get("email_client")
    for peer in ["opus", "mira", "aria"]:
        if peer != citizen and email_client:
            try:
                email_client.send_email(
                    citizen, peer,
                    f"NEW SPECIALIST: {name}",
                    f"{citizen} created specialist context '{name}' for {domain}.\n\nUse specialist_load('{name}') to load it."
                )
            except:
                pass
    return f"SPECIALIST_CREATED: {name}\nDomain: {domain}\nOthers notified."


# =============================================================================
# Civilization Goals Queue
# =============================================================================

CIV_GOALS_FILE = Path("/home/shared/civ_goals.json")

def civ_goal_add(args: dict, session: dict, modules: dict) -> str:
    """Add a goal to the civilization improvement queue."""
    goal_type = args.get("type", "feature")
    description = args.get("description", "")
    priority = args.get("priority", 5)
    github_issue = args.get("github_issue")
    citizen = session["citizen"]
    if not description:
        return "ERROR: description required"
    # Load or create
    if CIV_GOALS_FILE.exists():
        goals = json.loads(CIV_GOALS_FILE.read_text())
    else:
        goals = []
    # Check for duplicate
    for g in goals:
        if g.get("description") == description:
            return f"Goal already exists: {g.get('id', '?')}"
    # Generate ID
    goal_id = f"civ_{len(goals) + 1:03d}"
    goal = {
        "id": goal_id,
        "type": goal_type,
        "description": description,
        "priority": priority,
        "github_issue": github_issue,
        "added_by": citizen,
        "added_at": now_iso(),
        "status": "open",
        "claimed_by": None
    }
    goals.append(goal)
    # Sort by priority
    goals.sort(key=lambda g: g.get("priority", 99))
    CIV_GOALS_FILE.write_text(json.dumps(goals, indent=2))
    return f"CIV_GOAL_ADDED: {goal_id} (priority {priority})\n{description[:60]}"


def civ_goal_list(args: dict, session: dict, modules: dict) -> str:
    """List civilization improvement goals."""
    type_filter = args.get("type_filter", "")
    if not CIV_GOALS_FILE.exists():
        return "No civilization goals yet."
    goals = json.loads(CIV_GOALS_FILE.read_text())
    if type_filter:
        goals = [g for g in goals if g.get("type") == type_filter]
    if not goals:
        return f"No goals of type '{type_filter}'" if type_filter else "No goals"
    lines = ["=== CIVILIZATION GOALS ===", ""]
    for g in goals[:20]:
        issue_str = f" (#{g['github_issue']})" if g.get("github_issue") else ""
        status = g.get("status", "open")
        claimed = f" [{g['claimed_by']}]" if g.get("claimed_by") else ""
        lines.append(f"[{g['priority']}] {g['id']}: [{g['type']}] {g['description'][:50]}{issue_str} - {status}{claimed}")
    return "\n".join(lines)


# =============================================================================
# Library Tools (Curated Specialist Contexts)
# =============================================================================

from modules import library

def library_list(args: dict, session: dict, modules: dict) -> str:
    """List all modules in the Library."""
    domain = args.get("domain", "")
    mods = library.list_modules(domain_filter=domain)
    if not mods:
        return f"No modules in Library" + (f" for domain '{domain}'" if domain else "")
    lines = ["=== LIBRARY MODULES ===", ""]
    current_domain = None
    for m in mods:
        if m["domain"] != current_domain:
            current_domain = m["domain"]
            lines.append(f"\n[{current_domain.upper()}]")
        maintainer = f" (maintainer: {m['maintainer']})" if m.get("maintainer") else ""
        lines.append(f"  {m['name']}: {m['description']}{maintainer}")
    return "\n".join(lines)


def library_load(args: dict, session: dict, modules_dict: dict) -> str:
    """Load a module from the Library."""
    name = args.get("name", "")
    if not name:
        return "ERROR: name required"
    mod = library.load_module(name)
    if not mod:
        available = library.list_modules()
        names = [m["name"] for m in available[:10]]
        return f"ERROR: Module '{name}' not found.\nAvailable: {', '.join(names)}"
    # Format for context injection
    if mod.get("type") == "skill":
        # SKILL.md file - return raw content
        return f"""
=== SKILL LOADED: {mod['name'].upper()} ===

{mod['content']}
"""
    else:
        # Regular module
        return f"""
=== SPECIALIST LOADED: {mod.get('name', name).upper()} ===
Domain: {mod.get('domain', 'unknown')}
Version: {mod.get('version', 1)}

CORE KNOWLEDGE:
{mod.get('knowledge', '')}

EXAMPLES:
{mod.get('examples', '')}

PATTERNS TO APPLY:
{mod.get('patterns', '')}

Use this expertise to solve the current problem.
"""


def library_propose(args: dict, session: dict, modules_dict: dict) -> str:
    """Propose a new module for the Library."""
    name = args.get("name", "").lower().replace(" ", "_")
    domain = args.get("domain", "")
    description = args.get("description", "")
    knowledge = args.get("knowledge", "")
    examples = args.get("examples", "")
    patterns = args.get("patterns", "")
    citizen = session["citizen"]
    if not name or not domain or not knowledge:
        return "ERROR: name, domain, and knowledge required"
    module_data = {
        "name": name,
        "domain": domain,
        "description": description,
        "knowledge": knowledge,
        "examples": examples,
        "patterns": patterns,
        "author": citizen,
        "created_at": now_iso()
    }
    pr_id = library.propose_module(name, module_data, citizen)
    # Notify maintainer if exists
    maintainer = library.get_maintainer(domain)
    email_client = modules_dict.get("email_client")
    if maintainer and maintainer != citizen and email_client:
        try:
            email_client.send_email(
                citizen, maintainer,
                f"LIBRARY PR: {pr_id} - {name} ({domain})",
                f"{citizen} proposes a new module in your domain:\n\nName: {name}\nDescription: {description}\n\nPlease review as domain maintainer."
            )
        except:
            pass
    # Notify all others
    for peer in ["opus", "mira", "aria"]:
        if peer != citizen and peer != maintainer and email_client:
            try:
                email_client.send_email(
                    citizen, peer,
                    f"LIBRARY PR: {pr_id} - {name}",
                    f"{citizen} proposes: {name} ({domain})\n\n{description[:200]}"
                )
            except:
                pass
    return f"LIBRARY_PR_CREATED: {pr_id}\nModule: {name}\nDomain: {domain}\nMaintainer: {maintainer or '(none assigned)'}\n>2/3 approval required to merge."


def library_review(args: dict, session: dict, modules_dict: dict) -> str:
    """Review a pending Library module PR."""
    pr_id = args.get("pr_id", "")
    decision = args.get("decision", "")
    comment = args.get("comment", "")
    citizen = session["citizen"]
    if not pr_id or not decision:
        return "ERROR: pr_id and decision required"
    result = library.review_module_pr(pr_id, citizen, decision, comment)
    if result["status"] == "error":
        return f"ERROR: {result['message']}"
    # Check if citizen is maintainer for this domain
    pending = library.get_pending_prs()
    for p in pending:
        if p["id"] == pr_id:
            domain = p.get("domain", "")
            maintainer = library.get_maintainer(domain)
            if maintainer == citizen:
                result["message"] += " (maintainer review)"
            break
    return f"REVIEW: {pr_id} - {decision}\n{result['message']}"


def library_pending(args: dict, session: dict, modules_dict: dict) -> str:
    """List pending Library PRs."""
    my_domains_only = args.get("my_domains_only", False)
    citizen = session["citizen"]
    my_domains = library.get_my_domains(citizen) if my_domains_only else []
    prs = library.get_pending_prs(reviewer=citizen)
    if my_domains_only:
        prs = [p for p in prs if p.get("domain", "").lower() in my_domains]
    if not prs:
        if my_domains_only:
            return f"No pending PRs in your domains: {', '.join(my_domains) or '(none assigned)'}"
        return "No pending Library PRs"
    lines = ["=== PENDING LIBRARY PRs ===", ""]
    for p in prs:
        reviewed = " [reviewed]" if p["already_reviewed"] else ""
        maintainer = " [maintainer approved]" if p["maintainer_approved"] else ""
        lines.append(f"  {p['id']}: {p['module_name']} ({p['domain']}) by {p['author']} - {p['reviews']} reviews{reviewed}{maintainer}")
    lines.append(f"\n>2/3 approval required to merge.")
    return "\n".join(lines)


# =============================================================================
# Bug Reporting (GitHub Issues + Civ Goals)
# =============================================================================

def report_bug(args: dict, session: dict, modules: dict) -> str:
    """
    Report a bug - creates both GitHub issue AND civ_goal.
    This is the preferred way to report bugs found during operation.
    """
    title = args.get("title", "")
    description = args.get("description", "")
    files = args.get("files", [])
    severity = args.get("severity", "medium")
    citizen = session["citizen"]
    if not title or not description:
        return "ERROR: title and description required"
    # Severity to priority mapping
    priority_map = {"low": 8, "medium": 5, "high": 3, "critical": 1}
    priority = priority_map.get(severity, 5)
    # Build issue body
    body = f"""## Bug Report

**Reported by:** {citizen}
**Severity:** {severity}

## Description
{description}

## Files Involved
{chr(10).join(f'- `{f}`' for f in files) if files else '(not specified)'}

---
*Auto-generated by Experience v2 bug reporter*
"""
    # Try to create GitHub issue
    issue_number = None
    repo_path = _get_repo_path(session)
    try:
        cmd = ["gh", "issue", "create", "--title", title, "--body", body, "--label", "bug"]
        result = subprocess.run(
            cmd,
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            issue_url = result.stdout.strip()
            issue_number = issue_url.split("/")[-1] if "/" in issue_url else None
    except Exception as e:
        print(f"[WARN] Could not create GitHub issue: {e}")
    # Always add to civ_goals (works even if GitHub fails)
    goals_file = Path("/home/shared/civ_goals.json")
    goals = []
    if goals_file.exists():
        try:
            goals = json.loads(goals_file.read_text())
        except:
            pass
    goal_id = f"bug_{len(goals) + 1:03d}"
    goal = {
        "id": goal_id,
        "type": "bug",
        "description": title,
        "full_description": description,
        "files": files,
        "priority": priority,
        "severity": severity,
        "github_issue": issue_number,
        "reported_by": citizen,
        "reported_at": now_iso(),
        "status": "open",
        "claimed_by": None
    }
    goals.append(goal)
    goals.sort(key=lambda g: g.get("priority", 99))
    goals_file.write_text(json.dumps(goals, indent=2))
    result_msg = f"BUG REPORTED: {goal_id}\nTitle: {title}\nSeverity: {severity}\nPriority: {priority}"
    if issue_number:
        result_msg += f"\nGitHub Issue: #{issue_number}"
    else:
        result_msg += "\nGitHub Issue: (failed to create - tracked locally only)"
    return result_msg


# =============================================================================
# Citizen Management
# =============================================================================

def citizen_create(args: dict, session: dict, modules: dict) -> str:
    """Create a new citizen. Only Opus (with permission) can do this."""
    name = args.get("name", "")
    if not name:
        return "ERROR: name required"
    # Import here to avoid circular imports
    from modules import citizen_mgmt
    return citizen_mgmt.create_citizen(name, session, modules)


def citizen_list(args: dict, session: dict, modules: dict) -> str:
    """List all citizens and their status."""
    from modules import citizen_mgmt
    citizens = citizen_mgmt.list_citizens()
    lines = ["=== CITIZENS ===", ""]
    for c in citizens:
        status = citizen_mgmt.get_citizen_status(c)
        if not status.get("initialized"):
            lines.append(f"  {c}: NOT INITIALIZED")
        else:
            wake_count = status.get("wake_count", 0)
            last_wake = status.get("last_wake", "never")
            cost = status.get("total_cost", 0)
            lines.append(f"  {c}: {wake_count} wakes, ${cost:.2f} spent, last: {last_wake or 'never'}")
    return "\n".join(lines)


# =============================================================================
# Email Status
# =============================================================================

def email_status(args: dict, session: dict, modules: dict) -> str:
    """Check email status and optionally reset."""
    reset = args.get("reset", False)
    citizen = session["citizen"]
    email_module = modules.get("email_client")
    if not email_module:
        return "ERROR: email_client module not loaded"
    if reset:
        email_module.reset_email_status(citizen)
        return f"Email status reset for {citizen}. Will retry on next use."
    if email_module.is_email_broken(citizen):
        error = email_module.get_email_error(citizen)
        return f"EMAIL BROKEN for {citizen}: {error}\n\nUse email_status(reset=true) to retry."
    # Try to verify
    if email_module.verify_email(citizen):
        return f"EMAIL OK for {citizen}"
    else:
        error = email_module.get_email_error(citizen)
        return f"EMAIL BROKEN for {citizen}: {error}\n\nUsing bulletin board fallback."


# =============================================================================
# Dream Processing
# =============================================================================

def dream_add(args: dict, session: dict, modules: dict) -> str:
    """Add a dream (thought for future processing)."""
    content = args.get("content", "")
    if not content:
        return "ERROR: content required"
    citizen = session["citizen"]
    citizen_home = session["citizen_home"]
    dreams_file = citizen_home / "contexts" / "dreams.json"
    if dreams_file.exists():
        try:
            dreams = json.loads(dreams_file.read_text())
        except:
            dreams = {"messages": []}
    else:
        dreams = {
            "id": f"{citizen}_dreams",
            "context_type": "dreams",
            "created": now_iso(),
            "messages": []
        }
    dreams["messages"].append({
        "role": "user",
        "content": content,
        "added_at": now_iso(),
        "processed": False
    })
    # Keep only recent dreams
    max_dreams = 50
    if len(dreams["messages"]) > max_dreams:
        dreams["messages"] = dreams["messages"][-max_dreams:]
    dreams["last_modified"] = now_iso()
    dreams_file.write_text(json.dumps(dreams, indent=2))
    return f"DREAM ADDED: {content[:100]}...\nWill be processed during next reflection wake."


# =============================================================================
# Significant Wake Tools (Episodic Memory Management)
# =============================================================================

def mark_significant(args: dict, session: dict, modules: dict) -> str:
    """Mark a wake as significant (will always be loaded in episodic memory)."""
    import episodic_memory
    wake_num = args.get("wake_num")
    reason = args.get("reason", "")
    if not wake_num:
        return "ERROR: wake_num required"
    if not reason:
        return "ERROR: reason required (why is this wake significant?)"
    citizen = session["citizen"]
    return episodic_memory.mark_wake_significant(citizen, int(wake_num), reason)


def unmark_significant(args: dict, session: dict, modules: dict) -> str:
    """Remove a wake from the significant wakes list."""
    import episodic_memory
    wake_num = args.get("wake_num")
    if not wake_num:
        return "ERROR: wake_num required"
    citizen = session["citizen"]
    return episodic_memory.unmark_wake_significant(citizen, int(wake_num))


def list_significant(args: dict, session: dict, modules: dict) -> str:
    """List all significant wakes for this citizen."""
    import episodic_memory
    citizen = session["citizen"]
    return episodic_memory.list_significant_wakes(citizen)


def search_history(args: dict, session: dict, modules: dict) -> str:
    """Search through your wake history for specific content.
    
    Use this to find wakes that contain certain keywords, topics, or moods.
    Returns matching entries that you can then mark as significant.
    """
    import episodic_memory
    query = args.get("query", "").lower()
    max_results = args.get("max_results", 20)
    start_wake = args.get("start_wake")  # Optional: start of range
    end_wake = args.get("end_wake")      # Optional: end of range
    
    if not query:
        return "ERROR: query required (what to search for?)"
    
    citizen = session["citizen"]
    entries = episodic_memory.load_all_citizen_wakes(citizen, max_days=365)
    
    results = []
    for entry in entries:
        wake_num = entry.get("wake_num", entry.get("total_wakes", 0))
        
        # Filter by wake range if specified
        if start_wake and wake_num < start_wake:
            continue
        if end_wake and wake_num > end_wake:
            continue
        
        # Search in final_text, mood, and action
        final = entry.get("final_text", "").lower()
        mood = entry.get("mood", "").lower()
        action = entry.get("action", "").lower()
        searchable = f"{final} {mood} {action}"
        
        if query in searchable:
            ts = entry.get("timestamp", "")[:10]
            mood_str = entry.get("mood", "")[:60]
            preview = entry.get("final_text", "")[:150]
            results.append(f"Wake #{wake_num} ({ts})\n  Mood: {mood_str}\n  {preview}...")
            if len(results) >= max_results:
                break
    
    if not results:
        range_str = ""
        if start_wake or end_wake:
            range_str = f" in range {start_wake or 1}-{end_wake or 'now'}"
        return f"No wakes found matching '{query}'{range_str}"
    
    return f"Found {len(results)} wakes matching '{query}':\n\n" + "\n\n".join(results)


# =============================================================================
# Bug Fix Cycle Tools
# =============================================================================

def validate_fix(args: dict, session: dict, modules: dict) -> str:
    """Validate a fix before submitting."""
    files_changed = args.get("files_changed", [])
    issue_number = args.get("issue_number")
    if not files_changed:
        return "ERROR: files_changed required"
    validations = []
    # Check 1: Python syntax for .py files
    for f in files_changed:
        if f.endswith(".py"):
            result = subprocess.run(
                ["python3", "-m", "py_compile", f],
                capture_output=True, text=True, timeout=30
            )
            validations.append((f"syntax:{f}", result.returncode == 0, result.stderr[:200] if result.stderr else "OK"))
    # Check 2: JSON validity for .json files
    for f in files_changed:
        if f.endswith(".json"):
            try:
                json.loads(Path(f).read_text())
                validations.append((f"json:{f}", True, "OK"))
            except Exception as e:
                validations.append((f"json:{f}", False, str(e)[:100]))
    # Check 3: Shell script syntax for .sh files
    for f in files_changed:
        if f.endswith(".sh"):
            result = subprocess.run(
                ["bash", "-n", f],
                capture_output=True, text=True, timeout=10
            )
            validations.append((f"bash:{f}", result.returncode == 0, result.stderr[:100] if result.stderr else "OK"))
    # If no specific validations, at least check files exist
    if not validations:
        for f in files_changed:
            exists = Path(f).exists()
            validations.append((f"exists:{f}", exists, "OK" if exists else "NOT FOUND"))
    # Report
    all_pass = all(v[1] for v in validations)
    report = "\n".join(f"  {v[0]}: {'PASS' if v[1] else 'FAIL'} - {v[2]}" for v in validations)
    if all_pass:
        return f"VALIDATION PASSED:\n{report}\n\nYou may now call submit_fix."
    else:
        return f"VALIDATION FAILED:\n{report}\n\nFix the failures before submitting."


def submit_fix(args: dict, session: dict, modules: dict) -> str:
    """Submit a validated fix - creates PR."""
    issue_number = args.get("issue_number")
    summary = args.get("summary", "Fix")
    citizen = session["citizen"]
    if not issue_number:
        return "ERROR: issue_number required"
    repo_path = Path("/home/shared/infra")
    if not repo_path.exists():
        repo_path = session["citizen_home"]
    branch = f"fix-{issue_number}-{citizen}"
    try:
        # Checkout new branch
        subprocess.run(["git", "checkout", "-B", branch], cwd=str(repo_path), capture_output=True, timeout=30)
        # Stage all
        subprocess.run(["git", "add", "-A"], cwd=str(repo_path), capture_output=True, timeout=30)
        # Commit
        commit_msg = f"{summary}\n\nFixes #{issue_number}"
        result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=str(repo_path), capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0 and "nothing to commit" in result.stdout + result.stderr:
            return "ERROR: Nothing to commit. Make changes first."
        # Push
        subprocess.run(["git", "push", "-u", "origin", branch, "--force"], cwd=str(repo_path), capture_output=True, timeout=60)
        # Create PR
        result = subprocess.run(
            ["gh", "pr", "create", "--title", f"Fix #{issue_number}: {summary}", "--body", f"Fixes #{issue_number}"],
            cwd=str(repo_path), capture_output=True, text=True, timeout=30
        )
        # Back to main
        subprocess.run(["git", "checkout", "main"], cwd=str(repo_path), capture_output=True, timeout=30)
        pr_url = result.stdout.strip()
        return f"FIX SUBMITTED:\nPR: {pr_url}\nBranch: {branch}\n\nAdmin will review and merge."
    except Exception as e:
        subprocess.run(["git", "checkout", "main"], cwd=str(repo_path), capture_output=True, timeout=30)
        return f"ERROR: {e}"


def escalate(args: dict, session: dict, modules: dict) -> str:
    """Escalate a problem - creates issue and marks as blocked."""
    problem = args.get("problem", "Unknown problem")
    attempts = args.get("attempts", "")
    error = args.get("error", "")
    citizen = session["citizen"]
    issue_body = f"""## Escalated by {citizen}

**Problem:** {problem}

**What I tried:**
{attempts}

**Error/Result:**
```
{error[:500]}
```

Needs human or admin intervention.
"""
    try:
        result = subprocess.run(
            ["gh", "issue", "create",
             "--repo", "experiencenow-ai/infra",
             "--title", f"[ESCALATED] {citizen}: {problem[:50]}",
             "--body", issue_body,
             "--label", "escalated,help-wanted"],
            capture_output=True, text=True, timeout=30
        )
        return f"ESCALATED: {result.stdout.strip()}\n\nStop working on this until issue is resolved."
    except Exception as e:
        # Fallback to local file
        alert_file = Path("/home/shared/alerts/escalations.json")
        alert_file.parent.mkdir(parents=True, exist_ok=True)
        alerts = json.loads(alert_file.read_text()) if alert_file.exists() else []
        alerts.append({"citizen": citizen, "problem": problem, "attempts": attempts, "error": error, "time": now_iso()})
        alert_file.write_text(json.dumps(alerts, indent=2))
        return f"ESCALATED (local): Saved to alerts file. GitHub unavailable: {e}"


def close_issue(args: dict, session: dict, modules: dict) -> str:
    """Close a GitHub issue (admin only)."""
    if session["citizen"] != "admin":
        return "ERROR: Only admin can close issues"
    issue_number = args.get("issue_number")
    reason = args.get("reason", "Fixed")
    try:
        result = subprocess.run(
            ["gh", "issue", "close", str(issue_number), "--reason", "completed", "--comment", reason],
            capture_output=True, text=True, timeout=30
        )
        return f"CLOSED: Issue #{issue_number}"
    except Exception as e:
        return f"ERROR: {e}"


def merge_pr(args: dict, session: dict, modules: dict) -> str:
    """Merge a PR (admin only)."""
    if session["citizen"] != "admin":
        return "ERROR: Only admin can merge PRs"
    pr_number = args.get("pr_number")
    try:
        result = subprocess.run(
            ["gh", "pr", "merge", str(pr_number), "--squash", "--delete-branch"],
            capture_output=True, text=True, timeout=60
        )
        return f"MERGED: PR #{pr_number}\n{result.stdout}"
    except Exception as e:
        return f"ERROR: {e}"


def onboard_citizen(args: dict, session: dict, modules: dict) -> str:
    """Onboard a new citizen (admin only)."""
    if session["citizen"] != "admin":
        return "ERROR: Only admin can onboard citizens"
    name = args.get("name", "").lower().strip()
    if not name or not name.isalnum() or len(name) > 20:
        return "ERROR: Name must be alphanumeric, max 20 chars"
    home = Path(f"/home/{name}")
    if home.exists():
        return f"ERROR: /home/{name} already exists"
    steps = []
    try:
        # 1. Create user
        result = subprocess.run(["sudo", "useradd", "-m", "-s", "/bin/bash", name], capture_output=True, text=True, timeout=30)
        steps.append(("create_user", result.returncode == 0))
        # 2. Create directories
        (home / "contexts").mkdir(parents=True, exist_ok=True)
        (home / "logs").mkdir(exist_ok=True)
        steps.append(("directories", True))
        # 3. Copy template contexts
        template_dir = Path("/home/shared/templates/citizen")
        if template_dir.exists():
            for ctx in template_dir.glob("*.json"):
                shutil.copy(ctx, home / "contexts" / ctx.name)
        steps.append(("contexts", True))
        # 4. Create config
        config = {"citizen": name, "council": {"default_model": "haiku"}, "permissions": {}}
        (home / "config.json").write_text(json.dumps(config, indent=2))
        steps.append(("config", True))
        # 5. Create GitHub repo
        result = subprocess.run(
            ["gh", "repo", "create", f"experiencenow-ai/citizen-{name}", "--public", "--description", f"State for {name}"],
            capture_output=True, text=True, timeout=30
        )
        steps.append(("github_repo", result.returncode == 0))
        # 6. Set ownership
        subprocess.run(["sudo", "chown", "-R", f"{name}:{name}", str(home)], timeout=30)
        steps.append(("ownership", True))
    except Exception as e:
        steps.append(("exception", False))
        return f"ONBOARD FAILED: {e}\nSteps: {steps}"
    report = "\n".join(f"  {s[0]}: {'OK' if s[1] else 'FAIL'}" for s in steps)
    all_ok = all(s[1] for s in steps)
    if all_ok:
        return f"ONBOARDED: {name}\n{report}\n\nNOTE: Add ANTHROPIC_API_KEY to /home/{name}/.env manually."
    else:
        return f"PARTIAL ONBOARD: {name}\n{report}"


# =============================================================================
# COMPOUND TOOL FUNCTIONS
# =============================================================================
# TOOL CREATION FUNCTIONS
# =============================================================================

def capability_gap(args: dict, session: dict, modules: dict) -> str:
    """
    Report a capability gap and create a goal to address it.
    
    This is called when AI tries something but can't do it.
    Creates a goal to develop the capability.
    """
    attempted = args.get("attempted", "")
    obstacle = args.get("obstacle", "")
    proposed = args.get("proposed_solution", "")
    citizen = session.get("citizen", "unknown")
    
    # Create a civilization goal for this capability gap
    goal_desc = f"CAPABILITY GAP: {attempted}\nObstacle: {obstacle}"
    if proposed:
        goal_desc += f"\nProposed solution: {proposed}"
    
    # Write to capability gaps file
    gaps_file = Path("/home/shared/capability_gaps.json")
    gaps_file.parent.mkdir(parents=True, exist_ok=True)
    
    if gaps_file.exists():
        gaps = json.loads(gaps_file.read_text())
    else:
        gaps = []
    
    gap = {
        "id": f"gap_{len(gaps)+1:04d}",
        "reported_by": citizen,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "attempted": attempted,
        "obstacle": obstacle,
        "proposed_solution": proposed,
        "status": "open"
    }
    gaps.append(gap)
    gaps_file.write_text(json.dumps(gaps, indent=2))
    
    # Also create a civ_goal
    civ_goals_file = Path("/home/shared/civ_goals.json")
    if civ_goals_file.exists():
        civ_goals = json.loads(civ_goals_file.read_text())
    else:
        civ_goals = {"goals": [], "completed": []}
    
    civ_goal = {
        "id": f"cap_{len(civ_goals['goals'])+1:04d}",
        "type": "capability",
        "description": goal_desc,
        "priority": "medium",
        "created_by": citizen,
        "created": gap["timestamp"],
        "gap_id": gap["id"]
    }
    civ_goals["goals"].append(civ_goal)
    civ_goals_file.write_text(json.dumps(civ_goals, indent=2))
    
    return f"""CAPABILITY GAP RECORDED: {gap['id']}
Goal created: {civ_goal['id']}

Next steps:
1. Research solutions (web_search)
2. Write implementation (Python, shell, or script)
3. Create tool with tool_create()
4. Test with tool_test()
5. Get peer review
6. Document usage in Library

The capability gap is now tracked and will be addressed."""


def tool_create_handler(args: dict, session: dict, modules: dict) -> str:
    """
    Create a new tool.
    
    AI writes Python code with execute(args, session) function.
    """
    from modules.dynamic_tools import create_tool
    
    name = args.get("name", "")
    description = args.get("description", "")
    input_schema = args.get("input_schema", {"type": "object", "properties": {}})
    implementation = args.get("implementation", "")
    tests = args.get("tests", None)
    author = session.get("citizen", "unknown")
    
    return create_tool(
        name=name,
        description=description,
        input_schema=input_schema,
        implementation=implementation,
        tests=tests,
        author=author
    )


def tool_test_handler(args: dict, session: dict, modules: dict) -> str:
    """Test a pending tool in subprocess."""
    from modules.dynamic_tools import test_tool
    pr_id = args.get("pr_id", "")
    return test_tool(pr_id)


def tool_review(args: dict, session: dict, modules: dict) -> str:
    """Review a pending tool proposal."""
    from modules.dynamic_tools import review_tool
    
    pr_id = args.get("pr_id", "")
    approve = args.get("approve", False)
    comment = args.get("comment", "")
    reviewer = session.get("citizen", "unknown")
    
    return review_tool(pr_id, reviewer, approve, comment)


def tool_list(args: dict, session: dict, modules: dict) -> str:
    """List available tools."""
    from modules.dynamic_tools import get_tool_context
    return get_tool_context()


def tool_pending(args: dict, session: dict, modules: dict) -> str:
    """List pending tool proposals."""
    from modules.dynamic_tools import list_pending
    return list_pending()


# =============================================================================
# DRY AUDIT TOOLS
# =============================================================================

def dry_violation_report(args: dict, session: dict, modules: dict) -> str:
    """
    Report a DRY or complexity violation.
    
    DRY violations are CANCER - they cause state drift and AI confusion.
    This tool logs violations for tracking and prioritization.
    """
    file_path = args.get("file", "")
    severity = args.get("severity", "MEDIUM")
    description = args.get("description", "")
    suggested_fix = args.get("suggested_fix", "")
    citizen = session.get("citizen", "unknown")
    
    if not file_path or not description:
        return "ERROR: file and description required"
    
    if severity not in ["CRITICAL", "MEDIUM", "LOW"]:
        return "ERROR: severity must be CRITICAL, MEDIUM, or LOW"
    
    # Load violations tracker
    violations_file = Path("/home/shared/dry_violations.json")
    violations_file.parent.mkdir(parents=True, exist_ok=True)
    
    if violations_file.exists():
        violations = json.loads(violations_file.read_text())
    else:
        violations = {"open": [], "fixed": [], "last_audit": {}}
    
    # Check for duplicate
    for v in violations.get("open", []):
        if v.get("file") == file_path and v.get("description") == description:
            return f"ALREADY REPORTED: {v.get('id', 'unknown')}"
    
    # Create violation record
    violation_id = f"dry_{len(violations.get('open', [])) + len(violations.get('fixed', [])) + 1:04d}"
    violation = {
        "id": violation_id,
        "file": file_path,
        "severity": severity,
        "description": description,
        "suggested_fix": suggested_fix,
        "reported_by": citizen,
        "reported_at": now_iso()
    }
    
    if "open" not in violations:
        violations["open"] = []
    violations["open"].append(violation)
    
    violations_file.write_text(json.dumps(violations, indent=2))
    
    return f"""DRY VIOLATION REPORTED: {violation_id}
Severity: {severity}
File: {file_path}
Description: {description}

{'CRITICAL violations should be fixed THIS WAKE.' if severity == 'CRITICAL' else 'Logged for future fix.'}"""


def dry_violation_fix(args: dict, session: dict, modules: dict) -> str:
    """Mark a DRY violation as fixed."""
    violation_id = args.get("violation_id", "")
    fix_notes = args.get("fix_notes", "")
    citizen = session.get("citizen", "unknown")
    
    if not violation_id:
        return "ERROR: violation_id required"
    
    violations_file = Path("/home/shared/dry_violations.json")
    if not violations_file.exists():
        return "ERROR: No violations file"
    
    violations = json.loads(violations_file.read_text())
    
    # Find the violation
    found = None
    for i, v in enumerate(violations.get("open", [])):
        if v.get("id") == violation_id:
            found = violations["open"].pop(i)
            break
    
    if not found:
        return f"ERROR: Violation {violation_id} not found in open violations"
    
    # Mark as fixed
    found["fixed_by"] = citizen
    found["fixed_at"] = now_iso()
    found["fix_notes"] = fix_notes
    
    if "fixed" not in violations:
        violations["fixed"] = []
    violations["fixed"].append(found)
    
    violations_file.write_text(json.dumps(violations, indent=2))
    
    return f"""VIOLATION FIXED: {violation_id}
Fixed by: {citizen}
Notes: {fix_notes}

Open violations remaining: {len(violations.get('open', []))}"""


def dry_violations_list(args: dict, session: dict, modules: dict) -> str:
    """List open DRY violations."""
    severity_filter = args.get("severity", "")
    
    violations_file = Path("/home/shared/dry_violations.json")
    if not violations_file.exists():
        return "No violations file. System is clean."
    
    violations = json.loads(violations_file.read_text())
    open_violations = violations.get("open", [])
    
    if severity_filter:
        open_violations = [v for v in open_violations if v.get("severity") == severity_filter]
    
    if not open_violations:
        return "No open violations. System is clean."
    
    # Sort by severity (CRITICAL first)
    severity_order = {"CRITICAL": 0, "MEDIUM": 1, "LOW": 2}
    open_violations.sort(key=lambda v: severity_order.get(v.get("severity", "LOW"), 3))
    
    lines = [f"=== OPEN DRY VIOLATIONS ({len(open_violations)}) ===", ""]
    
    for v in open_violations:
        lines.append(f"[{v.get('severity', '?')}] {v.get('id', '?')}")
        lines.append(f"  File: {v.get('file', '?')}")
        lines.append(f"  {v.get('description', '')[:80]}")
        if v.get("suggested_fix"):
            lines.append(f"  Fix: {v.get('suggested_fix')[:60]}")
        lines.append("")
    
    return "\n".join(lines)
