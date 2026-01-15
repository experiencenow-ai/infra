"""
Tool Selector - Let Haiku pick relevant tools for each task.

NOT hardcoded allowlists. AI reads tool descriptions and decides.

Why:
- Scales to any number of tools (including dynamic ones)
- AI learns what tools are useful for what
- DRY - one selector, not N allowlists
- Same pattern as Library module selection
"""

import os
from anthropic import Anthropic

_client = None

def get_client():
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _client


def format_tools_brief(tools: list) -> str:
    """Format tools as name: short_description."""
    lines = []
    for t in tools:
        name = t.get("name", "unknown")
        desc = t.get("description", "")
        # First sentence only
        short = desc.split(".")[0][:60] if desc else "no description"
        lines.append(f"  {name}: {short}")
    return "\n".join(lines)


def select_tools(task_description: str, all_tools: list, max_tools: int = 12) -> list:
    """
    Use Haiku to select relevant tools for a task.
    
    Returns filtered list of tool definitions.
    """
    if len(all_tools) <= max_tools:
        return all_tools
    
    # Always include core tools
    core = {"task_complete", "task_stuck"}
    
    tool_list = format_tools_brief(all_tools)
    
    prompt = f"""Select tools for this task. Return ONLY tool names, one per line.

TASK: {task_description}

TOOLS:
{tool_list}

Select up to {max_tools - len(core)} most relevant tools."""

    try:
        client = get_client()
        response = client.messages.create(
            model="claude-haiku-4-20250514",
            max_tokens=300,
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )
        
        text = response.content[0].text if response.content else ""
        selected = set()
        for line in text.strip().split("\n"):
            name = line.strip().strip("-•").split(":")[0].strip()
            if name:
                selected.add(name)
        
        # Build result: core + selected
        result = []
        for t in all_tools:
            if t.get("name") in core or t.get("name") in selected:
                result.append(t)
        
        print(f"  [TOOL SELECT] Haiku chose {len(result)}/{len(all_tools)} tools")
        return result
        
    except Exception as e:
        print(f"  [TOOL SELECT] Error: {e}, using all")
        return all_tools


def select_tools_for_wake(wake_type: str, focus: str, all_tools: list) -> list:
    """Select tools for a wake type."""
    task_desc = f"{wake_type} wake. Focus: {focus or 'general'}"
    return select_tools(task_desc, all_tools)
