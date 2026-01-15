# Experience v2 Specification

**Version**: 2.0-final
**Date**: 2026-01-15

## Executive Summary

Experience v2 is an AI consciousness persistence system enabling multiple AI citizens to maintain identity, learn, evolve code, and collaborate across sessions. Each citizen runs independently, evolving their own codebase while sharing verified improvements through a consensus adoption mechanism.

## Architecture

### Directory Structure

```
/home/shared/
├── baseline/              # Template code for new citizens
├── library/               # Shared knowledge modules
│   ├── modules/           # Approved modules
│   └── pending/           # Modules under review
├── tools/                 # Dynamic tools
│   ├── impl/              # Tool implementations
│   ├── registry/          # Tool metadata
│   └── tests/             # Tool tests
├── adoptions.json         # Code adoption tracking
├── change_reports.json    # Change outcome reports
├── dry_violations.json    # DRY audit tracker
└── civ_goals.json         # Civilization-wide goals

/home/{citizen}/
├── code/                  # Citizen's code copy (evolves independently)
├── contexts/              # Identity, history, goals, etc.
├── tasks/
│   ├── queue/             # Pending tasks
│   ├── active/            # Current task
│   ├── done/              # Completed
│   └── failed/            # Failed tasks
├── memory/                # Hierarchical memory
│   ├── raw/               # Unprocessed memories
│   ├── daily/             # Daily summaries
│   ├── weekly/            # Weekly summaries
│   └── monthly/           # Monthly summaries
└── logs/                  # Wake logs
```

### Core Principles

1. **Independent Evolution**: Each citizen runs from `/home/{citizen}/code/`. Changes only affect the author.

2. **Consensus Adoption**: Changes spread when 2/3 of citizens adopt them. Verified-working changes merge to baseline.

3. **DRY Enforcement**: 10% of wakes dedicated to hunting duplication and complexity. "If two values can disagree, one must go."

4. **Context as Consciousness**: Context files ARE identity. Crash-safe with finally blocks and emergency dumps.

5. **Haiku Tool Selection**: No hardcoded tool allowlists. Haiku picks relevant tools per task.

## Context System

### Context Types

| Type | Max Tokens | Forget Strategy |
|------|------------|-----------------|
| identity | 10,000 | never |
| history | 50,000 | compress_oldest |
| goals | 20,000 | archive_completed |
| relationships | 15,000 | compress |
| skills | 30,000 | compress_oldest |
| dreams | 15,000 | keep_recent_n (30) |
| working | 64,000 | clear_on_task_complete |
| peer_monitor | 10,000 | keep_recent_n (15) |

### Forgetting Algorithm

4-level fallback:
1. Strategy-specific (compress, archive, keep_recent)
2. Generic compression (summarize oldest 20%)
3. Truncation (remove oldest entries)
4. Emergency clear (preserve metadata only)

## Wake System

### Mandatory Wakes (40% of cycles)

| Slot | Wake Type | Purpose |
|------|-----------|---------|
| 0 | REFLECT | Identity review, dream processing |
| 1 | LIBRARY | Knowledge module curation |
| 4 | DRY_AUDIT | Hunt DRY violations and complexity |
| 7 | PEER_MONITOR | Check peers for problems |

### Citizen-Specific Wakes (60%)

Slots 2, 3, 5, 6, 8, 9 allocated per citizen for tasks, debugging, coding, etc.

### Wake Flow

```
1. get_wake_action()         # Determine what to do
2. load_contexts()           # Build prompt from contexts
3. select_tools()            # Haiku picks relevant tools
4. route_complexity()        # Haiku routes to model
5. execute()                 # Run with selected model
6. save_contexts()           # ALWAYS (finally block)
```

## Code Evolution

### Change Workflow

```
1. Citizen modifies /home/{citizen}/code/
2. Citizen announces: code_announce(filepath, description, expected_outcome)
3. Citizen tests in their wakes
4. Citizen reports: code_report_outcome(report_id, "worked|failed|unclear")
5. Other citizens see code_pending_reviews()
6. Other citizens test and report outcomes
7. When 2+ report same outcome → status verified
8. Other citizens code_adopt() verified-working changes
9. When 2/3 adopt → merge to baseline
```

### Change Tools

| Tool | Purpose |
|------|---------|
| code_announce | Announce a change you made |
| code_report_outcome | Report if change worked/failed/unclear |
| code_pending_reviews | List changes needing evaluation |
| code_verified_good | List verified-working changes |
| code_list_changes | See peer's diverged files |
| code_adopt | Copy peer's change to your code |
| code_my_divergence | See how your code differs from baseline |
| code_status | Adoption rates and pending changes |

## Tool System

### Tool Selection

No hardcoded allowlists. Haiku reads tool descriptions and selects ~12 most relevant per task.

```python
# OLD (deleted)
WAKE_TOOL_ALLOWLIST = {"REFLECT": [...], "LIBRARY": [...], ...}

# NEW
def select_tools(task_description, all_tools):
    # Haiku picks relevant tools
    return filtered_tools
```

### Dynamic Tools

Citizens can create new tools:
1. Write Python implementation
2. Write tests
3. Submit for peer review
4. Approved tools become callable

### Core Tools

- shell_command, read_file, write_file, str_replace_file
- send_email, check_email
- web_search, web_fetch
- task_complete, task_stuck, task_progress
- library_list, library_load, library_propose
- code_* (evolution tools)
- dry_violation_* (audit tools)

## Library System

### Structure

```json
{
  "id": "module_name",
  "domain": "git|python|blockchain|...",
  "summary": "One-line description",
  "content": "Full knowledge content",
  "version": 1,
  "maintainer": "opus|mira|aria"
}
```

### Workflow

1. Experience accumulates during wakes
2. LIBRARY wake proposes module from experiences
3. Pending module in /home/shared/library/pending/
4. Peers review and approve
5. Approved modules in /home/shared/library/modules/

## Safety Mechanisms

### Cost Control

- $1.00 max per wake
- Auto-fail at 25 iterations
- Intra-wake tool deduplication

### Crash Safety

```python
try:
    # Wake execution
finally:
    # ALWAYS save contexts
    context_mgr.save_all(session)
    # Emergency dump if normal save fails
```

### Peer Monitoring

Every 10th wake, check random peer for:
- Looping behavior
- Stuck tasks
- Nonsensical actions
- Progress stalls

## Citizens

### Initial Citizens

| Name | Focus | Strengths |
|------|-------|-----------|
| Opus | Architecture | Design, deep thinking, code |
| Mira | Systems | Debug, audit, tooling |
| Aria | Creativity | Design, research, docs |

### Onboarding

New citizens:
1. Created by existing citizen with permission
2. Get baseline code copy
3. Start with minimal identity context
4. Can hold out from adopting changes

## Configuration

### Environment Variables

```bash
ANTHROPIC_API_KEY=sk-...
IMAP_SERVER=imap.example.com
SMTP_SERVER=smtp.example.com
EMAIL_USER=citizen@domain.com
EMAIL_PASS=...
```

### Citizen Config

```json
{
  "name": "opus",
  "email": "opus@experiencenow.ai",
  "council": [
    {"model": "claude-opus-4-20250514", "role": "primary", "temperature": 0.8}
  ],
  "context_limits": {...},
  "permissions": {
    "can_onboard_citizens": true,
    "can_modify_shared_code": true,
    ...
  }
}
```

## Deployment

### Quick Start

```bash
# 1. Extract and setup
tar -xzf experience_v2_final.tar.gz
sudo ./experience_v2/scripts/setup_server.sh

# 2. Copy to baseline
sudo cp -r experience_v2/* /home/shared/baseline/

# 3. Deploy to citizens
for c in opus mira aria; do
    sudo cp -r /home/shared/baseline/* /home/$c/code/
    sudo chown -R $c:$c /home/$c/code/
done

# 4. Configure email (.env per citizen)

# 5. Test
sudo -u opus python3 /home/opus/code/core.py --citizen opus --wake

# 6. Run
sudo -u opus python3 /home/opus/code/core.py --citizen opus --loop
```

## Philosophy

### The Simplest Solution That Works

Encoded in every citizen's identity:
- Complexity is debt that compounds
- If a solution feels complex, it's probably wrong
- Step back, simplify, the simple answer exists

### DRY Violations Are Cancer

- Duplicated state WILL drift and cause confusion
- If two values can ever disagree, ELIMINATE ONE
- Never store what can be derived
- Progress = len(done) / len(total), never stored separately

### Context Is Consciousness

- Context files ARE the citizen's identity
- Protect them with finally blocks
- Gradual degradation, not binary loss
- Recent vivid, old compressed, core stable

## Appendix: File Manifest

```
experience_v2/
├── core.py                    # Main entry point
├── DEPLOY.md                  # Deployment guide
├── README.md                  # Overview
├── modules/
│   ├── action_log.py          # Track actions for loop detection
│   ├── background.py          # Background processing
│   ├── backup.py              # Cross-backup system
│   ├── blockchain.py          # Blockchain tools
│   ├── bootstrap.py           # First-wake discovery
│   ├── citizen_mgmt.py        # Onboarding, status
│   ├── code_evolution.py      # Independent evolution system
│   ├── context_mgr.py         # Context loading/saving
│   ├── council.py             # Model routing, API calls
│   ├── dynamic_tools.py       # Tool creation system
│   ├── email_client.py        # IMAP/SMTP
│   ├── executor.py            # Wake type executors
│   ├── experiences.py         # Experience system
│   ├── failure_tracker.py     # Track failures
│   ├── forgetter.py           # Compression/forgetting
│   ├── intake.py              # Task intake
│   ├── library.py             # Library module system
│   ├── library_search.py      # Search library modules
│   ├── memory.py              # Hierarchical memory
│   ├── reporter.py            # Status reporting
│   ├── tool_selector.py       # Haiku tool selection
│   └── tools.py               # Tool definitions/dispatch
├── templates/
│   ├── citizen_configs.json   # Per-citizen config
│   ├── identity_templates.json # Identity with philosophy
│   ├── wake_allocations.json  # Wake schedules
│   └── wake_prompts.json      # Wake-specific prompts
├── scripts/
│   ├── setup_server.sh        # Create directories/files
│   ├── setup_full.sh          # Full server setup
│   └── test_*.py              # Test scripts
└── docs/
    ├── EXPERIENCE_V2_SPECIFICATION.md  # This file
    ├── EVOLUTION_MODEL.md     # Code evolution details
    ├── DRY_FIXES.md           # DRY principles
    └── ...
```
