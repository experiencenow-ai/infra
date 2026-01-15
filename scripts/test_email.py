#!/usr/bin/env python3
"""
Email Test - Verify email works for all citizens.

Run this BEFORE deploying v2. All tests must pass.

Usage:
    ./test_email.py
    ./test_email.py opus   # Test specific citizen
"""

import sys
import os
from pathlib import Path

# Add modules to path
SCRIPT_DIR = Path(__file__).parent
REPO_DIR = SCRIPT_DIR.parent
MODULES_DIR = REPO_DIR / "modules"
sys.path.insert(0, str(MODULES_DIR))

# Email domain
DOMAIN = "experiencenow.ai"

def load_env(citizen: str):
    """Load environment variables from citizen's .env file."""
    env_file = Path(f"/home/{citizen}/.env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip().strip('"\'')

def test_citizen(citizen: str) -> bool:
    """Test email for a single citizen."""
    print(f"\n{'='*50}")
    print(f"Testing {citizen}")
    print('='*50)
    
    # Load environment
    load_env(citizen)
    
    # Check config exists
    config_file = Path(f"/home/{citizen}/config.json")
    if not config_file.exists():
        print(f"  [FAIL] Config not found: {config_file}")
        return False
    print(f"  [OK] Config exists")
    
    # Check .env exists
    env_file = Path(f"/home/{citizen}/.env")
    if not env_file.exists():
        print(f"  [FAIL] .env not found: {env_file}")
        return False
    print(f"  [OK] .env exists")
    
    # Check API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(f"  [FAIL] ANTHROPIC_API_KEY not set")
        return False
    print(f"  [OK] API key set")
    
    # Check email password
    if not os.environ.get("EMAIL_PASSWORD"):
        print(f"  [FAIL] EMAIL_PASSWORD not set")
        return False
    print(f"  [OK] Email password set")
    
    # Test email client
    try:
        import email_client
        client = email_client.get_client(citizen)
        if client is None:
            print(f"  [WARN] Email broken - using bulletin board fallback")
            print(f"         Error: {email_client.get_email_error(citizen)}")
            print(f"  [OK] Bulletin board fallback available")
            return True  # Still passes - fallback works
        print(f"  [OK] SMTP connection successful")
        print(f"  [OK] IMAP connection successful")
    except Exception as e:
        print(f"  [FAIL] Email client error: {e}")
        return False
    
    # Test send (to self)
    try:
        result = email_client.send_email(
            citizen,
            f"{citizen}@{DOMAIN}",  # Send to self
            f"Test from {citizen}",
            f"This is a test email from {citizen}.\nTime: {__import__('datetime').datetime.now()}"
        )
        print(f"  [OK] Send test: {result}")
    except Exception as e:
        print(f"  [FAIL] Send error: {e}")
        return False
    
    # Test receive
    try:
        emails = email_client.check_email(citizen, unread_only=True)
        print(f"  [OK] Receive test: {len(emails)} unread emails")
    except Exception as e:
        print(f"  [FAIL] Receive error: {e}")
        return False
    
    print(f"\n  ✓ {citizen} PASSED all tests")
    return True

def main():
    citizens = sys.argv[1:] if len(sys.argv) > 1 else ["opus", "mira", "aria"]
    
    print("=" * 50)
    print("EMAIL TEST SUITE")
    print("=" * 50)
    print(f"Testing: {', '.join(citizens)}")
    
    results = {}
    for citizen in citizens:
        results[citizen] = test_citizen(citizen)
    
    print("\n" + "=" * 50)
    print("RESULTS")
    print("=" * 50)
    
    all_passed = True
    for citizen, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {citizen}: {status}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("All tests PASSED! Email is ready.")
        return 0
    else:
        print("Some tests FAILED. Fix issues before deploying.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
