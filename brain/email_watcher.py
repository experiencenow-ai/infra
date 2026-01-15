#!/usr/bin/env python3
"""
Email Watcher Daemon - Haiku, every 15 seconds

Scans inbox and triages emails:
- trivial: Can be answered by Sonnet
- needs_opus: Complex, needs Opus judgment
- informational: FYI only, no response needed

Writes to email_inbox.json for other daemons to process.

Cost: ~$0.001 × 4/min × 60 × 24 = ~$5.76/day
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import hashlib

try:
    import anthropic
except ImportError:
    os.system("pip install anthropic --break-system-packages --quiet")
    import anthropic

SCRIPT_DIR = Path(__file__).parent.parent  # Goes up from brain/ to mira/
BRAIN_DIR = SCRIPT_DIR / "brain"

INBOX_FILE = BRAIN_DIR / "email_inbox.json"
PROCESSED_FILE = BRAIN_DIR / "email_processed.json"

MODEL = "claude-haiku-4-5-20251001"

def load_inbox() -> dict:
    if INBOX_FILE.exists():
        try:
            with open(INBOX_FILE) as f:
                return json.load(f)
        except:
            pass
    return {"emails": [], "last_check": None}

def save_inbox(data: dict):
    BRAIN_DIR.mkdir(parents=True, exist_ok=True)
    with open(INBOX_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def load_processed() -> set:
    """Load set of processed email IDs."""
    if PROCESSED_FILE.exists():
        try:
            with open(PROCESSED_FILE) as f:
                data = json.load(f)
                return set(data.get("processed_ids", []))
        except:
            pass
    return set()

def save_processed(ids: set):
    with open(PROCESSED_FILE, 'w') as f:
        json.dump({"processed_ids": list(ids)[-500:]}, f)  # Keep last 500

def check_inbox_raw() -> list:
    """Check inbox using email_utils."""
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        from email_utils import check_inbox
        return check_inbox(max_results=10)
    except Exception as e:
        print(f"Email check error: {e}")
        return []

def triage_email(client, email: dict) -> dict:
    """Use Haiku to triage an email."""
    prompt = f"""Triage this email. Respond with JSON only.

From: {email.get('from', 'unknown')}
Subject: {email.get('subject', 'no subject')}
Body: {email.get('body', '')[:500]}

Classify as:
- "trivial": Simple question, factual, can be answered quickly
- "needs_opus": Complex decision, judgment call, sensitive topic
- "informational": FYI only, no response needed
- "spam": Ignore

Also extract:
- summary: 1 sentence summary
- urgency: low/medium/high
- suggested_response: Brief response if trivial (null otherwise)

JSON format:
{{"classification": "...", "summary": "...", "urgency": "...", "suggested_response": "..." or null}}"""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=500,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text.strip())
    except Exception as e:
        print(f"Triage error: {e}")
        return {
            "classification": "needs_opus",
            "summary": "Failed to triage",
            "urgency": "medium",
            "suggested_response": None
        }

def run_watcher():
    """Main watcher loop iteration."""
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
    
    # Check inbox
    raw_emails = check_inbox_raw()
    if not raw_emails:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] No new emails")
        return
    
    # Load state
    inbox_data = load_inbox()
    processed_ids = load_processed()
    
    # Process new emails
    new_count = 0
    for email in raw_emails:
        # Generate ID
        email_id = hashlib.md5(
            f"{email.get('from', '')}{email.get('subject', '')}{email.get('date', '')}".encode()
        ).hexdigest()[:12]
        
        if email_id in processed_ids:
            continue
        
        # Triage
        triage = triage_email(client, email)
        
        # Add to inbox
        inbox_entry = {
            "id": email_id,
            "from": email.get("from", "unknown"),
            "subject": email.get("subject", "no subject"),
            "body": email.get("body", "")[:1000],
            "date": email.get("date", ""),
            "received_at": datetime.now(timezone.utc).isoformat(),
            "triage": triage,
            "status": "pending",  # pending, responded, ignored
        }
        
        # Remove old entry if exists (update)
        inbox_data["emails"] = [e for e in inbox_data["emails"] if e["id"] != email_id]
        inbox_data["emails"].insert(0, inbox_entry)
        
        processed_ids.add(email_id)
        new_count += 1
        
        # Store to haiku memory
        try:
            sys.path.insert(0, str(SCRIPT_DIR))
            from brain.memory import get_brain_memory
            brain = get_brain_memory(str(SCRIPT_DIR))
            content = f"EMAIL from {email.get('from', 'unknown')}: {triage['summary']} [{triage['classification']}]"
            # Get wake number
            try:
                with open(SCRIPT_DIR / "state.json") as sf:
                    wake = json.load(sf).get("total_wakes", 0)
            except:
                wake = 0
            brain.add(content, "email", "haiku", wake)
        except:
            pass
        
        print(f"  [{triage['classification']}] {email.get('subject', 'no subject')[:40]}")
    
    # Keep only last 50 emails in active inbox
    inbox_data["emails"] = inbox_data["emails"][:50]
    inbox_data["last_check"] = datetime.now(timezone.utc).isoformat()
    
    save_inbox(inbox_data)
    save_processed(processed_ids)
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Processed {new_count} new emails")

if __name__ == "__main__":
    run_watcher()
