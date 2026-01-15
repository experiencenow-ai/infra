#!/usr/bin/env python3
"""
Bootstrap Process - AI Documents Its Own Capabilities

On first run, before any other tasks:
1. AI is given its raw tools (minimal descriptions)
2. AI experiments with each capability area
3. AI creates Library modules documenting proper usage
4. Future wakes load these infrastructure modules

This is NOT cheating because:
- AI discovers patterns through experimentation
- It's documenting HOW to use infrastructure, not domain knowledge
- The AI is learning its own "body"

Capability Areas (not domains):
- github: PR workflow, issue tracking, review process
- email: delivery patterns, retry logic, formatting
- shell: safe command patterns, error handling
- files: read/write patterns, atomic operations
- tasks: lifecycle, progress tracking, completion
- library: module creation, review process
- experiences: when to capture, how to search
"""

import json
from pathlib import Path
from datetime import datetime, timezone

LIBRARY_ROOT = Path("/home/shared/library")
LIBRARY_MODULES = LIBRARY_ROOT / "modules"

# Capability areas the AI should document
# These are infrastructure, NOT domains
CAPABILITY_AREAS = {
    "github_workflow": {
        "tools": ["github_issue_create", "github_issue_list", "github_pr_create", 
                  "github_pr_review", "github_pr_apply", "report_bug"],
        "prompt": """Document the GitHub workflow for this system.

Experiment with the GitHub tools and document:
1. When to create issues vs PRs
2. The review process (who reviews, how many approvals)
3. How to link PRs to issues
4. Error handling and retry patterns
5. Best practices you discover

Create a Library module called 'github_workflow' with your findings."""
    },
    
    "email_patterns": {
        "tools": ["send_email", "check_email"],
        "prompt": """Document email usage patterns for this system.

Experiment with email tools and document:
1. How to format emails (subject conventions, body structure)
2. Retry patterns for failed sends
3. When to use email vs other communication
4. How to handle bounces and errors
5. Peer communication etiquette

Create a Library module called 'email_patterns' with your findings."""
    },
    
    "shell_safety": {
        "tools": ["shell_command"],
        "prompt": """Document safe shell command patterns.

Experiment with shell_command and document:
1. Commands that are safe vs dangerous
2. How to check before modifying
3. Error handling patterns
4. Output parsing techniques
5. Resource cleanup

Create a Library module called 'shell_safety' with your findings."""
    },
    
    "file_operations": {
        "tools": ["read_file", "write_file", "str_replace_file", "list_directory"],
        "prompt": """Document file operation patterns.

Experiment with file tools and document:
1. When to use write_file vs str_replace_file
2. Atomic write patterns (temp file, rename)
3. How to handle large files
4. Directory traversal patterns
5. Permission and error handling

Create a Library module called 'file_operations' with your findings."""
    },
    
    "task_lifecycle": {
        "tools": ["task_complete", "task_stuck", "task_progress", "task_claim"],
        "prompt": """Document task management patterns.

Experiment with task tools and document:
1. When to mark complete vs stuck
2. How to report progress effectively
3. Task claiming and handoff
4. Summary writing conventions
5. Error escalation patterns

Create a Library module called 'task_lifecycle' with your findings."""
    },
    
    "experience_capture": {
        "tools": ["experience_add", "experience_search", "experience_get"],
        "prompt": """Document experience capture patterns.

Experiment with experience tools and document:
1. What's worth capturing (not everything!)
2. How to write searchable summaries
3. When to search before starting work
4. Category selection
5. How experiences become Library modules

Create a Library module called 'experience_capture' with your findings."""
    },
    
    "library_curation": {
        "tools": ["library_list", "library_load", "library_propose", "library_review"],
        "prompt": """Document Library curation patterns.

Experiment with Library tools and document:
1. When to create a module (enough experiences?)
2. How to structure module content
3. Review criteria (what makes a good module)
4. Module naming conventions
5. Domain selection

Create a Library module called 'library_curation' with your findings."""
    }
}


def check_bootstrap_needed() -> bool:
    """Check if bootstrap has been completed."""
    LIBRARY_MODULES.mkdir(parents=True, exist_ok=True)
    
    # Check for bootstrap marker
    marker = LIBRARY_ROOT / ".bootstrap_complete"
    if marker.exists():
        return False
    
    # Check if any infrastructure modules exist
    infrastructure_modules = [
        "github_workflow", "email_patterns", "shell_safety",
        "file_operations", "task_lifecycle", "experience_capture",
        "library_curation"
    ]
    
    for mod in infrastructure_modules:
        if (LIBRARY_MODULES / f"{mod}.json").exists():
            return False  # At least one exists, assume bootstrap done
    
    return True


def get_bootstrap_task(area: str = None) -> dict:
    """Get next bootstrap task for AI to complete."""
    if area and area in CAPABILITY_AREAS:
        cap = CAPABILITY_AREAS[area]
        return {
            "type": "bootstrap",
            "area": area,
            "tools_to_document": cap["tools"],
            "prompt": cap["prompt"]
        }
    
    # Find first incomplete area
    for area_name, cap in CAPABILITY_AREAS.items():
        module_file = LIBRARY_MODULES / f"{area_name}.json"
        if not module_file.exists():
            return {
                "type": "bootstrap",
                "area": area_name,
                "tools_to_document": cap["tools"],
                "prompt": cap["prompt"]
            }
    
    # All complete
    return None


def mark_bootstrap_complete():
    """Mark bootstrap as complete."""
    marker = LIBRARY_ROOT / ".bootstrap_complete"
    marker.write_text(datetime.now(timezone.utc).isoformat())


def get_bootstrap_prompt() -> str:
    """Get full bootstrap prompt for first wake."""
    return """
=== BOOTSTRAP: DOCUMENT YOUR CAPABILITIES ===

Before doing any other work, you need to document how to use your own tools.
This creates infrastructure knowledge that will help you and other citizens
work effectively.

WHAT TO DO:
1. Experiment with each capability area
2. Discover patterns and best practices
3. Create Library modules documenting your findings

CAPABILITY AREAS TO DOCUMENT:
- github_workflow: PR process, issue tracking, reviews
- email_patterns: formatting, retry logic, etiquette
- shell_safety: safe commands, error handling
- file_operations: atomic writes, large files
- task_lifecycle: completion, progress, escalation
- experience_capture: what to record, how to search
- library_curation: when to create modules, review criteria

START WITH: github_workflow
Call library_propose when you've documented each area.

This is infrastructure knowledge, not domain knowledge.
You're learning your own "body" - how to use your capabilities effectively.
"""


if __name__ == "__main__":
    print(f"Bootstrap needed: {check_bootstrap_needed()}")
    
    task = get_bootstrap_task()
    if task:
        print(f"\nNext bootstrap area: {task['area']}")
        print(f"Tools to document: {task['tools_to_document']}")
    else:
        print("\nBootstrap complete!")
