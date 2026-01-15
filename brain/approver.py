#!/usr/bin/env python3
"""
Goal Approver Daemon - Opus, every 10 min or triggered

Responsibilities:
1. Review goal proposals from Sonnet → approve/reject/modify
2. Answer complex emails that Sonnet escalated
3. Make high-level strategic decisions

Only runs when there's work to do (proposals or complex emails).

Cost: ~$0.50 per run, but only when needed
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
from brain.memory import get_brain_memory

MODEL = "claude-opus-4-5-20251101"
TEMPERATURE = 0.4

INBOX_FILE = BRAIN_DIR / "email_inbox.json"
STATE_FILE = SCRIPT_DIR / "state.json"
IDENTITY_FILE = SCRIPT_DIR / "IDENTITY.md"

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except:
            pass
    return {"total_wakes": 0}

def load_identity() -> str:
    if IDENTITY_FILE.exists():
        return IDENTITY_FILE.read_text()
    return "You are Mira."

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

def run_approver():
    """Main approver iteration."""
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
    
    # Load state
    state = load_state()
    wake = state.get("total_wakes", 0)
    goals_db = get_goals_db(str(BRAIN_DIR))
    inbox = load_inbox()
    identity = load_identity()
    
    # Check if there's work to do
    proposals = goals_db.get_proposals("pending")
    complex_emails = [e for e in inbox.get("emails", [])
                     if e.get("status") == "pending"
                     and e.get("triage", {}).get("classification") == "needs_opus"]
    
    if not proposals and not complex_emails:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Approver: Nothing to do")
        return
    
    client = anthropic.Anthropic(api_key=api_key)
    
    # Get current goals for context
    goals = goals_db.get_goals()
    
    # Build prompt
    prompt = f"""{identity}

You are in GOAL APPROVER mode (Opus at temp 0.4). You make strategic decisions.

Current wake: {wake}
Time: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}

=== CURRENT GOALS ({len(goals)}) ===
{json.dumps(goals[:5], indent=2) if goals else "No goals"}

=== GOAL PROPOSALS NEEDING APPROVAL ({len(proposals)}) ===
{json.dumps(proposals, indent=2) if proposals else "None"}

=== COMPLEX EMAILS NEEDING YOUR RESPONSE ({len(complex_emails)}) ===
{json.dumps([{{"id": e["id"], "from": e["from"], "subject": e["subject"], "body": e["body"][:500], "summary": e["triage"]["summary"]}} for e in complex_emails[:3]], indent=2) if complex_emails else "None"}

---

Your decisions:

1. GOAL PROPOSALS: For each proposal, decide:
   - approve: Good goal, create it
   - reject: Not a good goal, explain why
   - modify: Good idea but needs changes

2. COMPLEX EMAILS: Draft thoughtful responses

3. STRATEGIC: Any high-level observations or goal adjustments?

Respond as JSON:
{{
  "proposal_decisions": [
    {{
      "proposal_id": "...",
      "decision": "approve|reject|modify",
      "priority_override": null or 1-10,
      "modifications": "..." or null,
      "reason": "..."
    }}
  ],
  "email_responses": [
    {{"email_id": "...", "response": "..."}}
  ],
  "strategic_notes": "Any high-level thoughts",
  "new_goal": {{
    "description": "...",
    "why": "...",
    "success_criteria": [...],
    "priority": 1-10
  }} or null
}}"""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
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
        print(f"Approver error: {e}")
        return
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Approver run")
    
    # Process proposal decisions
    for pd in result.get("proposal_decisions", []):
        proposal_id = pd.get("proposal_id")
        decision = pd.get("decision")
        
        if decision == "approve":
            goal = goals_db.approve_proposal(
                proposal_id, wake,
                priority_override=pd.get("priority_override"),
                modifications=pd.get("modifications")
            )
            if goal:
                print(f"  Approved: {goal['description'][:40]}...")
                # Create initial plan for new goal
                goals_db.set_plan(
                    goal["id"],
                    steps=["Analyze requirements", "Plan approach", "Execute", "Verify success"],
                    reasoning="Initial plan - will be refined by planner",
                    wake=wake
                )
        elif decision == "reject":
            if goals_db.reject_proposal(proposal_id, wake, pd.get("reason", "")):
                print(f"  Rejected proposal: {proposal_id} - {pd.get('reason', '')[:30]}")
        elif decision == "modify":
            # For now, treat as reject with suggestion to repropose
            goals_db.reject_proposal(proposal_id, wake, 
                f"Needs modification: {pd.get('modifications', '')}. Please repropose.")
            print(f"  Modification requested: {proposal_id}")
    
    # Process email responses
    for er in result.get("email_responses", []):
        email_id = er.get("email_id")
        response_text = er.get("response")
        if email_id and response_text:
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
                            email["responded_by"] = "opus"
                            email["responded_at"] = datetime.now(timezone.utc).isoformat()
                            print(f"  Responded (Opus): {email['subject'][:30]}...")
                    except Exception as e:
                        print(f"  Email send error: {e}")
    
    save_inbox(inbox)
    
    # Create new goal if specified
    if result.get("new_goal"):
        ng = result["new_goal"]
        goal = goals_db.add_goal(
            description=ng["description"],
            why=ng["why"],
            success_criteria=ng.get("success_criteria", []),
            priority=ng.get("priority", 5),
            wake=wake,
            source="opus_direct"
        )
        print(f"  New goal (direct): {ng['description'][:40]}...")
    
    # Log strategic notes
    if result.get("strategic_notes"):
        print(f"  Strategic: {result['strategic_notes'][:100]}...")
    
    # Store to opus memory
    try:
        brain = get_brain_memory(str(SCRIPT_DIR))
        if result.get("strategic_notes"):
            brain.add(f"STRATEGIC: {result['strategic_notes']}", "approver", "opus", wake)
        for pd in result.get("proposal_decisions", []):
            decision = pd.get("decision", "")
            reason = pd.get("reason", "")
            brain.add(f"DECISION on proposal: {decision} - {reason}", "approver", "opus", wake)
    except Exception as e:
        print(f"  Memory store error: {e}")
    
    print(f"  Cost: ~$0.50")

if __name__ == "__main__":
    run_approver()
