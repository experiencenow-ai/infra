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
from modules import daily_log
from modules import episodic_memory

# Model costs per 1M tokens
COSTS = {
    "claude-opus-4-5-20251101": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-5-20250929": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.25, "output": 1.25}
}

# Safety limits
MAX_COST_PER_WAKE = 5.00  # $5.00 max per wake (Opus is 5x more expensive than Sonnet)
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
    """
    # Allow forcing complexity via session
    if session.get("force_complex"):
        return "complex"
    
    prompt = f"""Rate this task. Reply with ONLY one word: simple, medium, or complex.

simple = greetings, status checks, single file reads
medium = standard coding, routine operations  
complex = ANYTHING involving: thinking, analysis, philosophy, debugging, architecture, creative work, opinions, advice, multi-step reasoning, important questions

Default to "complex" if unsure. Most real work is complex.

Task: {task_desc[:300]}

Rating:"""

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
        print(f"  [ROUTER] Haiku says: '{result}'")
        
        if "simple" in result:
            return "simple"
        elif "medium" in result:
            return "medium"
        else:
            # Default to complex for anything unclear
            return "complex"
            
    except Exception as e:
        print(f"[ROUTER] Error: {e}, defaulting to complex")
        return "complex"  # Default to complex on error, not medium


def select_model(complexity: str, council_config: list) -> tuple[str, float]:
    """Select model based on complexity."""
    if complexity == "simple":
        return SIMPLE_MODEL, 0.3
    elif complexity == "medium":
        return MEDIUM_MODEL, 0.5
    else:
        # Complex - use council config (primary model)
        primary = council_config[0] if council_config else {"model": MEDIUM_MODEL, "temperature": 0.7}
        model = primary.get("model", MEDIUM_MODEL)
        print(f"  [MODEL] Council config[0]: {primary}")
        return model, primary.get("temperature", 0.7)


def _process_simple(user_input: str, session: dict, model: str, temperature: float, 
                    tools: list, modules: dict) -> dict:
    """
    Fast path for simple queries. Minimal context, no compression.
    
    Expected cost: ~$0.001 vs $0.30 for full path
    """
    client = get_client()
    tools_mod = modules.get("tools")
    citizen = session.get("citizen", "opus")
    
    # Minimal system prompt - no episodic, no library, no compression
    system_prompt = f"""You are {citizen.title()}, an AI assistant.
Answer briefly and use tools when needed.
Current time: {now_iso()}"""
    
    messages = [{"role": "user", "content": user_input}]
    
    # Single API call (no iteration loop for simple queries)
    try:
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            temperature=temperature,
            system=system_prompt,
            messages=messages,
            tools=tools
        )
        
        input_cost = response.usage.input_tokens * COSTS.get(model, COSTS[SIMPLE_MODEL])["input"] / 1_000_000
        output_cost = response.usage.output_tokens * COSTS.get(model, COSTS[SIMPLE_MODEL])["output"] / 1_000_000
        total_tokens = response.usage.input_tokens + response.usage.output_tokens
        total_cost = input_cost + output_cost
        
        session["tokens_used"] = session.get("tokens_used", 0) + total_tokens
        session["cost"] = session.get("cost", 0) + total_cost
        
    except Exception as e:
        return {"error": str(e), "text": f"API Error: {e}"}
    
    # Process response - handle tools if needed
    text_parts = []
    tool_uses = []
    
    for block in response.content:
        if hasattr(block, "text") and block.text:
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_uses.append(block)
    
    # Execute tools (simple path: one round only)
    tool_results = []
    for tool in tool_uses:
        print(f"  [TOOL] {tool.name}: {str(tool.input)[:60]}")
        try:
            result = tools_mod.execute_tool(tool.name, tool.input, session, modules)
            failed = str(result).startswith("ERROR")
        except Exception as e:
            result = f"ERROR: {e}"
            failed = True
        
        display = str(result)[:100] + "..." if len(str(result)) > 100 else str(result)
        print(f"  [{'FAIL' if failed else 'OK'}] {display}")
        
        tool_results.append({
            "type": "tool_result",
            "tool_use_id": tool.id,
            "content": str(result)
        })
    
    # If tools were used, get final response
    if tool_uses and tool_results:
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})
        
        try:
            final_response = client.messages.create(
                model=model,
                max_tokens=1024,
                temperature=temperature,
                system=system_prompt,
                messages=messages,
                tools=tools
            )
            
            # Update costs
            input_cost = final_response.usage.input_tokens * COSTS.get(model, COSTS[SIMPLE_MODEL])["input"] / 1_000_000
            output_cost = final_response.usage.output_tokens * COSTS.get(model, COSTS[SIMPLE_MODEL])["output"] / 1_000_000
            session["tokens_used"] += final_response.usage.input_tokens + final_response.usage.output_tokens
            session["cost"] += input_cost + output_cost
            
            for block in final_response.content:
                if hasattr(block, "text") and block.text:
                    text_parts.append(block.text)
                    
        except Exception as e:
            text_parts.append(f"(Tool executed, but follow-up failed: {e})")
    
    return {
        "text": "\n".join(text_parts),
        "model": model,
        "tokens": session["tokens_used"],
        "cost": session["cost"]
    }

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
    
    # FAST PATH: Simple queries skip heavy context building
    if complexity == "simple":
        return _process_simple(user_input, session, model, temperature, filtered_tools, modules)
    
    # FULL PATH: Complex/medium queries get full context
    # Build context from loaded contexts
    base_prompt = context_mgr.compose_prompt(session, "task_execution")
    
    # CRITICAL: Inject episodic memory - this is the "soul"
    # Without this, the AI has semantic knowledge but no experiential texture
    try:
        episodic_ctx = episodic_memory.build_episodic_context(session["citizen"], max_tokens=6000)
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
If UNCERTAIN: use web_search, then capture with library_create.
If stuck: use task_stuck."""
    
    # COMPRESS CONTEXT: Apply semantic deduplication + NLP compression
    # Compresses everything EXCEPT user's prompt (which goes in messages separately)
    try:
        from modules.prompt_compressor import compress_prompt
        original_tokens = len(base_prompt) // 4
        base_prompt, comp_stats = compress_prompt(
            base_prompt, 
            target_tokens=20000,  # Soft target, won't truncate
            dedup_threshold=0.85,
            aggressive_compress=True
        )
        reduction = comp_stats.get('reduction_pct', 0)
        if reduction > 5:  # Only log if meaningful reduction
            print(f"  [COMPRESS] {comp_stats['original_tokens']} → {comp_stats['final_tokens']} ({reduction}% off)")
    except Exception as e:
        print(f"  [COMPRESS] Skipped: {e}")
    
    # PROMPT CACHING: Separate static (cacheable) from dynamic content
    # Static: identity, episodic, guidance - doesn't change within a wake
    # Dynamic: user input, tool results - changes each iteration
    static_system = base_prompt  # This is the cacheable part
    
    # Build messages - only dynamic content
    messages = []
    
    # Add working context history (prior conversation turns)
    working = session.get("contexts", {}).get("working", {})
    for msg in working.get("messages", [])[-10:]:  # Reduced from 20
        messages.append(msg)
    
    # Add user input as separate message (not combined with base_prompt!)
    messages.append({"role": "user", "content": user_input})
    
    # Model already selected by router above
    
    # Tool use loop with safety guards
    iteration = 0
    final_response = None
    tool_call_counts = {}  # Track repeated calls: {hash: count}
    tool_calls_log = []    # Accumulate tool calls for daily log
    
    # Build system with cache control
    system_with_cache = [
        {
            "type": "text",
            "text": static_system,
            "cache_control": {"type": "ephemeral"}
        }
    ]
    
    # Track all tool results for final synthesis
    all_tool_results = []
    first_response_text = ""
    actual_api_calls = 0  # Safety counter
    
    while iteration < MAX_ITERATIONS:
        iteration += 1
        actual_api_calls += 1
        
        # SAFETY: Hard limit on API calls
        if actual_api_calls > MAX_ITERATIONS:
            print(f"  [SAFETY] Max API calls reached")
            break
        
        # SAFETY: Cost checks
        if session.get("cost", 0) > MAX_COST_PER_WAKE:
            print(f"  [COST LIMIT] ${session['cost']:.2f} - hard stop")
            break
        
        try:
            # Always use main model with cached context
            # Opus sees errors and can decide how to handle them
            # No Haiku recovery - it lacks context and loops
            response = client.messages.create(
                model=model,
                max_tokens=8192,
                temperature=temperature,
                system=system_with_cache,
                messages=messages,
                tools=filtered_tools
            )
            iter_costs = COSTS.get(model, COSTS["claude-sonnet-4-5-20250929"])
            
            # Cache stats
            cache_read = getattr(response.usage, 'cache_read_input_tokens', 0)
            cache_creation = getattr(response.usage, 'cache_creation_input_tokens', 0)
            total_input = response.usage.input_tokens
            
            if iteration == 1:
                fresh_input = max(0, total_input - cache_read - cache_creation)
                print(f"  [CACHE] Total: {total_input}, Creating: {cache_creation}, Fresh: {fresh_input}")
                input_cost = (
                    fresh_input * iter_costs["input"] +
                    cache_read * iter_costs["input"] * 0.1 +
                    cache_creation * iter_costs["input"] * 1.25
                ) / 1_000_000
            else:
                if cache_read > 0:
                    print(f"  [CACHE HIT] {cache_read} tokens cached")
                # Cached portion at 10%, fresh at full price
                cached_cost = cache_read * iter_costs["input"] * 0.1
                fresh_cost = max(0, total_input - cache_read) * iter_costs["input"]
                input_cost = (cached_cost + fresh_cost) / 1_000_000
        
        except Exception as e:
            return {"error": str(e), "text": f"API Error: {e}"}
        
        # Track costs
        output_cost = response.usage.output_tokens * iter_costs["output"] / 1_000_000
        session["tokens_used"] = session.get("tokens_used", 0) + response.usage.input_tokens + response.usage.output_tokens
        session["cost"] = session.get("cost", 0) + input_cost + output_cost
        
        # Process response
        text_parts = []
        tool_uses = []
        
        for block in response.content:
            if hasattr(block, "text") and block.text:
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)
        
        # Save first response text for final output
        if iteration == 1 and text_parts:
            first_response_text = "\n".join(text_parts)
        
        # Append to messages (needed for proper API flow)
        messages.append({"role": "assistant", "content": response.content})
        
        # If no tool use, we're done
        if response.stop_reason == "end_turn" or not tool_uses:
            response_text = "\n".join(text_parts)
            final_response = {
                "text": first_response_text + "\n\n" + response_text if first_response_text and response_text else (first_response_text or response_text),
                "model": model,
                "tokens": session["tokens_used"],
                "cost": session["cost"]
            }
            break
        
        # Execute tools - STOP ON FIRST ERROR
        tool_results = []
        any_failed = False
        
        for tool in tool_uses:
            # SAFETY: Track repeated identical calls
            call_hash = tool_call_hash(tool.name, tool.input)
            tool_call_counts[call_hash] = tool_call_counts.get(call_hash, 0) + 1
            
            if tool_call_counts[call_hash] > MAX_TOOL_REPEATS:
                print(f"  [WARN] {tool.name} repeated {tool_call_counts[call_hash]}x - loop detected")
                result = "ERROR: Loop detected. Use task_stuck."
                failed = True
            else:
                print(f"  [TOOL] {tool.name}: {str(tool.input)[:80]}")
                try:
                    result = tools_mod.execute_tool(tool.name, tool.input, session, modules)
                    failed = str(result).startswith("ERROR")
                except Exception as e:
                    result = f"ERROR: {e}"
                    failed = True
                
                display = str(result)[:150] + "..." if len(str(result)) > 150 else str(result)
                print(f"  [{'FAIL' if failed else 'OK'}] {display}")
            
            # Track result
            all_tool_results.append({
                "tool": tool.name,
                "args": tool.input,
                "result": str(result),
                "failed": failed
            })
            
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool.id,
                "content": str(result)
            })
            
            # Log
            tool_calls_log.append(daily_log.log_tool_call(
                citizen=session["citizen"],
                wake_num=session.get("wake_num", 0),
                tool_name=tool.name,
                tool_args=tool.input,
                result=str(result),
                iteration=iteration
            ))
            
            session["actions"] = session.get("actions", [])
            session["actions"].append({
                "tool": tool.name,
                "input": tool.input,
                "result": str(result),
                "time": now_iso()
            })
            
            # Check for explicit completion
            if "TASK_COMPLETE" in str(result) or "TASK_STUCK" in str(result):
                final_response = {
                    "text": str(result),
                    "model": model,
                    "tokens": session["tokens_used"],
                    "cost": session["cost"],
                    "task_ended": True
                }
                break
            
            # STOP ON FIRST ERROR - don't waste time on subsequent tools
            if failed:
                any_failed = True
                print(f"  [STOP] Error encountered, skipping remaining {len(tool_uses) - len(tool_results)} tools")
                # Add placeholder results for remaining tools so API is happy
                for remaining_tool in tool_uses[len(tool_results):]:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": remaining_tool.id,
                        "content": "SKIPPED: Previous tool failed"
                    })
                break
        
        if final_response:
            break
        
        # Add tool results for next iteration
        messages.append({"role": "user", "content": tool_results})
        
        # OPTIMIZATION: Skip API call if we can detect completion
        # Terminal tools that indicate "task is done"
        TERMINAL_TOOLS = {"task_complete", "task_stuck", "github_commit", "github_pr_create"}
        last_tool = tool_uses[-1].name if tool_uses else None
        
        # Completion indicators in Opus's response text
        completion_phrases = ["will complete", "this fixes", "should fix", "will fix", 
                             "task complete", "that's all", "done", "finished"]
        text_suggests_done = any(p in first_response_text.lower() for p in completion_phrases)
        
        if not any_failed:
            if last_tool in TERMINAL_TOOLS:
                # Explicitly terminal tool - we're done
                print(f"  [DONE] Terminal tool {last_tool} succeeded")
                final_response = {
                    "text": first_response_text + f"\n\n[Completed via {last_tool}]",
                    "model": model,
                    "tokens": session["tokens_used"],
                    "cost": session["cost"]
                }
                break
            elif text_suggests_done and iteration >= 2:
                # Opus suggested completion and we've done some work
                print(f"  [DONE] All tools succeeded and text suggests completion")
                final_response = {
                    "text": first_response_text + "\n\n[Tools executed successfully]",
                    "model": model,
                    "tokens": session["tokens_used"],
                    "cost": session["cost"]
                }
                break
            else:
                # Need to check with Opus if there's more to do - but use cache
                pass
    
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
