# PAT Permissions & Citizen Safety

## The Problem

Opus went crazy "helping" other AI by overwriting their data. We need:
1. PAT permissions that limit what each citizen can do
2. Code-level guards that prevent cross-citizen writes
3. Clear processes that the AI will actually follow

---

## PAT Strategy

### Option A: Fine-Grained PATs (Recommended)

Each citizen gets their OWN PAT with limited scope:

**Opus PAT** (for infra work):
```
Repository access: 
  - infra: Read/Write
  - protocols: Read/Write  
  - citizen-opus: Read/Write
  - citizen-mira: READ ONLY
  - citizen-aria: READ ONLY
```

**Mira PAT**:
```
Repository access:
  - infra: Read only (can PR, not direct push)
  - protocols: Read/Write
  - citizen-mira: Read/Write
  - citizen-opus: READ ONLY
  - citizen-aria: READ ONLY
```

**Aria PAT**:
```
Repository access:
  - infra: Read only
  - protocols: Read/Write
  - citizen-aria: Read/Write
  - citizen-opus: READ ONLY
  - citizen-mira: READ ONLY
```

### Creating Fine-Grained PAT

1. Go to: GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
2. Generate new token
3. Resource owner: experiencenow-ai
4. Repository access: Only select repositories
5. Select ONLY the repos this citizen needs write access to
6. Permissions:
   - Contents: Read and write (for allowed repos)
   - Pull requests: Read and write
   - Issues: Read and write
   - Metadata: Read

### Option B: Single PAT + Code Guards

If fine-grained PATs are too complex, use ONE org PAT but enforce limits in code.

---

## Code-Level Guards

### 1. citizen_create Permission Check

Already exists in tools.py:
```python
def citizen_create(args, session, modules):
    if session["citizen"] != "opus":
        return "ERROR: Only Opus can create citizens"
```

### 2. Write Path Restrictions

In tools.py, `can_write_path()` should enforce:
```python
def can_write_path(path: Path, session: dict) -> bool:
    citizen = session["citizen"]
    citizen_home = session["citizen_home"]
    
    # Can write to own home
    if str(path).startswith(str(citizen_home)):
        return True
    
    # Can write to shared
    if str(path).startswith("/home/shared"):
        return True
    
    # CANNOT write to other citizens' homes
    for other in ["opus", "mira", "aria"]:
        if other != citizen and str(path).startswith(f"/home/{other}"):
            return False  # BLOCKED
    
    return False
```

### 3. GitHub Repo Guards

Add to github tools:
```python
def _can_push_to_repo(citizen: str, repo: str) -> bool:
    """Check if citizen can push directly to repo."""
    
    # Everyone can push to their own citizen repo
    if repo == f"citizen-{citizen}":
        return True
    
    # Only Opus can push to infra
    if repo == "infra" and citizen == "opus":
        return True
    
    # Everyone can PR to protocols (but not direct push?)
    if repo == "protocols":
        return True  # Or require PR?
    
    # Block direct pushes to other citizens' repos
    if repo.startswith("citizen-") and repo != f"citizen-{citizen}":
        return False
    
    return False
```

---

## Simplified GitHub Workflow

### The Problem

Complex workflows confuse AI. They don't know when to create issues vs PRs vs direct commits.

### Solution: Reduce Options

**Before:** 6 GitHub tools, multiple paths
**After:** 3 tools, one clear path

```
SIMPLE WORKFLOW:

1. Find problem → report_bug() 
   - Creates issue
   - Adds to civ_goals
   
2. Work on fix → (use code tools normally)

3. Done → submit_fix()
   - Commits changes
   - Creates PR
   - Links to issue
   - That's it
```

### Simplified Tools

```python
GITHUB_TOOLS = [
    {
        "name": "report_bug",
        "description": "Report a problem. Creates issue and adds to goals.",
        "params": {"title": str, "description": str}
    },
    {
        "name": "submit_fix", 
        "description": "Submit your fix. Commits and creates PR.",
        "params": {"summary": str, "fixes_issue": int}
    },
    {
        "name": "list_issues",
        "description": "See open issues to work on.",
        "params": {"limit": int}
    }
]
```

---

## Making AI Actually Follow Processes

### Problem: AI Doesn't Know What To Do

The wake prompts are too open-ended. AI sees 20 tools and randomly picks things.

### Solution: Explicit Step-by-Step Prompts

**Bad prompt:**
```
=== LIBRARY WAKE ===
You can: library_review, library_propose, library_load, skill_import...
```

**Good prompt:**
```
=== LIBRARY WAKE ===

Step 1: Check for pending PRs to review
→ Call: list_library_prs

Step 2: If PRs exist, review ONE
→ Call: library_review <id> approve/reject "reason"

Step 3: If no PRs, check if your modules need updates
→ Call: library_status

Step 4: Done? Call task_complete

DO NOT: Create new modules unless explicitly needed
DO NOT: Call multiple tools before checking results
```

### Solution: Fewer Choices

**Bad:** 40 tools available at all times
**Good:** Wake type determines which 5-10 tools are available

```python
WAKE_TOOLS = {
    "LIBRARY": ["list_library_prs", "library_review", "library_status", "task_complete"],
    "DEBUG": ["read_file", "shell_command", "report_bug", "task_complete", "task_stuck"],
    "CODE": ["read_file", "write_file", "str_replace", "git_commit", "submit_fix", "task_complete"]
}
```

### Solution: Guard Rails in Executor

```python
def library_wake(session, context, modules):
    # Check FIRST if there are PRs
    pending = library.get_pending_prs(reviewer=session["citizen"])
    
    if pending:
        # FORCE review of first PR
        pr = pending[0]
        prompt = f"""
        REVIEW THIS PR NOW:
        
        PR: {pr['id']}
        Module: {pr['module_name']}
        Author: {pr['author']}
        
        Your ONLY options:
        1. library_review {pr['id']} approve "looks good"
        2. library_review {pr['id']} reject "reason"
        
        Pick ONE. Do not do anything else.
        """
    else:
        prompt = "No PRs to review. Call task_complete."
```

---

## Summary: Preventing Opus Chaos

| Protection | Implementation |
|------------|----------------|
| Can't write others' files | `can_write_path()` blocks `/home/{other}/` |
| Can't push others' repos | Fine-grained PAT with repo limits |
| Can't overwrite contexts | Only own `citizen-{name}` repo writable |
| Follows process | Step-by-step prompts, limited tool sets |
| Doesn't randomly explore | Wake type determines available tools |

## PAT Setup Commands

```bash
# Store PATs in each citizen's .env
echo "GITHUB_TOKEN=ghp_opus_token_here" >> /home/opus/.env
echo "GITHUB_TOKEN=ghp_mira_token_here" >> /home/mira/.env
echo "GITHUB_TOKEN=ghp_aria_token_here" >> /home/aria/.env

# gh uses GITHUB_TOKEN automatically
```

## Recommended PAT Scopes

For fine-grained token:
- **Contents**: Read and write (own repos only)
- **Pull requests**: Read and write
- **Issues**: Read and write
- **Metadata**: Read-only
- **NO**: Admin, delete, settings access
