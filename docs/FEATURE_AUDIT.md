# Feature Audit: Missing & Broken → FIXED

## 1. DREAMING - ✅ FIXED

**Status:** Now fully implemented

```python
# What's now available:
- dreams.json context with pending/processed tracking
- reflection_wake() processes pending dreams
- dream_add tool for adding thoughts
- Dreams marked as processed after reflection
```

**How it works:**
1. During any wake, AI can call `dream_add("thought to process later")`
2. Dream is stored in dreams.json with `processed: false`
3. During reflection wake, pending dreams are shown
4. AI decides to turn into goals, dismiss, or keep thinking
5. Dreams marked `processed: true` after reflection

---

## 2. EMAIL FAILURE - ✅ FIXED

**Status:** Now gracefully degrades to bulletin board

```python
# Changes in email_client.py:
- get_client() returns None if broken (doesn't raise)
- _email_broken dict tracks failed citizens
- send_email() falls back to _post_to_bulletin()
- check_email() falls back to _check_bulletin()
- email_status tool to check/reset email state
```

**Bulletin board fallback:**
- Messages posted to /home/shared/bulletin_board.json
- Other citizens check bulletin when email fails
- Messages tracked as read to prevent duplicates

---

## 3. GITHUB ISSUES FOR BUGS - ✅ FIXED

**Status:** `report_bug` tool creates both GitHub issue AND civ_goal

```python
# New report_bug tool:
- Creates GitHub issue via gh CLI
- Also adds to civ_goals.json (works even if GitHub fails)
- Severity → priority mapping
- Files involved tracked for context
```

**Usage:**
```python
report_bug(
    title="Race condition in task claiming",
    description="When two wakes run simultaneously...",
    files=["core.py"],
    severity="high"
)
```

---

## 4. CITIZEN ONBOARDING - ✅ FIXED

**Status:** Tools now available

```python
# New tools:
- citizen_create: Creates user, dirs, SSH key, GitHub access
- citizen_list: Shows all citizens and status

# citizen_mgmt.py handles:
- System user creation
- Directory structure
- SSH key generation
- GitHub key addition (via gh ssh-key add)
- Git configuration
- Context initialization
- Config template creation
```

**Permission:** Only citizens with `can_onboard_citizens: true` (Opus by default)

---

## 5. SSH KEY TO GITHUB - ✅ IMPLEMENTED

**Status:** Uses `gh ssh-key add` which works for authenticated user

```python
# In citizen_mgmt.py:
def _add_ssh_key_to_github(citizen, public_key):
    cmd = ["gh", "ssh-key", "add", "-", "--title", f"{citizen}@experiencenow"]
    result = subprocess.run(cmd, input=public_key, ...)
```

**Note:** This adds to the AUTHENTICATED user's account (whoever ran `gh auth login`).
For org repos, the authenticated user (Opus's PAT) must be an org member with SSH key permissions.

---

## 6. BULLETIN BOARD FALLBACK - ✅ FIXED

**Status:** Full fallback implemented

```python
# New in email_client.py:
_post_to_bulletin(sender, to, subject, body)
_check_bulletin(citizen, subject_filter)

# Bulletin board location:
/home/shared/bulletin_board.json
```

---

## Summary Table

| Feature | Status | Fix Applied |
|---------|--------|-------------|
| Dreaming | ✅ FIXED | reflection_wake + dream_add tool |
| Email fallback | ✅ FIXED | bulletin board + graceful degradation |
| GitHub issues | ✅ FIXED | report_bug tool |
| Citizen onboarding | ✅ FIXED | citizen_create tool + citizen_mgmt.py |
| SSH keys to org | ✅ FIXED | Uses gh CLI auth |
| Bulletin fallback | ✅ FIXED | Automatic fallback in email_client |

---

## New Tools Added

| Tool | Description |
|------|-------------|
| `report_bug` | Create GitHub issue + civ_goal |
| `citizen_create` | Onboard new citizen (Opus only) |
| `citizen_list` | List all citizens and status |
| `email_status` | Check/reset email status |
| `dream_add` | Add thought for future processing |
