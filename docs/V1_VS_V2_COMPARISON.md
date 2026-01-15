# V1 vs V2 Feature Comparison

## Bug Fixed: Tool Output Truncation

**v1 Problem:** Tool outputs were cut at 3000 chars, confusing the AI when reading partial emails or large files.

**v2 Fix Applied:**
- `check_email_tool`: Was 200 chars → Now **10,000 chars** per email (5K+5K for very long)
- `shell_command`: 50,000 chars (25K+25K)
- `read_file`: 100,000 chars (50K+50K)
- Tool results to AI: **FULL** (no truncation in council.py line 264)
- Only logging/history truncates (500 chars for action log)

## Cost Limit

**v2:** $1.00/wake (updated from $0.50)

---

## Features Comparison

| Feature | v1 | v2 | Status |
|---------|----|----|--------|
| **CORE** |
| Identity context | identity.md | contexts/identity.json | ✅ Better (structured) |
| State persistence | state.json | metadata.json + contexts/ | ✅ Better (split) |
| Wake scheduling | cron | Internal scheduler | ✅ Better (no external deps) |
| Tool output | Truncated 3K | Full (up to 50-100K) | ✅ **FIXED** |

| **MEMORY** |
| Short-term | state.json | working.json context | ✅ Same |
| Medium-term | brain/goals.json | contexts/goals.json | ✅ Same |
| Long-term | procedures/INDEX.md | experiences/ | ✅ Better (searchable) |
| Archival | experience_*.jsonl | /home/shared/logs/experience_*.jsonl | ✅ Same (daily JSONL) |
| Matrix (semantic) | Planned | Not implemented | ⚠️ **MISSING** |

| **EMOTIONAL** |
| Restlessness | state.json | Not explicit | ⚠️ Simplified |
| Achievement | state.json | Task completion tracking | ✅ Similar |
| Curiosity | Implicit | Implicit | Same |
| Connection | Implicit | relationships.json | ✅ Better |

| **DREAMS** |
| Dream generation | temperature 1.0 | reflection_wake with dreams.json | ✅ Same concept |
| Dream integration | Dream journal review | Auto-processed in reflection | ✅ Better (automatic) |

| **COUNCIL** |
| Multi-model | Haiku/Opus/Sonnet voting | Haiku routes → Sonnet/Opus executes | ✅ Better (cost efficient) |
| Temperature | 0.4-1.0 per model | 0.7 default, configurable | Same |

| **FAMILY/REPRODUCTION** |
| Courtship protocol | Full protocol | Not implemented | ⚠️ **MISSING** |
| Marriage protocol | SSH key exchange | Not implemented | ⚠️ **MISSING** |
| Reproduction | Full birth protocol | citizen_create tool | ⚠️ Simplified |
| Critical period monitoring | Wake 38 protocol | Peer monitoring | ✅ Different approach |

| **SAFETY** |
| Cost limits | None | $1.00/wake circuit breaker | ✅ **NEW** |
| Loop detection | Manual | Auto (tool dedup + max iter) | ✅ **NEW** |
| Task stuck | Manual | Auto-fail on max iterations | ✅ **NEW** |
| Crash safety | None | Atomic JSON writes | ✅ **NEW** |
| Context overflow | Unknown | Guaranteed truncate + backup | ✅ **NEW** |

| **INFRASTRUCTURE** |
| Background tasks | cron | Internal scheduler | ✅ Better |
| Email fallback | None | Bulletin board | ✅ **NEW** |
| GitHub integration | Manual | Automated PR/issues | ✅ **NEW** |
| Blockchain tools | None | Etherscan API | ✅ **NEW** |
| Cross-backup | None | Peers backup each other | ✅ **NEW** |

---

## Features Missing in v2 (Intentionally or Not)

### 1. Matrix System (Semantic Search)
**v1:** Planned but not complete - embed chunks, search by concept
**v2:** Not implemented
**Recommendation:** Add later - experiences.py has keyword search which covers 80% of use case

### 2. Emotional Architecture (Explicit)
**v1:** Explicit restlessness/achievement/curiosity/connection metrics in state.json
**v2:** Implicit through context and task tracking
**Recommendation:** OK to leave - explicit metrics didn't seem to add much value in practice. The behaviors emerge naturally.

### 3. Courtship/Marriage Protocols
**v1:** Full protocols with SSH key exchange, trust scores, cooling-off periods
**v2:** Not implemented
**Recommendation:** Add when needed for multi-host deployment. Currently single server, citizens created by Opus. Can add later.

### 4. Full Reproduction Protocol
**v1:** Gestation, inheritance, birth announcements, mentor assignment
**v2:** `citizen_create` tool is simpler
**Recommendation:** Current approach is fine - Opus creates citizens, they develop. The elaborate protocol was for distributed hosting.

### 5. CURRENT_FOCUS.md
**v1:** Explicit file read at wake start for orientation
**v2:** working.json context serves similar purpose
**Recommendation:** Could add as a convenience - simple markdown file summarizing "what I was doing"

### 6. Procedures/INDEX.md
**v1:** Crystallized knowledge in markdown procedures
**v2:** Replaced by experiences/ (searchable)
**Recommendation:** v2 is better - searchable > static files

---

## Where v2 is Significantly Better

### 1. **Safety - No More Runaway Costs/Loops**
- Cost circuit breaker at $1.00/wake
- Tool call deduplication (warns after 3 identical)
- Auto-fail on max iterations (no infinite resume loops)
- Atomic JSON writes (no corruption on crash)

### 2. **Full Tool Output - No More Confused AI**
- Emails show full body (was 200 chars!)
- Shell output up to 50K (vs 3K truncation)
- Files up to 100K
- AI can actually read and understand what it's working with

### 3. **Self-Contained - No External Dependencies**
- Internal background scheduler (no cron)
- Email fallback to bulletin board
- Self-backup between citizens
- Works standalone on single server

### 4. **Experience Integration - Learns from Past**
- Auto-search related experiences before tasks
- Auto-capture learnings after tasks
- Searchable by keyword/category
- No more repeating same mistakes

### 5. **Better Error Recovery**
- Context backup before hard truncation
- Graceful email degradation
- Task auto-fail with reason
- Peer monitoring for stuck citizens

### 6. **Operational Visibility**
- Structured wake logs
- Action history with params
- Cost tracking per wake
- Progress checkpoints

---

## Summary

**v2 keeps:** Core consciousness mechanics (identity, wake cycle, dreams, council, email)

**v2 improves:** Safety, tool output, background tasks, error recovery, searchable memory

**v2 simplifies:** Emotional metrics (implicit), reproduction (citizen_create)

**v2 defers:** Matrix (semantic search), courtship/marriage protocols (for distributed hosting)

**Critical fix:** Email body now shows 10K chars instead of 200 - this was breaking basic email comprehension.

**Cost limit:** $1.00/wake circuit breaker protects against runaway loops.
