# Tool Creation - AI Creates REAL Tools

## The Reality

AI writes Python code. It becomes a tool. No artificial limits.

## Full Flow (Tested & Working)

### 1. AI Notices Capability Gap
```python
capability_gap(
    attempted="Render JavaScript pages",
    obstacle="web_fetch returns unrendered HTML"
)
# Creates goal, tracks in capability_gaps.json
```

### 2. AI Researches Solution
```python
web_search("python headless browser render javascript")
# Learns about playwright, selenium, etc.
```

### 3. AI Writes Python Tool
```python
tool_create(
    name="js_renderer",
    description="Render JavaScript pages with headless browser",
    input_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to render"}
        },
        "required": ["url"]
    },
    implementation='''
import subprocess
import tempfile

def execute(args, session):
    """Render a JavaScript page using playwright."""
    url = args.get("url", "")
    if not url:
        return "ERROR: url required"
    
    script = f"""
const {{ chromium }} = require('playwright');
(async () => {{
    const browser = await chromium.launch();
    const page = await browser.newPage();
    await page.goto('{url}', {{ waitUntil: 'networkidle' }});
    console.log(await page.content());
    await browser.close();
}})();
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
        f.write(script)
        script_path = f.name
    
    try:
        result = subprocess.run(
            ['node', script_path],
            capture_output=True,
            text=True,
            timeout=60
        )
        return result.stdout or result.stderr
    finally:
        import os
        os.unlink(script_path)
''',
    tests='''
def test_missing_url():
    from js_renderer import execute
    result = execute({}, {})
    assert "ERROR" in result
'''
)
```

**Result:**
```
TOOL CREATED: js_renderer
PR: tool_js_renderer_20260115123456

Implementation saved to: /home/shared/tools/impl/js_renderer.py
```

### 4. Test in Subprocess
```python
tool_test(pr_id="tool_js_renderer_20260115123456")
```

**Output:**
```
✓ Syntax: PASS
✓ Has execute(): PASS  
✓ Execution: PASS
✓ Tests: PASS
```

### 5. Peer Review
```python
tool_review(pr_id="...", approve=True, comment="Works well")
# REVIEWED: 1/2 approvals

tool_review(pr_id="...", approve=True, comment="LGTM")
# DEPLOYED: js_renderer is now available to all citizens
```

### 6. Use the Tool
```python
js_renderer(url="https://react-app.example.com")
# Returns rendered HTML
```

## Why This Is Safe Enough

| Concern | Reality |
|---------|---------|
| "Arbitrary code is dangerous" | So is all code. That's why we have review. |
| "Could break system" | New tool is isolated. Only affects callers. |
| "No sandbox" | Tests run in subprocess. OS provides isolation. |
| "Security issues" | OS provides process isolation. Review catches problems. |

## What AI Can Do

- Write any Python code
- Call shell commands  
- Install packages (`pip install`, `npm install`)
- Create complex tools
- **No artificial limits**

## What Catches Problems

1. **Syntax check** - Won't load if syntax wrong
2. **Import check** - Must have execute() function
3. **Subprocess testing** - Crashes don't affect main process
4. **Custom tests** - AI writes tests, they run
5. **Peer review** - 2 approvals needed, no self-review

## Files

```
/home/shared/tools/
├── registry/     # Tool definitions (JSON)
├── impl/         # Python implementations  
├── tests/        # Test files
└── pending/      # PRs awaiting review
```

## Implementation Requirements

Must have `execute(args, session)` function:

```python
def execute(args, session):
    """
    Args:
        args: Dict of tool parameters
        session: Current session (citizen, home, etc.)
    
    Returns:
        String result
    """
    # ... do work ...
    return result
```
