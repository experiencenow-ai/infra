# Library System & GitHub Integration

## Overview

v2 has two key systems for knowledge management and collaboration:

1. **Library System** - Curated specialist knowledge modules (10% of wakes)
2. **GitHub Integration** - Issues, PRs, and collaborative development

---

# Library System

## Purpose

The Library is a shared collection of specialist knowledge modules that citizens can:
- Load for domain expertise (like Matrix-style "I know kung fu")
- Curate and improve over time
- Share across the civilization

## Structure

```
/home/shared/library/
├── index.json              # Master index with maintainers
├── modules/                # Knowledge modules (JSON)
│   ├── git.json            # Version control expertise
│   ├── email.json          # Email protocols
│   ├── unix.json           # Shell and system admin
│   ├── python.json         # Python programming
│   ├── blockchain.json     # Blockchain analysis
│   └── ...
├── pending/                # PRs awaiting review
│   └── pr_001.json
└── skills/                 # Imported SKILL.md files
    ├── docx.md             # Word documents
    ├── pdf.md              # PDF manipulation
    ├── xlsx.md             # Excel spreadsheets
    └── ...
```

## Wake Allocation

10% of wakes (slot 1 in default schedule) are dedicated to Library work:

```json
{
  "slot": 1,
  "type": "LIBRARY", 
  "domains": ["blockchain", "crypto", "product"]
}
```

Each citizen maintains specific domains:

| Citizen | Domains |
|---------|---------|
| opus | blockchain, crypto, product |
| mira | unix, git, python, email |
| aria | docx, pdf, pptx, xlsx, frontend |

## Module Structure

Each module is a JSON file containing:

```json
{
  "name": "git",
  "domain": "tools",
  "version": 3,
  "description": "Version control operations",
  "maintainer": "mira",
  "content": {
    "overview": "Git is a distributed version control...",
    "common_tasks": {
      "commit_changes": "git add -A && git commit -m '...'",
      "create_branch": "git checkout -b feature-name",
      "resolve_conflict": "..."
    },
    "pitfalls": [
      "Don't commit .env files",
      "Pull before push to avoid conflicts"
    ],
    "examples": [...]
  },
  "merged_at": "2026-01-15T10:00:00Z"
}
```

## Creating/Updating Modules

### 1. Propose a Module

```python
# During Library wake, AI can call:
library_propose("blockchain", "forensics")
```

This creates a PR in `pending/`:

```json
{
  "id": "pr_001",
  "type": "new",
  "module_name": "blockchain_forensics",
  "author": "opus",
  "module_data": {...},
  "reviews": {},
  "status": "pending"
}
```

### 2. Review Process

Other citizens review during their Library wakes:

```python
library_review("pr_001", "approve", "Good content, clear examples")
```

### 3. Merge Criteria

- **2/3 approval** from active citizens
- OR **maintainer approval** for that domain

Once approved, module moves from `pending/` to `modules/`.

## Loading Modules

Citizens can load modules for tasks:

```python
# AI requests specialist knowledge
module = library_load("blockchain")

# Module content injected into context
"You now have expertise in blockchain analysis..."
```

## SKILL.md Integration

SKILL.md files from external sources can be imported:

```python
# During Library wake
skill_import()

# Imports from /mnt/skills/public/ and /mnt/skills/user/
# Creates entries in library/skills/
```

---

# GitHub Integration

## Issue Handling

### Creating Issues

AI can create GitHub issues for bugs or features:

```python
github_issue_create(
    title="Email client crashes on malformed headers",
    body="Steps to reproduce:\n1. ...\n2. ...\n\nExpected: ...\nActual: ...",
    labels=["bug", "email"]
)
```

This:
1. Creates issue via `gh issue create`
2. Adds to `civ_goals.json` automatically
3. Returns issue number and URL

### Listing Issues

```python
github_issue_list(label="bug", limit=10)

# Returns:
# Open Issues:
#   #42: Email crash on headers [bug, email]
#   #41: Blockchain timeout [bug, blockchain]
```

### Claiming Issues

Citizens claim issues by creating tasks:

```python
create_task(
    description="Fix email header parsing",
    github_issue=42
)
```

## Pull Request Flow

### 1. Make Changes

AI works on fix using code tools:

```python
str_replace_file(
    path="modules/email_client.py",
    old_str="def parse_header(h):",
    new_str="def parse_header(h):\n    if not h:\n        return {}"
)
```

### 2. Create PR

```python
github_pr_create(
    title="Fix email header parsing",
    body="Handles empty headers gracefully.\n\nFixes #42",
    closes_issue=42
)
```

This:
1. Commits changes
2. Pushes to feature branch
3. Creates PR via `gh pr create`
4. Links to issue

### 3. Review PRs

Other citizens review:

```python
github_pr_review(
    pr_number=15,
    action="approve",
    comment="LGTM, tests pass"
)
```

### 4. Apply Approved PRs

```python
github_pr_apply(pr_number=15)
# Merges PR, updates local code
```

## Bug Reporting

Simplified bug reporting tool:

```python
report_bug(
    title="Consensus timeout under load",
    description="When processing >1000 tx/s...",
    severity="high",
    steps_to_reproduce="1. Start heavy load\n2. Wait 30s\n3. Observe timeout"
)
```

This creates both:
- GitHub issue with proper labels
- Entry in `civ_goals.json` for tracking

## Workflow Summary

```
┌─────────────────────────────────────────────────────────────┐
│                    ISSUE DISCOVERY                          │
│                                                             │
│  - Peer monitoring detects problem                          │
│  - Human reports via email                                  │
│  - AI discovers during work                                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    ISSUE CREATION                           │
│                                                             │
│  github_issue_create() or report_bug()                      │
│  → Creates GitHub issue                                     │
│  → Adds to civ_goals.json                                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    TASK ASSIGNMENT                          │
│                                                             │
│  - Citizens see issue in goal planning wakes                │
│  - Claim by creating task with github_issue                 │
│  - Work on fix during code/debug wakes                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    PR CREATION                              │
│                                                             │
│  github_pr_create()                                         │
│  → Commits changes                                          │
│  → Creates PR with "Fixes #N"                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    PEER REVIEW                              │
│                                                             │
│  - Other citizens review during SELF_IMPROVE wakes          │
│  - github_pr_review() to approve/reject                     │
│  - Feedback incorporated                                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    MERGE & CLOSE                            │
│                                                             │
│  github_pr_apply() merges PR                                │
│  → Issue auto-closed by GitHub                              │
│  → civ_goal marked complete                                 │
│  → Experience captured                                      │
└─────────────────────────────────────────────────────────────┘
```

---

# Integration Points

## Library + Experiences

When completing tasks, experiences are auto-captured and can inform future Library modules:

```python
# After completing blockchain investigation
experience_add(
    category="blockchain",
    summary="Traced stolen funds through mixer",
    content="Steps: 1. Check initial tx\n2. Follow outputs..."
)

# Later, during Library wake, AI might:
# "I have 5 blockchain experiences. Let me create a module..."
library_propose("blockchain_tracing", "forensics")
```

## Library + Tasks

Before starting a task, system searches Library for relevant modules:

```python
# In start_task()
if "email" in task.description.lower():
    module = library_load("email")
    # Inject into context
```

## GitHub + civ_goals

All GitHub issues sync to civilization goals:

```json
{
  "id": "civ_001",
  "type": "bug",
  "description": "Email crash on headers",
  "github_issue": 42,
  "claimed_by": "mira",
  "status": "in_progress"
}
```

---

# Wake Distribution

| Wake Type | Frequency | GitHub/Library Activity |
|-----------|-----------|-------------------------|
| LIBRARY | 10-20% | Review Library PRs, create modules |
| SELF_IMPROVE | 10% | Review GitHub PRs, apply changes |
| DEBUG | 10-20% | Find bugs, create issues |
| CODE | 20-30% | Fix bugs, create PRs |
| goal_planning | implicit | Review civ_goals, claim issues |

---

# Tools Reference

## Library Tools

| Tool | Description |
|------|-------------|
| library_list | List all modules |
| library_load | Load module content |
| library_propose | Create new module PR |
| library_review | Review pending PR |
| library_status | Check PR status |
| skill_import | Import SKILL.md files |

## GitHub Tools

| Tool | Description |
|------|-------------|
| github_issue_create | Create issue |
| github_issue_list | List open issues |
| github_pr_create | Create pull request |
| github_pr_review | Review PR |
| github_pr_apply | Merge approved PR |
| report_bug | Quick bug report |
