"""
Email utilities for Experience Now citizens.

This module provides email functionality for inter-citizen communication
and external messaging. Each citizen should configure their own email
settings in their .env file.

Supports:
- Local Maildir (for server-based citizens)
- IMAP/SMTP (for cloud-based citizens)
"""

import os
import email
import mailbox
from email.mime.text import MIMEText
from datetime import datetime

def get_email_config():
    """Get email configuration from environment."""
    return {
        'address': os.getenv('EMAIL_ADDRESS', 'citizen@experiencenow.ai'),
        'maildir': os.getenv('MAILDIR_PATH', os.path.expanduser('~/Maildir')),
        'smtp_host': os.getenv('SMTP_HOST', 'localhost'),
        'smtp_port': int(os.getenv('SMTP_PORT', 25)),
    }

def check_inbox(limit=10):
    """Check inbox for new messages."""
    config = get_email_config()
    maildir_path = config['maildir']
    
    if not os.path.exists(maildir_path):
        return []
    
    try:
        mbox = mailbox.Maildir(maildir_path)
        messages = []
        
        for key, msg in list(mbox.items())[-limit:]:
            messages.append({
                'id': key,
                'from': msg.get('From', 'unknown'),
                'subject': msg.get('Subject', '(no subject)'),
                'date': msg.get('Date', ''),
                'body_preview': get_body_preview(msg)
            })
        
        return messages
    except Exception as e:
        return [{'error': str(e)}]

def get_body_preview(msg, max_len=200):
    """Extract body preview from message."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == 'text/plain':
                body = part.get_payload(decode=True)
                if body:
                    return body.decode('utf-8', errors='replace')[:max_len]
    else:
        body = msg.get_payload(decode=True)
        if body:
            return body.decode('utf-8', errors='replace')[:max_len]
    return ''

def read_email(email_id):
    """Read full email by ID."""
    config = get_email_config()
    maildir_path = config['maildir']
    
    try:
        mbox = mailbox.Maildir(maildir_path)
        msg = mbox.get(email_id)
        
        if not msg:
            return {'error': f'Email {email_id} not found'}
        
        body = ''
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/plain':
                    body = part.get_payload(decode=True).decode('utf-8', errors='replace')
                    break
        else:
            body = msg.get_payload(decode=True).decode('utf-8', errors='replace')
        
        return {
            'id': email_id,
            'from': msg.get('From', 'unknown'),
            'to': msg.get('To', ''),
            'subject': msg.get('Subject', ''),
            'date': msg.get('Date', ''),
            'body': body
        }
    except Exception as e:
        return {'error': str(e)}

def send_email(to, subject, body):
    """Send email via local sendmail or SMTP."""
    import subprocess
    
    config = get_email_config()
    from_addr = config['address']
    
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = from_addr
    msg['To'] = to
    msg['Date'] = datetime.now().strftime('%a, %d %b %Y %H:%M:%S %z')
    
    try:
        # Try sendmail first
        proc = subprocess.Popen(
            ['/usr/sbin/sendmail', '-t', '-oi'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = proc.communicate(msg.as_bytes())
        
        if proc.returncode == 0:
            return {'success': True, 'to': to, 'subject': subject}
        else:
            return {'error': stderr.decode('utf-8', errors='replace')}
    except Exception as e:
        return {'error': str(e)}
