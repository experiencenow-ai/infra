# Knowledge Acquisition - How AI Learns

## The Core Principle

**No pre-loaded answers.** Library starts EMPTY.

Pre-seeding knowledge is cheating. Real intelligence requires:
1. Recognizing you don't know something
2. Researching to fill the gap
3. Learning from the results
4. Sharing useful knowledge with peers

## The Learning Flow

### Step 1: Task Arrives

```
User: "Write a C program that sorts a file of numbers"
```

### Step 2: Library Search (Keyword-Based)

```python
# Extract keywords from task
keywords = extract_keywords(task)  # ["sort", "numbers", "file"]

# Search Library modules (starts EMPTY)
modules = search_library(keywords)  # []

# Console output:
[LIBRARY] No modules found for: ['sort', 'numbers', 'file']
```

### Step 3: AI Sees Guidance

```
=== GUIDANCE ===
If you're UNCERTAIN about the best approach:
1. Use web_search to research (e.g., "C sorting algorithms comparison")
2. After learning something useful, capture it with library_propose
```

### Step 4: AI Researches

AI thinks: "I can write a basic sort, but I'm not sure about optimal approach."

```python
web_search("C sorting algorithms comparison performance")
```

Results explain:
- qsort() from stdlib: O(n log n), good for general use
- For large files: external merge sort
- For integers with small range: counting sort

### Step 5: Task Completion + Learning Capture

AI writes the program using qsort().

```python
experience_add(
    "Learned: For general C sorting, use qsort() from stdlib. "
    "It's O(n log n) average case. For very large files that don't "
    "fit in memory, external merge sort is needed."
)
```

### Step 6: Module Creation (Later)

After 5+ related experiences, during a LIBRARY wake:

```
=== LIBRARY WAKE: STATUS CHECK ===

YOUR EXPERIENCES: 7
(If you have 5+ experiences on a topic, consider creating a module)
```

AI reviews experiences:
```python
experience_search("sorting")
```

Finds multiple learnings about sorting. Creates module:

```python
library_propose(
    name="c_sorting",
    domain="programming",
    knowledge="Summary of sorting learnings...",
    examples="qsort usage, when to use external sort...",
    patterns="Algorithm selection by data characteristics..."
)
```

PR created → Peer review → 2/3 approval → Merged

### Step 7: Future Tasks

```
User: "Help optimize my sorting code"

Console:
[LIBRARY] Found modules: ['c_sorting']

AI sees:
=== RELEVANT KNOWLEDGE (from Library) ===
### c_sorting
(Content created from real learning, not hardcoded)
```

## What This Means

| First time | Subsequent times |
|------------|------------------|
| No Library modules | Module exists |
| AI researches (web_search) | Knowledge injected |
| AI captures learning | AI has context |
| Slower, but learns | Faster, uses learning |

## Key Guarantees

1. **Library starts empty** - no pre-seeded "answers"
2. **Modules come from experience** - AI must actually work on the topic
3. **Peer review required** - 2/3 approval prevents low-quality modules
4. **Keyword search** - no hardcoded domain detection

## Forgetting: File Deduplication

When you iterate on the same file many times, only the latest version is kept:

```
Wake 1: read_file('/path/foo.c') → version 1
Wake 2: modify, read_file('/path/foo.c') → version 2
Wake 3: modify, read_file('/path/foo.c') → version 3
...
Wake 10: modify, read_file('/path/foo.c') → version 10

When Forgetter runs:
- Detects /path/foo.c appears 10 times
- Keeps ONLY version 10 (most recent)
- Removes versions 1-9

Result: Context doesn't grow linearly with iterations
```

This allows many iterations without exploding context size.

## Console Output Examples

**No Library modules, no experiences:**
```
[LIBRARY] No modules found for: ['sort', 'numbers']
[LIBRARY] Should research: True
[ROUTE] MEDIUM → sonnet
```

**Library module found:**
```
[LIBRARY] Found modules: ['c_sorting']
[EXP] Found 3 related experiences
[ROUTE] MEDIUM → sonnet
```

**After file deduplication:**
```
[DEDUP] Removed 5 duplicate file instances
[FORGET] working: 15,000 → 8,000 (freed 7,000)
```

## The Knuth Problem (Large Library Selection)

### The Problem

What if AI creates 100 modules from Knuth's "Art of Computer Programming"?

Keyword search becomes noisy:
```
Task: "implement a hash table"

Keyword search finds 8 matches:
- hash_tables
- searching  
- sorting
- data_structures
- complexity
- memory_management
- algorithms_vol3
- numerical_methods
```

How does AI know which one to use?

### The Solution: AI-Assisted Selection

**When few matches (≤2):** Auto-inject
```
[LIBRARY] Auto-loaded: ['hash_tables']
```

**When many matches (>2):** Show options, let AI pick
```
=== LIBRARY MODULES AVAILABLE ===
Found 8 potentially relevant modules:
  - hash_tables: Hash function design, collision resolution...
  - searching: Sequential and binary search algorithms...
  - sorting: Comparison-based and linear-time sorting...
  - data_structures: Arrays, lists, trees, graphs...
  - complexity: Big-O analysis, amortized complexity...

Use library_load(name) if you need one of these.
```

AI reads the summaries and decides:
```python
library_load("hash_tables")  # This is what I need
```

### Why This Isn't Cheating

| Approach | Who Decides | Problem |
|----------|-------------|---------|
| Hardcoded domains | We do | We encode what's relevant to what |
| Auto-inject all | Nobody | Context explodes |
| AI-assisted | AI does | AI reads summaries, makes choice |

The key: **We don't encode domain-to-task mappings.** AI makes the selection based on understanding module summaries and task requirements.

## Expertise Cleanup

Library content doesn't accumulate across turns:

```
Turn 1: Task needs sorting → sorting module loaded
Turn 2: Task shifts to file I/O → sorting module STRIPPED, file_io loaded
Turn 3: Task shifts to networking → file_io STRIPPED, networking loaded
```

Each turn:
1. Old Library content is removed from working context
2. New keyword search runs
3. Fresh relevant modules loaded

This keeps context focused on current need, not historical accumulation.

---

## Bootstrap Process (First Wakes)

### The Problem

Tools need descriptions for the API, but we shouldn't hardcode "best practices" or "when to use" - that's encoding knowledge.

### The Solution

On first wakes, AI documents its own capabilities:

```
=== BOOTSTRAP WAKE: DOCUMENT YOUR CAPABILITIES ===

CAPABILITY AREA: github_workflow
TOOLS TO DOCUMENT: github_issue_create, github_pr_create, ...

Experiment with these tools and document:
1. When to create issues vs PRs
2. The review process
3. Error handling patterns
4. Best practices you discover

Create a Library module called 'github_workflow' with your findings.
```

### Why This Isn't Cheating

| Type | Example | Cheating? |
|------|---------|-----------|
| Domain knowledge | "quicksort is O(n log n)" | YES |
| Infrastructure knowledge | "use PRs for code changes" | NO |

Infrastructure knowledge is the AI learning its own "body" - how to effectively use the tools it has.

### Bootstrap Areas

| Area | Tools | Creates Module |
|------|-------|----------------|
| github_workflow | issue_create, pr_create, pr_review | How to use GitHub |
| email_patterns | send_email, check_email | How to communicate |
| shell_safety | shell_command | Safe command patterns |
| file_operations | read_file, write_file | Atomic writes, errors |
| task_lifecycle | task_complete, task_stuck | When to complete/escalate |
| experience_capture | experience_add, search | What to record |
| library_curation | library_propose, review | When to create modules |

### Bootstrap Flow

```
Wake 1: [BOOTSTRAP] Documenting: github_workflow
        AI experiments with GitHub tools
        AI calls library_propose("github_workflow", ...)
        PR created for review

Wake 2: [BOOTSTRAP] Documenting: email_patterns
        ...

Wake 7: [BOOTSTRAP] All capability areas documented!
        Normal wake cycle begins
```

### After Bootstrap

When AI does GitHub work:
```
[LIBRARY] Found modules: ['github_workflow']
```

The infrastructure module (created by AI experimentation, not hardcoded) is injected.
