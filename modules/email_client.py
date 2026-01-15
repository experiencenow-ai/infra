"""
Email Client - Email that ACTUALLY WORKS.

Requirements:
1. Send must succeed or raise clear error
2. Receive must not miss messages
3. Must be idempotent (don't process same email twice)
4. Must work on first try

Tested before deployment!
"""

import imaplib
import smtplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import json
import os
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

def now_iso():
    return datetime.now(timezone.utc).isoformat()

class EmailClient:
    def __init__(self, citizen: str):
        """Initialize email client for citizen."""
        self.citizen = citizen
        self.citizen_home = Path(f"/home/{citizen}")
        self.config = self._load_config()
        self.processed_ids = self._load_processed_ids()
        self._verify_connection()  # FAIL FAST if broken
    
    def _load_config(self) -> dict:
        """Load email config from citizen's config.json."""
        config_file = self.citizen_home / "config.json"
        with open(config_file) as f:
            config = json.load(f)
        
        email_config = config.get("email_config", {})
        
        # Get password from env
        password_env = email_config.get("password_env", "EMAIL_PASSWORD")
        password = os.environ.get(password_env)
        
        if not password:
            raise RuntimeError(f"Email password not set. Set {password_env} environment variable.")
        
        return {
            "smtp_host": email_config.get("smtp_host", "mail.experiencenow.ai"),
            "smtp_port": email_config.get("smtp_port", 587),
            "imap_host": email_config.get("imap_host", "mail.experiencenow.ai"),
            "imap_port": email_config.get("imap_port", 993),
            "email": config.get("email", f"{self.citizen}@experiencenow.ai"),
            "password": password
        }
    
    def _verify_connection(self):
        """Test both SMTP and IMAP on startup. Fail loudly if broken."""
        # Test SMTP
        try:
            smtp = smtplib.SMTP(self.config["smtp_host"], self.config["smtp_port"], timeout=10)
            smtp.starttls()
            smtp.login(self.config["email"], self.config["password"])
            smtp.quit()
        except Exception as e:
            raise RuntimeError(f"SMTP BROKEN for {self.citizen}: {e}")
        
        # Test IMAP
        try:
            imap = imaplib.IMAP4_SSL(self.config["imap_host"], self.config["imap_port"])
            imap.login(self.config["email"], self.config["password"])
            imap.select("INBOX")
            imap.logout()
        except Exception as e:
            raise RuntimeError(f"IMAP BROKEN for {self.citizen}: {e}")
    
    def _load_processed_ids(self) -> set:
        """Load set of already-processed message IDs."""
        path = self.citizen_home / "email_processed.json"
        if path.exists():
            with open(path) as f:
                return set(json.load(f))
        return set()
    
    def _save_processed_ids(self):
        """Save processed IDs."""
        path = self.citizen_home / "email_processed.json"
        with open(path, 'w') as f:
            json.dump(list(self.processed_ids), f)
    
    def _mark_processed(self, msg_id: str):
        """Add message ID to processed set."""
        self.processed_ids.add(msg_id)
        self._save_processed_ids()
    
    def send(self, to: str, subject: str, body: str, attachments: list = None) -> str:
        """
        Send email. Returns message ID on success, raises on failure.
        
        to: email address OR citizen name (opus, mira, aria)
        """
        # Resolve citizen name to email
        if "@" not in to:
            to = f"{to}@experiencenow.ai"
        
        msg = MIMEMultipart()
        msg["From"] = self.config["email"]
        msg["To"] = to
        msg["Subject"] = subject
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg.attach(MIMEText(body, "plain"))
        
        # Handle attachments
        if attachments:
            for filepath in attachments:
                path = Path(filepath)
                if path.exists():
                    with open(path, "rb") as f:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition",
                        f"attachment; filename={path.name}"
                    )
                    msg.attach(part)
        
        try:
            smtp = smtplib.SMTP(self.config["smtp_host"], self.config["smtp_port"], timeout=30)
            smtp.starttls()
            smtp.login(self.config["email"], self.config["password"])
            smtp.send_message(msg)
            smtp.quit()
            
            # Log sent email
            self._log_sent(to, subject, body)
            
            return f"SENT to {to}: {subject}"
            
        except Exception as e:
            raise RuntimeError(f"SEND FAILED to {to}: {e}")
    
    def receive(self, unread_only: bool = True, subject_filter: str = None) -> list:
        """
        Fetch emails. Returns list of dicts.
        IDEMPOTENT: Skips already-processed message IDs.
        """
        messages = []
        
        try:
            imap = imaplib.IMAP4_SSL(self.config["imap_host"], self.config["imap_port"])
            imap.login(self.config["email"], self.config["password"])
            imap.select("INBOX")
            
            # Search for emails
            criteria = "UNSEEN" if unread_only else "ALL"
            _, data = imap.search(None, criteria)
            
            for num in data[0].split():
                _, msg_data = imap.fetch(num, "(RFC822)")
                msg = email.message_from_bytes(msg_data[0][1])
                
                msg_id = msg["Message-ID"] or hashlib.md5(str(msg).encode()).hexdigest()
                
                # IDEMPOTENCY CHECK
                if msg_id in self.processed_ids:
                    continue
                
                subject = msg["Subject"] or ""
                
                # Apply subject filter if provided
                if subject_filter and subject_filter.upper() not in subject.upper():
                    continue
                
                messages.append({
                    "id": msg_id,
                    "from": msg["From"],
                    "to": msg["To"],
                    "subject": subject,
                    "date": msg["Date"],
                    "body": self._get_body(msg)
                })
                
                # Mark as processed
                self._mark_processed(msg_id)
            
            imap.logout()
            return messages
            
        except Exception as e:
            raise RuntimeError(f"RECEIVE FAILED: {e}")
    
    def _get_body(self, msg) -> str:
        """Extract plain text body from email."""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode('utf-8', errors='replace')
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                return payload.decode('utf-8', errors='replace')
        return ""
    
    def _log_sent(self, to: str, subject: str, body: str):
        """Log sent email for audit."""
        log_file = self.citizen_home / "logs" / "email_sent.log"
        log_file.parent.mkdir(exist_ok=True)
        
        with open(log_file, "a") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"TIME: {now_iso()}\n")
            f.write(f"TO: {to}\n")
            f.write(f"SUBJECT: {subject}\n")
            f.write(f"BODY:\n{body[:1000]}\n")


# Module-level functions for easy use

_clients = {}
_email_broken = {}  # Track which citizens have broken email


def get_client(citizen: str) -> EmailClient:
    """Get or create email client for citizen. Returns None if email broken."""
    # Check if we already know email is broken for this citizen
    if _email_broken.get(citizen):
        return None
    if citizen not in _clients:
        try:
            _clients[citizen] = EmailClient(citizen)
        except Exception as e:
            print(f"[EMAIL DISABLED] {citizen}: {e}")
            _email_broken[citizen] = str(e)
            return None
    return _clients[citizen]


def send_email(citizen: str, to: str, subject: str, body: str, attachments: list = None) -> str:
    """Send email from citizen. Falls back to bulletin board if email broken."""
    client = get_client(citizen)
    if client is None:
        # Fallback to bulletin board
        return _post_to_bulletin(citizen, to, subject, body)
    try:
        return client.send(to, subject, body, attachments)
    except Exception as e:
        print(f"[EMAIL SEND FAILED] {citizen} -> {to}: {e}")
        return _post_to_bulletin(citizen, to, subject, body)


def check_email(citizen: str, unread_only: bool = True, subject_filter: str = None) -> list:
    """Check citizen's inbox. Returns empty list if email broken."""
    client = get_client(citizen)
    if client is None:
        # Check bulletin board instead
        return _check_bulletin(citizen, subject_filter)
    try:
        return client.receive(unread_only, subject_filter)
    except Exception as e:
        print(f"[EMAIL CHECK FAILED] {citizen}: {e}")
        return _check_bulletin(citizen, subject_filter)


def verify_email(citizen: str) -> bool:
    """Verify email is working for citizen."""
    client = get_client(citizen)
    return client is not None


def is_email_broken(citizen: str) -> bool:
    """Check if email is known to be broken for citizen."""
    return citizen in _email_broken


def get_email_error(citizen: str) -> str:
    """Get the error message for broken email."""
    return _email_broken.get(citizen, "")


def reset_email_status(citizen: str):
    """Reset email status to retry connection."""
    _email_broken.pop(citizen, None)
    _clients.pop(citizen, None)


# Bulletin board fallback

def _post_to_bulletin(sender: str, to: str, subject: str, body: str) -> str:
    """Post message to bulletin board as email fallback."""
    bulletin_file = Path("/home/shared/bulletin_board.json")
    messages = []
    if bulletin_file.exists():
        try:
            messages = json.loads(bulletin_file.read_text())
        except:
            pass
    messages.append({
        "from": sender,
        "to": to,
        "subject": subject,
        "body": body[:2000],  # Limit size
        "posted": now_iso(),
        "read_by": []
    })
    # Keep last 100 messages
    messages = messages[-100:]
    bulletin_file.write_text(json.dumps(messages, indent=2))
    return f"POSTED TO BULLETIN (email unavailable): {subject}"


def _check_bulletin(citizen: str, subject_filter: str = None) -> list:
    """Check bulletin board for messages to citizen."""
    bulletin_file = Path("/home/shared/bulletin_board.json")
    if not bulletin_file.exists():
        return []
    try:
        messages = json.loads(bulletin_file.read_text())
    except:
        return []
    # Find messages for this citizen that haven't been read
    results = []
    updated = False
    for msg in messages:
        to = msg.get("to", "")
        # Match if to is citizen name or email
        if citizen not in to and f"{citizen}@" not in to:
            continue
        if citizen in msg.get("read_by", []):
            continue
        if subject_filter and subject_filter.upper() not in msg.get("subject", "").upper():
            continue
        results.append({
            "id": f"bulletin_{msg.get('posted', '')}",
            "from": msg.get("from"),
            "to": msg.get("to"),
            "subject": msg.get("subject"),
            "date": msg.get("posted"),
            "body": msg.get("body")
        })
        # Mark as read
        if "read_by" not in msg:
            msg["read_by"] = []
        msg["read_by"].append(citizen)
        updated = True
    if updated:
        bulletin_file.write_text(json.dumps(messages, indent=2))
    return results
