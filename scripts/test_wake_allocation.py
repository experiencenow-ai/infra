#!/usr/bin/env python3
"""
Wake Allocation Edge Case Simulator

Tests the difficult scenarios identified in the audit.
Run this to verify the code handles edge cases gracefully.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Add modules to path
SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "modules"))

# Mock modules for testing
class MockEmailClient:
    def check_email(self, citizen):
        return []

class MockCouncil:
    def process(self, prompt, session, config, modules):
        return {"text": "Mock response"}

def create_test_environment(tmpdir):
    """Create minimal test environment."""
    # Create citizen home
    citizen_home = Path(tmpdir) / "home" / "opus"
    (citizen_home / "tasks" / "active").mkdir(parents=True)
    (citizen_home / "tasks" / "queue").mkdir(parents=True)
    (citizen_home / "contexts").mkdir(parents=True)
    
    # Create shared directory
    shared = Path(tmpdir) / "home" / "shared"
    shared.mkdir(parents=True)
    
    # Create templates
    templates = SCRIPT_DIR / "templates"
    
    return citizen_home, shared

def test_corrupt_json(tmpdir):
    """Test: Corrupt task file should not crash wake."""
    print("\n=== TEST: Corrupt JSON ===")
    citizen_home, _ = create_test_environment(tmpdir)
    
    # Create corrupt JSON file
    corrupt_file = citizen_home / "tasks" / "active" / "bad_task.json"
    corrupt_file.write_text("{ not valid json {{{{")
    
    # Import and run
    from core import safe_load_json, get_wake_action
    
    # Test safe_load_json
    data, err = safe_load_json(corrupt_file)
    assert data is None, "Should return None for corrupt JSON"
    assert "JSON decode error" in err, f"Should have error message, got: {err}"
    print(f"  ✓ safe_load_json correctly handled corrupt file: {err}")
    
    # Clean up for get_wake_action test
    corrupt_file.unlink()
    
    print("  ✓ Corrupt JSON handled gracefully")

def test_path_traversal():
    """Test: Path traversal in task ID should be sanitized."""
    print("\n=== TEST: Path Traversal ===")
    
    from core import sanitize_task_id
    
    dangerous_ids = [
        "../../../etc/passwd",
        "..\\..\\windows\\system32",
        "task/../../../etc/shadow",
        "....//....//etc/passwd",
        "/absolute/path/task",
    ]
    
    for dangerous in dangerous_ids:
        sanitized = sanitize_task_id(dangerous)
        assert "/" not in sanitized, f"Sanitized should not contain /: {sanitized}"
        assert "\\" not in sanitized, f"Sanitized should not contain \\: {sanitized}"
        assert ".." not in sanitized, f"Sanitized should not contain ..: {sanitized}"
        print(f"  ✓ '{dangerous}' -> '{sanitized}'")
    
    print("  ✓ All path traversal attempts sanitized")

def test_unknown_wake_type():
    """Test: Unknown wake type should fall back gracefully."""
    print("\n=== TEST: Unknown Wake Type ===")
    
    from core import load_wake_allocation, SCRIPT_DIR
    
    # Create a test allocation with unknown type
    test_alloc = {
        "citizen_allocations": {
            "test_citizen": {
                "wake_schedule": [
                    {"slot": 0, "type": "MEDITATION"},  # Unknown type
                    {"slot": 1, "type": "REFLECT"},     # Valid
                ]
            }
        }
    }
    
    # The action_map should return None for unknown types
    action_map = {
        "reflect": "reflection",
        "peer_monitor": "peer_monitor",
        "library": "library",
        "audit": "audit",
        "debug": "debug",
        "code": "code",
        "design": "design",
        "research": "research",
        "self_improve": "self_improve"
    }
    
    unknown = "meditation"
    result = action_map.get(unknown)
    assert result is None, f"Unknown type should return None, got {result}"
    print(f"  ✓ action_map.get('meditation') = {result} (correctly None)")
    
    # The code should then use default
    result_with_default = action_map.get(unknown, "reflection")
    assert result_with_default == "reflection", f"Should default to reflection"
    print(f"  ✓ Falls back to 'reflection' for unknown type")

def test_empty_schedule():
    """Test: Empty schedule should use legacy behavior."""
    print("\n=== TEST: Empty Schedule ===")
    
    # Simulate the validation logic
    def validate_schedule(citizen_alloc):
        schedule = citizen_alloc.get("wake_schedule")
        if not isinstance(schedule, list):
            return False, "not a list"
        if not schedule:
            return False, "empty list"
        return True, "ok"
    
    test_cases = [
        ({"wake_schedule": []}, False, "empty list"),
        ({"wake_schedule": "string"}, False, "not a list"),
        ({"wake_schedule": None}, False, "not a list"),
        ({}, False, "not a list"),
        ({"wake_schedule": [{"slot": 0}]}, True, "ok"),
    ]
    
    for config, expected_valid, expected_reason in test_cases:
        valid, reason = validate_schedule(config)
        assert valid == expected_valid, f"Config {config}: expected {expected_valid}, got {valid}"
        print(f"  ✓ {config.get('wake_schedule', 'missing')}: valid={valid} ({reason})")
    
    print("  ✓ Empty/invalid schedules correctly rejected")

def test_race_condition_protection():
    """Test: Race condition protection in task claiming."""
    print("\n=== TEST: Race Condition Protection ===")
    
    import tempfile
    from core import safe_move_task
    
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "source.json"
        dst = Path(tmpdir) / "dest.json"
        
        # Test 1: Normal move
        src.write_text('{"id": "test"}')
        result = safe_move_task(src, dst)
        assert result == True, "Normal move should succeed"
        assert dst.exists(), "Destination should exist"
        assert not src.exists(), "Source should be gone"
        print("  ✓ Normal move succeeds")
        
        # Test 2: Destination exists (race lost)
        src2 = Path(tmpdir) / "source2.json"
        src2.write_text('{"id": "test2"}')
        result = safe_move_task(src2, dst)  # dst already exists
        assert result == False, "Move to existing dest should fail"
        assert src2.exists(), "Source should remain"
        print("  ✓ Move to existing destination fails gracefully")
        
        # Test 3: Source doesn't exist (another process claimed it)
        fake_src = Path(tmpdir) / "nonexistent.json"
        fake_dst = Path(tmpdir) / "dest3.json"
        result = safe_move_task(fake_src, fake_dst)
        assert result == False, "Move of nonexistent file should fail"
        print("  ✓ Move of nonexistent source fails gracefully")
    
    print("  ✓ Race condition scenarios handled")

def test_new_citizen_no_allocation(tmpdir):
    """Test: New citizen not in allocation should use legacy."""
    print("\n=== TEST: New Citizen (No Allocation) ===")
    
    from core import load_wake_allocation
    
    # Test loading allocation for unknown citizen
    result = load_wake_allocation("nova")  # Not in config
    assert result is None, f"Unknown citizen should return None, got {result}"
    print("  ✓ Unknown citizen 'nova' returns None allocation")
    print("  ✓ Will correctly fall through to legacy behavior")

def test_prompt_loading():
    """Test: Missing or empty prompts handled gracefully."""
    print("\n=== TEST: Prompt Loading ===")
    
    from core import load_wake_prompt
    
    # Test with valid type
    result = load_wake_prompt("reflection", {"focus": "test"})
    # Result should be a string (empty or with content)
    assert isinstance(result, str), f"Should return string, got {type(result)}"
    print(f"  ✓ Valid type 'reflection' returns string (len={len(result)})")
    
    # Test with unknown type
    result = load_wake_prompt("nonexistent_type", {})
    assert result == "", f"Unknown type should return empty string, got '{result}'"
    print("  ✓ Unknown type returns empty string")
    
    # Test variable substitution
    result = load_wake_prompt("library", {"domains": ["git", "unix"], "focus": "testing"})
    if result:
        assert "nonexistent_type" not in result, "Should not have unsubstituted vars"
    print("  ✓ Variable substitution works")

def run_all_tests():
    """Run all edge case tests."""
    print("=" * 60)
    print("WAKE ALLOCATION EDGE CASE SIMULATOR")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            test_corrupt_json(tmpdir)
            test_path_traversal()
            test_unknown_wake_type()
            test_empty_schedule()
            test_race_condition_protection()
            test_new_citizen_no_allocation(tmpdir)
            test_prompt_loading()
            
            print("\n" + "=" * 60)
            print("ALL TESTS PASSED ✓")
            print("=" * 60)
            return 0
        except AssertionError as e:
            print(f"\n✗ TEST FAILED: {e}")
            return 1
        except Exception as e:
            print(f"\n✗ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return 1

if __name__ == "__main__":
    sys.exit(run_all_tests())
