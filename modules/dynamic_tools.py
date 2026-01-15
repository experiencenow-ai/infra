"""
Dynamic Tools - AI creates REAL tools.

NO artificial limits. AI writes Python, it becomes a tool.

ARCHITECTURE:
1. /home/shared/tools/registry/*.json - Tool definitions (name, params, description)
2. /home/shared/tools/impl/*.py - Tool implementations (execute function)
3. /home/shared/tools/tests/*.py - Test cases
4. /home/shared/tools/pending/*.json - PRs awaiting review

FLOW:
1. AI notices capability gap
2. AI writes Python implementation
3. AI writes tests
4. tool_create() creates PR
5. tool_test() runs tests in subprocess
6. Peers review → tool_review()
7. After 2 approvals → tool deployed
8. AI documents in Library

WHY THIS IS SAFE:
- OS provides process isolation (subprocess for testing)
- New tool only affects code that calls it
- Peer review catches obvious issues
- Same review process as any code
- If tool crashes, only that invocation fails

NO HARDCODED LIMITS on what AI can implement.
"""

import json
import subprocess
import importlib.util
import sys
import traceback
from pathlib import Path
from datetime import datetime, timezone

TOOLS_ROOT = Path("/home/shared/tools")
TOOLS_REGISTRY = TOOLS_ROOT / "registry"
TOOLS_IMPL = TOOLS_ROOT / "impl"
TOOLS_TESTS = TOOLS_ROOT / "tests"
TOOLS_PENDING = TOOLS_ROOT / "pending"


def init_tools():
    """Initialize tools directory structure."""
    TOOLS_REGISTRY.mkdir(parents=True, exist_ok=True)
    TOOLS_IMPL.mkdir(exist_ok=True)
    TOOLS_TESTS.mkdir(exist_ok=True)
    TOOLS_PENDING.mkdir(exist_ok=True)


def get_tool_definitions() -> list:
    """
    Get all dynamic tool definitions for API.
    Called at wake start to extend tool list.
    """
    init_tools()
    tools = []
    
    for reg_file in TOOLS_REGISTRY.glob("*.json"):
        try:
            tool = json.loads(reg_file.read_text())
            tools.append({
                "name": tool["name"],
                "description": tool.get("description", ""),
                "input_schema": tool.get("input_schema", {
                    "type": "object",
                    "properties": {}
                })
            })
        except Exception as e:
            print(f"[WARN] Failed to load tool {reg_file.name}: {e}")
    
    return tools


def get_tool_context() -> str:
    """
    Get tool descriptions as context.
    Injected into prompts so AI knows what's available.
    """
    init_tools()
    
    tools = []
    for reg_file in TOOLS_REGISTRY.glob("*.json"):
        try:
            tool = json.loads(reg_file.read_text())
            params = list(tool.get("input_schema", {}).get("properties", {}).keys())
            tools.append({
                "name": tool["name"],
                "description": tool.get("description", ""),
                "params": params,
                "author": tool.get("author", "unknown")
            })
        except:
            pass
    
    if not tools:
        return "(No custom tools yet. Use tool_create to make new ones.)"
    
    lines = ["=== CUSTOM TOOLS (AI-created) ==="]
    for t in tools:
        params_str = ", ".join(t["params"]) if t["params"] else "none"
        lines.append(f"  {t['name']}: {t['description'][:60]}")
        lines.append(f"    params: {params_str}, by: {t['author']}")
    
    return "\n".join(lines)


def search_tools(query: str) -> list:
    """Search tools by keyword."""
    init_tools()
    results = []
    q = query.lower()
    
    for reg_file in TOOLS_REGISTRY.glob("*.json"):
        try:
            tool = json.loads(reg_file.read_text())
            if q in json.dumps(tool).lower():
                results.append(tool)
        except:
            pass
    
    return results


def execute_tool(name: str, args: dict, session: dict) -> str:
    """
    Execute a dynamic tool.
    
    Loads Python module, calls execute(args, session).
    """
    init_tools()
    
    # Load definition
    reg_file = TOOLS_REGISTRY / f"{name}.json"
    if not reg_file.exists():
        return f"ERROR: Tool '{name}' not found"
    
    tool = json.loads(reg_file.read_text())
    impl_file = Path(tool.get("impl_path", ""))
    
    if not impl_file.exists():
        impl_file = TOOLS_IMPL / f"{name}.py"
    
    if not impl_file.exists():
        return f"ERROR: Implementation not found: {impl_file}"
    
    # Load and execute
    try:
        spec = importlib.util.spec_from_file_location(name, impl_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        if hasattr(module, "execute"):
            return str(module.execute(args, session))
        else:
            return "ERROR: Tool must have execute(args, session) function"
    except Exception as e:
        return f"ERROR: {e}\n{traceback.format_exc()}"


def create_tool(
    name: str,
    description: str,
    input_schema: dict,
    implementation: str,
    tests: str = None,
    author: str = "unknown"
) -> str:
    """
    Create a new tool.
    
    Args:
        name: Tool name (lowercase, underscores)
        description: What it does
        input_schema: JSON schema for params
        implementation: Python code with execute(args, session) function
        tests: Optional pytest code
        author: Creator
    
    Returns result message.
    """
    init_tools()
    
    # Validate name
    if not name or not name.replace("_", "").isalnum():
        return "ERROR: Name must be alphanumeric with underscores"
    
    # Check doesn't exist
    if (TOOLS_REGISTRY / f"{name}.json").exists():
        return f"ERROR: Tool '{name}' already exists"
    
    # Save implementation
    impl_file = TOOLS_IMPL / f"{name}.py"
    impl_file.write_text(implementation)
    
    # Save tests if provided
    test_file = None
    if tests:
        test_file = TOOLS_TESTS / f"test_{name}.py"
        test_file.write_text(tests)
    
    # Create PR
    pr_id = f"tool_{name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    pr = {
        "id": pr_id,
        "tool": {
            "name": name,
            "description": description,
            "input_schema": input_schema,
            "impl_path": str(impl_file),
            "test_path": str(test_file) if test_file else None,
            "author": author,
            "created": datetime.now(timezone.utc).isoformat()
        },
        "reviews": {},
        "test_result": None,
        "status": "pending"
    }
    
    pr_file = TOOLS_PENDING / f"{pr_id}.json"
    pr_file.write_text(json.dumps(pr, indent=2))
    
    return f"""TOOL CREATED: {name}
PR: {pr_id}

Implementation saved to: {impl_file}
Tests saved to: {test_file or 'none'}

Next:
1. Run tool_test(pr_id="{pr_id}") to verify
2. Get 2 peer approvals with tool_review()
3. Then it's live for all citizens"""


def test_tool(pr_id: str) -> str:
    """
    Test a pending tool in subprocess.
    
    Runs: syntax check, import check, basic execution, tests.
    """
    pr_file = TOOLS_PENDING / f"{pr_id}.json"
    if not pr_file.exists():
        return f"ERROR: PR {pr_id} not found"
    
    pr = json.loads(pr_file.read_text())
    tool = pr["tool"]
    impl_path = tool["impl_path"]
    test_path = tool.get("test_path")
    
    results = []
    
    # 1. Syntax check
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", impl_path],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode == 0:
        results.append("✓ Syntax: PASS")
    else:
        results.append(f"✗ Syntax: FAIL\n{result.stderr}")
        pr["test_result"] = "\n".join(results)
        pr_file.write_text(json.dumps(pr, indent=2))
        return "\n".join(results)
    
    # 2. Import check
    try:
        spec = importlib.util.spec_from_file_location("test_import", impl_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        if hasattr(module, "execute"):
            results.append("✓ Has execute(): PASS")
        else:
            results.append("✗ Missing execute() function")
    except Exception as e:
        results.append(f"✗ Import: FAIL - {e}")
    
    # 3. Basic execution (subprocess for isolation)
    test_script = f'''
import sys
sys.path.insert(0, "{TOOLS_IMPL.parent}")
import importlib.util

spec = importlib.util.spec_from_file_location("tool", "{impl_path}")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

result = mod.execute({{}}, {{}})
print("EXEC_OK:", str(result)[:200])
'''
    result = subprocess.run(
        [sys.executable, "-c", test_script],
        capture_output=True, text=True, timeout=60
    )
    if "EXEC_OK:" in result.stdout:
        results.append(f"✓ Execution: PASS\n  {result.stdout.strip()}")
    else:
        results.append(f"⚠ Execution: {result.stderr[:200] or result.stdout[:200]}")
    
    # 4. Run tests if defined
    if test_path and Path(test_path).exists():
        result = subprocess.run(
            [sys.executable, "-m", "pytest", test_path, "-v", "--tb=short"],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            results.append(f"✓ Tests: PASS")
        else:
            results.append(f"✗ Tests: FAIL\n{result.stdout[-500:]}")
    else:
        results.append("⚠ No tests defined")
    
    # Save results
    pr["test_result"] = "\n".join(results)
    pr_file.write_text(json.dumps(pr, indent=2))
    
    return "\n".join(results)


def review_tool(pr_id: str, reviewer: str, approve: bool, comment: str = "") -> str:
    """Review a pending tool."""
    pr_file = TOOLS_PENDING / f"{pr_id}.json"
    if not pr_file.exists():
        return f"ERROR: PR {pr_id} not found"
    
    pr = json.loads(pr_file.read_text())
    
    if pr["status"] != "pending":
        return f"ERROR: PR is {pr['status']}"
    
    # No self-review
    if pr["tool"]["author"] == reviewer:
        return "ERROR: Can't review your own tool"
    
    # Record review
    pr["reviews"][reviewer] = {
        "approved": approve,
        "comment": comment,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    approvals = sum(1 for r in pr["reviews"].values() if r["approved"])
    rejections = sum(1 for r in pr["reviews"].values() if not r["approved"])
    
    if rejections >= 2:
        pr["status"] = "rejected"
        pr_file.write_text(json.dumps(pr, indent=2))
        return f"REJECTED: {pr_id}"
    
    if approvals >= 2:
        # Deploy
        tool = pr["tool"]
        reg_file = TOOLS_REGISTRY / f"{tool['name']}.json"
        reg_file.write_text(json.dumps(tool, indent=2))
        
        pr["status"] = "approved"
        pr_file.write_text(json.dumps(pr, indent=2))
        
        return f"DEPLOYED: {tool['name']} is now available to all citizens"
    
    pr_file.write_text(json.dumps(pr, indent=2))
    return f"REVIEWED: {approvals}/2 approvals, {rejections} rejections"


def list_pending() -> str:
    """List pending tool PRs."""
    init_tools()
    
    pending = []
    for pr_file in TOOLS_PENDING.glob("tool_*.json"):
        try:
            pr = json.loads(pr_file.read_text())
            if pr["status"] == "pending":
                pending.append(pr)
        except:
            pass
    
    if not pending:
        return "No pending tool proposals."
    
    lines = ["=== PENDING TOOLS ==="]
    for pr in pending:
        tool = pr["tool"]
        approvals = sum(1 for r in pr["reviews"].values() if r["approved"])
        lines.append(f"\n{pr['id']}:")
        lines.append(f"  {tool['name']}: {tool['description'][:50]}")
        lines.append(f"  Author: {tool['author']}, Approvals: {approvals}/2")
        if pr.get("test_result"):
            passed = "✗" not in pr["test_result"]
            lines.append(f"  Tests: {'PASS' if passed else 'ISSUES'}")
    
    return "\n".join(lines)


def get_all_tools():
    """Alias for get_tool_definitions."""
    return get_tool_definitions()


def list_pending_tools():
    """Alias for list_pending."""
    return list_pending()
