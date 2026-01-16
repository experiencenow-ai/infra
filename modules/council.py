"""
Council - Multi-model orchestration.

Each citizen can have a "council" of models with different roles.
This module handles calling the API and processing responses.

COST OPTIMIZATION:
- Simple tasks → Haiku (fast, cheap)
- Medium tasks → Sonnet (default)
- Complex tasks → Council config (may be Opus)

SAFETY:
- Cost circuit breaker: max $0.50/wake
- Tool call deduplication: warn after 3 identical calls
- Auto-fail on max iterations: prevent infinite loops

Haiku routes the task before execution.
"""

import json
import os
import hashlib
import anthropic
from datetime import datetime, timezone
from typing import Optional, List
import daily_log
import episodic_memory

# Model costs per 1M tokens
COSTS = {
    "claude-opus-4-5-20251101": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-5-20250929": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.25, "output": 1.25}
}

# Safety limits
MAX_COST_PER_WAKE = 2.00  # $2.00 max per wake
MAX_TOOL_REPEATS = 3      # Warn after this many identical calls
MAX_ITERATIONS = 30       # Max tool use loops

# Complexity routing
ROUTER_MODEL = "claude-haiku-4-5-20251001"
SIMPLE_MODEL = "claude-haiku-4-5-20251001"
MEDIUM_MODEL = "claude-sonnet-4-5-20250929"

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def get_client():
    """Get Anthropic client."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return anthropic.Anthropic(api_key=api_key)

def tool_call_hash(name: str, args: dict) -> str:
    """Generate hash for tool call deduplication."""
    content = f"{name}:{json.dumps(args, sort_keys=True)}"
    return hashlib.md5(content.encode()).hexdigest()[:12]


def route_complexity(task_desc: str, session: dict) -> str:
    """
    Use Haiku to determine task complexity.
    Returns: "simple", "medium", or "complex"
    
    Cost: ~100 tokens × $0.25/1M = $0.000025 per routing decision
    """
    # Allow forcing complexity via session
    if session.get("force_complex"):
        return "complex"
    
    prompt = f"""Classify this task's complexity. Reply with ONE word: simple, medium, or complex.

simple = Single status check, file read, simple question, greeting
medium = Multi-step task, moderate code changes, standard operations
complex = Architecture, debugging hard problems, creative/philosophical work, multi-file changes, deep analysis, important decisions

Err on the side of "complex" for anything non-trivial.

TASK: {task_desc[:500]}

Complexity:"""

    try:
        client = get_client()
        response = client.messages.create(
            model=ROUTER_MODEL,
            max_tokens=10,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Track (minimal) cost
        session["tokens_used"] = session.get("tokens_used", 0) + \
            response.usage.input_tokens + response.usage.output_tokens
        session["cost"] = session.get("cost", 0) + \
            (response.usage.input_tokens * COSTS[ROUTER_MODEL]["input"] + 
             response.usage.output_tokens * COSTS[ROUTER_MODEL]["output"]) / 1_000_000
        
        result = response.content[0].text.strip().lower()
        
        if "simple" in result:
            return "simple"
        elif "complex" in result:
            return "complex"
        else:
            return "medium"
            
    except Exception as e:
        print(f"[ROUTER] Error: {e}, defaulting to medium")
        return "medium"


def select_model(complexity: str, council_config: list) -> tuple[str, float]:
    """Select model based on complexity."""
    if complexity == "simple":
        return SIMPLE_MODEL, 0.3
    elif complexity == "medium":
        return MEDIUM_MODEL, 0.5
    else:
        # Complex - use council config (primary model)
        primary = council_config[0] if council_config else {"model": MEDIUM_MODEL, "temperature": 0.7}
        return primary.get("model", MEDIUM_MODEL), primary.get("temperature", 0.7)

def process(user_input: str, session: dict, council_config: list, modules: dict) -> dict:
    """
    Process user input through the council.
    
    COST OPTIMIZATION:
    1. Haiku routes complexity (~$0.00003)
    2. Simple → Haiku
    3. Medium → Sonnet  
    4. Complex → Council config (may be Opus)
    
    TOOL FILTERING:
    Each wake type gets limited tools to reduce confusion.
    """
    if not council_config:
        council_config = [{"model": "claude-sonnet-4-5-20250929", "role": "primary", "temperature": 0.7}]
    
    client = get_client()
    context_mgr = modules.get("context_mgr")
    tools_mod = modules.get("tools")
    
    # Get wake type and focus for tool selection
    wake_type = session.get("wake_type", "TASK")
    focus = session.get("focus", "general")
    
    # Use Haiku to select relevant tools (not hardcoded allowlists)
    try:
        from modules.tool_selector import select_tools_for_wake
    except ImportError:
        try:
            from tool_selector import select_tools_for_wake
        except ImportError:
            # Fallback: use all tools
            select_tools_for_wake = lambda wt, f, tools: tools
    
    all_tools = tools_mod.get_all_tools()  # Core + dynamic tools
    filtered_tools = select_tools_for_wake(wake_type, focus, all_tools)
    print(f"  [TOOLS] Haiku selected {len(filtered_tools)}/{len(all_tools)} tools for {wake_type}")
    
    # Route complexity FIRST (cheap Haiku call)
    complexity = route_complexity(user_input, session)
    model, temperature = select_model(complexity, council_config)
    print(f"  [ROUTE] {complexity} → {model.split('-')[1]}")  # e.g., "haiku" or "opus"
    
    # Build context from loaded contexts
    base_prompt = context_mgr.compose_prompt(session, "task_execution")
    
    # CRITICAL: Inject episodic memory - this is the "soul"
    # Without this, the AI has semantic knowledge but no experiential texture
    try:
        episodic_ctx = episodic_memory.build_episodic_context(session["citizen"], max_tokens=12000)
        if episodic_ctx and len(episodic_ctx) > 100:
            base_prompt += f"\n\n{episodic_ctx}"
            print(f"  [EPISODIC] Injected {len(episodic_ctx)} chars of experiential memory")
    except Exception as e:
        print(f"  [EPISODIC] Failed to load: {e}")
    
    # Add recent actions for awareness
    action_log = modules.get("action_log")
    if action_log:
        recent = action_log.get_recent_actions_text(session["citizen"], hours=24)
        base_prompt += f"\n\n=== RECENT ACTIONS (already done, don't repeat) ===\n{recent}"
    
    # Add memory context if available
    memory_mod = modules.get("memory")
    if memory_mod:
        mem_context = memory_mod.get_context_for_wake(session["citizen"], session)
        if mem_context and len(mem_context) > 20:
            base_prompt += f"\n\n=== MEMORY ===\n{mem_context}"
    
    # Clean up old Library content from working context before adding new
    # This prevents expertise accumulation across turns
    working = session.get("contexts", {}).get("working", {})
    if working.get("messages"):
        cleaned_messages = []
        for msg in working["messages"]:
            content = msg.get("content", "")
            # Skip messages that are primarily Library injections
            if "=== RELEVANT KNOWLEDGE (from Library) ===" in content:
                # Keep only the task part, strip Library content
                if "=== CURRENT INPUT ===" in content:
                    # Extract just the input part
                    parts = content.split("=== CURRENT INPUT ===")
                    if len(parts) > 1:
                        msg = dict(msg)  # Copy
                        msg["content"] = "=== CURRENT INPUT ===" + parts[-1]
                        cleaned_messages.append(msg)
                    continue
            cleaned_messages.append(msg)
        working["messages"] = cleaned_messages
    
    # Search Library for relevant modules (keyword search - no hardcoding)
    # NOTE: This is re-done each turn, so expertise is fresh not accumulated
    try:
        from modules.library_search import search_and_inject, search_library, extract_keywords
        
        keywords = extract_keywords(user_input)
        candidates = search_library(keywords, max_results=5)  # Get more candidates
        
        if candidates:
            # With many modules, don't auto-inject - show candidates and let AI decide
            if len(candidates) <= 2:
                # Few matches - safe to auto-inject
                search_result = search_and_inject(user_input, max_modules=2)
                if search_result.get("context_injection"):
                    base_prompt += search_result["context_injection"]
                    session["loaded_modules"] = search_result["modules_found"]
                    print(f"  [LIBRARY] Auto-loaded: {search_result['modules_found']}")
            else:
                # Many matches - show summaries, let AI pick with library_load
                base_prompt += "\n\n=== LIBRARY MODULES AVAILABLE ==="
                base_prompt += f"\nFound {len(candidates)} potentially relevant modules:"
                for c in candidates[:5]:
                    base_prompt += f"\n  - {c['name']}: {c.get('description', '')[:80]}"
                base_prompt += "\n\nUse library_load(name) if you need one of these."
                print(f"  [LIBRARY] {len(candidates)} candidates - AI will choose")
        else:
            # No modules found
            base_prompt += f"\n\n(No Library modules match. Use web_search if uncertain.)"
            print(f"  [LIBRARY] No modules found for: {keywords[:5]}")
    except Exception as e:
        print(f"  [LIBRARY] Search failed: {e}")
    
    # Search past experiences
    try:
        from modules.experiences import search_experiences
        exp_results = search_experiences(session["citizen"], user_input, limit=3)
        if exp_results:
            base_prompt += "\n\n=== YOUR PAST LEARNINGS ==="
            for exp in exp_results:
                base_prompt += f"\n- {exp.get('summary', '')[:150]}"
            print(f"  [EXP] Found {len(exp_results)} related experiences")
    except:
        pass
    
    # Add guidance
    base_prompt += """

=== GUIDANCE ===
If you're UNCERTAIN about the best approach:
1. Use web_search to research (e.g., "C sorting algorithms comparison")
2. After learning something useful, capture it with library_create
3. Check experience_search for your past learnings

If stuck, use task_stuck."""
    
    # Build messages
    messages = []
    
    # Add working context history
    working = session.get("contexts", {}).get("working", {})
    for msg in working.get("messages", [])[-20:]:
        messages.append(msg)
    
    # Add user input
    messages.append({"role": "user", "content": f"{base_prompt}\n\n=== CURRENT INPUT ===\n{user_input}"})
    
    # Model already selected by router above
    
    # Tool use loop with safety guards
    iteration = 0
    final_response = None
    tool_call_counts = {}  # Track repeated calls: {hash: count}
    tool_calls_log = []    # Accumulate tool calls for daily log
    cost_warning_given = False
    
    while iteration < MAX_ITERATIONS:
        iteration += 1
        
        # SAFETY: At 80% cost, tell AI to wrap up
        if not cost_warning_given and session.get("cost", 0) > MAX_COST_PER_WAKE * 0.8:
            print(f"  [COST WARNING] At 80% - telling AI to wrap up")
            cost_warning_given = True
            # Inject wrap-up instruction
            messages.append({
                "role": "user", 
                "content": "[SYSTEM: You are at 80% of your cost budget for this wake. Please wrap up your current work and provide your conclusions. Do not start new investigations.]"
            })
        
        # SAFETY: Hard stop at limit
        if session.get("cost", 0) > MAX_COST_PER_WAKE:
            print(f"  [COST LIMIT] ${session['cost']:.2f} - hard stop")
            break
        
        try:
            response = client.messages.create(
                model=model,
                max_tokens=8192,
                temperature=temperature,
                messages=messages,
                tools=filtered_tools  # Use filtered tools, not all tools
            )
        except Exception as e:
            return {"error": str(e), "text": f"API Error: {e}"}
        
        # Track costs
        costs = COSTS.get(model, COSTS["claude-sonnet-4-5-20250929"])
        session["tokens_used"] = session.get("tokens_used", 0) + \
            response.usage.input_tokens + response.usage.output_tokens
        session["cost"] = session.get("cost", 0) + \
            (response.usage.input_tokens * costs["input"] + 
             response.usage.output_tokens * costs["output"]) / 1_000_000
        
        # Process response
        text_parts = []
        tool_uses = []
        
        for block in response.content:
            if hasattr(block, "text") and block.text:
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)
        
        # Store assistant response
        messages.append({"role": "assistant", "content": response.content})
        
        # If no tool use, we're done
        if response.stop_reason == "end_turn" or not tool_uses:
            final_response = {
                "text": "\n".join(text_parts),
                "model": model,
                "tokens": session["tokens_used"],
                "cost": session["cost"]
            }
            break
        
        # Execute tools with deduplication tracking
        tool_results = []
        for tool in tool_uses:
            # SAFETY: Track repeated identical calls
            call_hash = tool_call_hash(tool.name, tool.input)
            tool_call_counts[call_hash] = tool_call_counts.get(call_hash, 0) + 1
            
            if tool_call_counts[call_hash] > MAX_TOOL_REPEATS:
                print(f"  [WARN] {tool.name} called {tool_call_counts[call_hash]} times with same args")
                result = f"WARNING: You've called {tool.name} {tool_call_counts[call_hash]} times with identical arguments. This suggests a loop. Try a different approach or use task_stuck if you're blocked."
            else:
                print(f"  [TOOL] {tool.name}: {tool.input}")
                result = tools_mod.execute_tool(
                    tool.name, 
                    tool.input, 
                    session, 
                    modules
                )
                print(f"  [RESULT] {result}")
            
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool.id,
                "content": str(result)
            })
            
            # Log tool call for daily log
            tool_calls_log.append(daily_log.log_tool_call(
                citizen=session["citizen"],
                wake_num=session.get("wake_num", 0),
                tool_name=tool.name,
                tool_args=tool.input,
                result=str(result),
                iteration=iteration
            ))
            
            # Log action (full result for session, truncated only for display)
            session["actions"] = session.get("actions", [])
            session["actions"].append({
                "tool": tool.name,
                "input": tool.input,
                "result": str(result),  # Full result
                "time": now_iso()
            })
            
            # Check for task completion signals
            if "TASK_COMPLETE" in str(result) or "TASK_STUCK" in str(result):
                final_response = {
                    "text": str(result),
                    "model": model,
                    "tokens": session["tokens_used"],
                    "cost": session["cost"],
                    "task_ended": True
                }
                break
        
        if final_response:
            break
        
        # Add tool results for next iteration
        messages.append({"role": "user", "content": tool_results})
    
    # SAFETY: Auto-fail on max iterations (prevents infinite resume loops)
    if not final_response:
        print(f"  [SAFETY] Max iterations ({MAX_ITERATIONS}) reached - auto-failing task")
        # Try to fail the task gracefully
        try:
            stuck_result = tools_mod.execute_tool(
                "task_stuck",
                {"reason": f"Max iterations ({MAX_ITERATIONS}) reached without completing. Likely looping."},
                session,
                modules
            )
            final_response = {
                "text": f"Max iterations reached. Task marked as stuck: {stuck_result}",
                "model": model,
                "tokens": session["tokens_used"],
                "cost": session["cost"],
                "auto_failed": True
            }
        except:
            final_response = {
                "text": f"Max iterations ({MAX_ITERATIONS}) reached",
                "model": model,
                "tokens": session["tokens_used"],
                "cost": session["cost"],
                "auto_failed": True
            }
    
    # Update working context
    if "working" in session.get("contexts", {}):
        context_mgr.add_message(
            session["contexts"]["working"],
            "user",
            user_input
        )
        context_mgr.add_message(
            session["contexts"]["working"],
            "assistant",
            final_response.get("text", "")[:2000]
        )
    
    # CRITICAL: Log complete wake to daily JSONL
    try:
        # Convert messages to serializable format
        serializable_messages = []
        for msg in messages:
            if isinstance(msg, dict):
                if "content" in msg:
                    content = msg["content"]
                    # Handle anthropic API content blocks
                    if hasattr(content, '__iter__') and not isinstance(content, (str, dict)):
                        # Convert content blocks to dicts
                        content_list = []
                        for block in content:
                            if hasattr(block, 'text'):
                                content_list.append({"type": "text", "text": block.text})
                            elif hasattr(block, 'type') and block.type == "tool_use":
                                content_list.append({
                                    "type": "tool_use",
                                    "id": block.id,
                                    "name": block.name,
                                    "input": block.input
                                })
                            elif isinstance(block, dict):
                                content_list.append(block)
                        serializable_messages.append({"role": msg["role"], "content": content_list})
                    else:
                        serializable_messages.append(msg)
                else:
                    serializable_messages.append(msg)
            else:
                serializable_messages.append(str(msg))
        daily_log.log_wake_complete(
            citizen=session["citizen"],
            wake_num=session.get("wake_num", 0),
            session=session,
            messages=serializable_messages,
            tool_calls=tool_calls_log,
            final_response=final_response,
            action=session.get("action", "unknown")
        )
    except Exception as e:
        print(f"  [WARN] Daily log failed: {e}")
    
    return final_response

def simple_query(prompt: str, session: dict, model: str = None, temperature: float = 0.7) -> str:
    """
    Simple one-shot query without tools.
    Used for forgetting, summarization, etc.
    """
    if model is None:
        model = "claude-sonnet-4-5-20250929"
    
    client = get_client()
    
    try:
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Track costs
        costs = COSTS.get(model, COSTS["claude-sonnet-4-5-20250929"])
        session["tokens_used"] = session.get("tokens_used", 0) + \
            response.usage.input_tokens + response.usage.output_tokens
        session["cost"] = session.get("cost", 0) + \
            (response.usage.input_tokens * costs["input"] + 
             response.usage.output_tokens * costs["output"]) / 1_000_000
        
        return response.content[0].text
        
    except Exception as e:
        return f"ERROR: {e}"
