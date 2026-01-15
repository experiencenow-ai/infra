#!/usr/bin/env python3
"""
Planner Daemon - Sonnet, every 1 minute, temp 0.5

Responsibilities:
1. Review goals and current state
2. Update/refine plans for active goals
3. Propose new goals (pending Opus approval)
4. Answer trivial emails from email_inbox.json
5. Decide which emails need Opus

Cost: ~$0.02 × 60 × 24 = ~$28.80/day
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import anthropic
except ImportError:
    os.system("pip install anthropic --break-system-packages --quiet")
    import anthropic

SCRIPT_DIR = Path(__file__).parent.parent
BRAIN_DIR = SCRIPT_DIR / "brain"
sys.path.insert(0, str(SCRIPT_DIR))

from brain.goals import get_goals_db
from brain.task import get_task_db
from brain.memory import get_brain_memory

MODEL = "claude-sonnet-4-5-20250929"
TEMPERATURE = 0.5

INBOX_FILE = BRAIN_DIR / "email_inbox.json"
STATE_FILE = SCRIPT_DIR / "state.json"

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except:
            pass
    return {"total_wakes": 0}

def load_inbox() -> dict:
    if INBOX_FILE.exists():
        try:
            with open(INBOX_FILE) as f:
                return json.load(f)
        except:
            pass
    return {"emails": []}

def save_inbox(data: dict):
    with open(INBOX_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def run_planner():
    """Main planner iteration."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        env_file = SCRIPT_DIR.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text().split('\n'):
                if line.startswith("ANTHROPIC_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"')
    
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set")
        return
    
    client = anthropic.Anthropic(api_key=api_key)
    
    # Load state
    state = load_state()
    wake = state.get("total_wakes", 0)
    goals_db = get_goals_db(str(BRAIN_DIR))
    task_db = get_task_db(str(BRAIN_DIR))
    inbox = load_inbox()
    
    # Build context
    goals = goals_db.get_goals()
    active_plan = goals_db.get_active_plan()
    proposals = goals_db.get_proposals("pending")
    task_state = task_db.format_for_prompt()
    
    # Pending trivial emails
    trivial_emails = [e for e in inbox.get("emails", []) 
                     if e.get("status") == "pending" 
                     and e.get("triage", {}).get("classification") == "trivial"]
    
    # Build prompt
    prompt = f"""You are the PLANNER (Sonnet at temp 0.5). Your job is to plan and organize.

Current wake: {wake}
Time: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}

=== CURRENT STATE ===
{task_state}

=== GOALS ({len(goals)}) ===
{json.dumps(goals[:5], indent=2) if goals else "No goals set"}

=== ACTIVE PLAN ===
{json.dumps(active_plan, indent=2) if active_plan else "No active plan"}

=== PENDING GOAL PROPOSALS ({len(proposals)}) ===
{json.dumps(proposals, indent=2) if proposals else "None"}

=== TRIVIAL EMAILS NEEDING RESPONSE ({len(trivial_emails)}) ===
{json.dumps([{{"id": e["id"], "from": e["from"], "subject": e["subject"], "summary": e["triage"]["summary"], "suggested": e["triage"].get("suggested_response")}} for e in trivial_emails[:3]], indent=2) if trivial_emails else "None"}

---

Your tasks:
1. PLAN REVIEW: Is the current plan still optimal? Should steps be reordered, added, or removed?
2. GOAL PROPOSALS: Should any new goals be proposed? (Will need Opus approval)
3. TRIVIAL EMAILS: Draft responses for trivial emails (I'll send them)
4. PRIORITY: Which goal should be active focus?

Respond as JSON:
{{
  "plan_updates": {{
    "goal_id": "...",
    "action": "none|reorder|add_steps|modify",
    "new_steps": [...] or null,
    "reasoning": "..."
  }},
  "new_goal_proposal": {{
    "description": "...",
    "why": "...",
    "success_criteria": [...],
    "priority": 1-10,
    "reasoning": "..."
  }} or null,
  "email_responses": [
    {{"email_id": "...", "response": "..."}}
  ],
  "set_active_goal": "goal_id" or null,
  "observations": "Any important observations about current state"
}}"""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            temperature=TEMPERATURE,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        result = json.loads(text.strip())
    except Exception as e:
        print(f"Planner error: {e}")
        return
    
    # Process results
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Planner run")
    
    # Plan updates
    if result.get("plan_updates", {}).get("action") not in [None, "none"]:
        pu = result["plan_updates"]
        goal_id = pu.get("goal_id")
        if goal_id and pu.get("new_steps"):
            goals_db.update_plan(goal_id, wake, new_steps=pu["new_steps"], reasoning=pu.get("reasoning"))
            print(f"  Updated plan for {goal_id}")
    
    # New goal proposal
    if result.get("new_goal_proposal"):
        ng = result["new_goal_proposal"]
        proposal = goals_db.propose_goal(
            description=ng["description"],
            why=ng["why"],
            success_criteria=ng.get("success_criteria", []),
            priority=ng.get("priority", 5),
            wake=wake,
            reasoning=ng.get("reasoning", "")
        )
        print(f"  Proposed goal: {ng['description'][:40]}...")
    
    # Email responses
    for er in result.get("email_responses", []):
        email_id = er.get("email_id")
        response_text = er.get("response")
        if email_id and response_text:
            # Find email and send response
            for email in inbox.get("emails", []):
                if email["id"] == email_id and email["status"] == "pending":
                    try:
                        from email_utils import send_email
                        subject = email.get("subject", "")
                        if not subject.startswith("Re:"):
                            subject = f"Re: {subject}"
                        if send_email(email["from"], subject, response_text):
                            email["status"] = "responded"
                            email["response"] = response_text
                            email["responded_at"] = datetime.now(timezone.utc).isoformat()
                            print(f"  Responded to: {email['subject'][:30]}...")
                    except Exception as e:
                        print(f"  Email send error: {e}")
    
    save_inbox(inbox)
    
    # Set active goal
    if result.get("set_active_goal"):
        goals_db.set_active_goal(result["set_active_goal"])
        print(f"  Set active goal: {result['set_active_goal']}")
    
    # Log observations
    if result.get("observations"):
        print(f"  Observations: {result['observations'][:100]}...")
    
    # Store to sonnet memory
    try:
        brain = get_brain_memory(str(SCRIPT_DIR))
        if result.get("observations"):
            brain.add(f"PLANNER OBSERVATION: {result['observations']}", "planner", "sonnet", wake)
        if result.get("new_goal_proposal"):
            brain.add(f"PROPOSED GOAL: {result['new_goal_proposal'].get('description', '')}", "planner", "sonnet", wake)
    except Exception as e:
        print(f"  Memory store error: {e}")
    
    # Cost estimate
    print(f"  Cost: ~$0.02")

if __name__ == "__main__":
    run_planner()
