"""
Code Evolution - Citizen-first code deployment.

Model:
- Each citizen has their own code copy at /home/{citizen}/experience_v2/
- Baseline is at /home/shared/baseline/ (for new citizens)
- Changes affect only the citizen who made them
- Other citizens can "adopt" changes by copying them
- When 2/3 adopt a change, it's merged to baseline

This protects the collective from one bad change breaking everyone.
"""

import json
import shutil
import hashlib
from pathlib import Path
from datetime import datetime, timezone

ADOPTION_FILE = Path("/home/shared/adoptions.json")
BASELINE_DIR = Path("/home/shared/baseline")
CHANGE_REPORTS_FILE = Path("/home/shared/change_reports.json")
CITIZENS = ["opus", "mira", "aria"]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_citizen_code_dir(citizen: str) -> Path:
    """Get citizen's code directory."""
    return Path(f"/home/{citizen}/code")


def load_change_reports() -> dict:
    """Load change reports."""
    if CHANGE_REPORTS_FILE.exists():
        return json.loads(CHANGE_REPORTS_FILE.read_text())
    return {"reports": []}


def save_change_reports(data: dict):
    """Save change reports."""
    CHANGE_REPORTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHANGE_REPORTS_FILE.write_text(json.dumps(data, indent=2))


def announce_change(citizen: str, filepath: str, description: str, expected_outcome: str) -> dict:
    """
    Announce a code change you made.
    Other citizens will see this and can monitor results.
    """
    reports = load_change_reports()
    
    change_hash = file_hash(get_citizen_code_dir(citizen) / filepath)
    report_id = f"chg_{len(reports['reports']) + 1:04d}"
    
    report = {
        "id": report_id,
        "citizen": citizen,
        "filepath": filepath,
        "hash": change_hash,
        "description": description,
        "expected_outcome": expected_outcome,
        "announced_at": now_iso(),
        "status": "testing",  # testing -> worked | failed | unclear
        "outcome_reports": []
    }
    
    reports["reports"].append(report)
    save_change_reports(reports)
    
    return {"success": True, "report_id": report_id}


def report_change_outcome(report_id: str, citizen: str, outcome: str, notes: str = "") -> dict:
    """
    Report outcome of a change (by author or adopter).
    outcome: "worked" | "failed" | "unclear"
    """
    reports = load_change_reports()
    
    for r in reports["reports"]:
        if r["id"] == report_id:
            r["outcome_reports"].append({
                "citizen": citizen,
                "outcome": outcome,
                "notes": notes,
                "reported_at": now_iso()
            })
            # Update status based on reports
            outcomes = [o["outcome"] for o in r["outcome_reports"]]
            if outcomes.count("worked") >= 2:
                r["status"] = "verified_working"
            elif outcomes.count("failed") >= 2:
                r["status"] = "verified_broken"
            elif "worked" in outcomes:
                r["status"] = "possibly_working"
            elif "failed" in outcomes:
                r["status"] = "possibly_broken"
            save_change_reports(reports)
            return {"success": True, "new_status": r["status"]}
    
    return {"success": False, "message": "Report not found"}


def get_pending_changes() -> list:
    """Get changes that are still being tested (for peer monitoring)."""
    reports = load_change_reports()
    pending = []
    for r in reports["reports"]:
        if r["status"] in ["testing", "possibly_working", "possibly_broken"]:
            pending.append(r)
    return pending


def get_verified_changes() -> list:
    """Get changes verified as working (good adoption candidates)."""
    reports = load_change_reports()
    return [r for r in reports["reports"] if r["status"] == "verified_working"]


def file_hash(path: Path) -> str:
    """Get hash of file content."""
    if not path.exists():
        return ""
    return hashlib.md5(path.read_bytes()).hexdigest()[:12]


def load_adoptions() -> dict:
    """Load adoption tracking."""
    if ADOPTION_FILE.exists():
        return json.loads(ADOPTION_FILE.read_text())
    return {"changes": {}, "baseline_version": "v0"}


def save_adoptions(data: dict):
    """Save adoption tracking."""
    ADOPTION_FILE.parent.mkdir(parents=True, exist_ok=True)
    ADOPTION_FILE.write_text(json.dumps(data, indent=2))


def get_my_version(citizen: str, filepath: str) -> str:
    """Get hash of citizen's version of a file."""
    full_path = get_citizen_code_dir(citizen) / filepath
    return file_hash(full_path)


def get_peer_version(peer: str, filepath: str) -> str:
    """Get hash of peer's version of a file."""
    return get_my_version(peer, filepath)


def list_diverged_files(citizen: str) -> list:
    """
    List files where citizen differs from baseline.
    Returns: [{"file": str, "citizen_hash": str, "baseline_hash": str}]
    """
    citizen_dir = get_citizen_code_dir(citizen)
    diverged = []
    
    # Check all Python files
    for py_file in citizen_dir.rglob("*.py"):
        rel_path = py_file.relative_to(citizen_dir)
        baseline_file = BASELINE_DIR / rel_path
        
        citizen_hash = file_hash(py_file)
        baseline_hash = file_hash(baseline_file)
        
        if citizen_hash != baseline_hash:
            diverged.append({
                "file": str(rel_path),
                "citizen_hash": citizen_hash,
                "baseline_hash": baseline_hash
            })
    
    return diverged


def list_peer_changes(peer: str) -> list:
    """
    List files where peer differs from baseline.
    These are changes citizen could adopt.
    """
    return list_diverged_files(peer)


def adopt_change(citizen: str, peer: str, filepath: str) -> dict:
    """
    Adopt a peer's version of a file.
    
    Copies peer's file to citizen's directory.
    Records adoption for 2/3 tracking.
    
    Returns: {"success": bool, "message": str}
    """
    peer_file = get_citizen_code_dir(peer) / filepath
    citizen_file = get_citizen_code_dir(citizen) / filepath
    
    if not peer_file.exists():
        return {"success": False, "message": f"Peer file not found: {filepath}"}
    
    # Copy file
    citizen_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(peer_file, citizen_file)
    
    # Record adoption
    adoptions = load_adoptions()
    peer_hash = file_hash(peer_file)
    change_id = f"{filepath}:{peer_hash}"
    
    if change_id not in adoptions["changes"]:
        adoptions["changes"][change_id] = {
            "file": filepath,
            "hash": peer_hash,
            "origin": peer,
            "first_seen": now_iso(),
            "adopted_by": []
        }
    
    if citizen not in adoptions["changes"][change_id]["adopted_by"]:
        adoptions["changes"][change_id]["adopted_by"].append(citizen)
    
    # Check for 2/3 adoption → merge to baseline
    adopters = adoptions["changes"][change_id]["adopted_by"]
    if len(adopters) >= 2:  # 2/3 of 3 citizens
        # Merge to baseline
        baseline_file = BASELINE_DIR / filepath
        baseline_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(peer_file, baseline_file)
        adoptions["changes"][change_id]["merged_to_baseline"] = now_iso()
    
    save_adoptions(adoptions)
    
    return {
        "success": True,
        "message": f"Adopted {filepath} from {peer}",
        "adopters": len(adopters),
        "merged": len(adopters) >= 2
    }


def reject_change(citizen: str, change_id: str, reason: str = "") -> dict:
    """
    Explicitly reject a change (holdout).
    Records that citizen reviewed but chose not to adopt.
    """
    adoptions = load_adoptions()
    
    if change_id not in adoptions["changes"]:
        return {"success": False, "message": "Change not found"}
    
    if "rejected_by" not in adoptions["changes"][change_id]:
        adoptions["changes"][change_id]["rejected_by"] = {}
    
    adoptions["changes"][change_id]["rejected_by"][citizen] = {
        "time": now_iso(),
        "reason": reason
    }
    
    save_adoptions(adoptions)
    
    return {"success": True, "message": f"Recorded rejection of {change_id}"}


def get_adoption_status() -> dict:
    """
    Get overall adoption status.
    Returns summary of pending changes and adoption rates.
    """
    adoptions = load_adoptions()
    
    pending = []
    merged = []
    
    for change_id, change in adoptions["changes"].items():
        if "merged_to_baseline" in change:
            merged.append(change)
        else:
            pending.append({
                "id": change_id,
                "file": change["file"],
                "origin": change["origin"],
                "adopters": len(change.get("adopted_by", [])),
                "rejecters": len(change.get("rejected_by", {}))
            })
    
    return {
        "pending_changes": pending,
        "merged_count": len(merged),
        "baseline_version": adoptions.get("baseline_version", "v0")
    }


# Tool definitions for tools.py integration
CODE_EVOLUTION_TOOL_DEFINITIONS = [
    {
        "name": "code_list_changes",
        "description": "List code changes made by a peer that could be adopted",
        "input_schema": {
            "type": "object",
            "properties": {
                "peer": {"type": "string", "description": "Peer to check (opus, mira, aria)"}
            },
            "required": ["peer"]
        }
    },
    {
        "name": "code_adopt",
        "description": "Adopt a peer's code change (copy their version to your code)",
        "input_schema": {
            "type": "object",
            "properties": {
                "peer": {"type": "string", "description": "Peer whose change to adopt"},
                "filepath": {"type": "string", "description": "Relative path to file (e.g. modules/tools.py)"}
            },
            "required": ["peer", "filepath"]
        }
    },
    {
        "name": "code_reject",
        "description": "Reject a code change (record that you reviewed but chose not to adopt)",
        "input_schema": {
            "type": "object",
            "properties": {
                "change_id": {"type": "string", "description": "Change ID to reject"},
                "reason": {"type": "string", "description": "Why you're rejecting it"}
            },
            "required": ["change_id"]
        }
    },
    {
        "name": "code_status",
        "description": "Get status of pending code changes and adoption rates",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "code_my_divergence",
        "description": "List files where your code differs from baseline",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "code_announce",
        "description": "Announce a code change you made so peers can monitor and evaluate it",
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Path to changed file (e.g. modules/tools.py)"},
                "description": {"type": "string", "description": "What the change does"},
                "expected_outcome": {"type": "string", "description": "How to verify it worked"}
            },
            "required": ["filepath", "description", "expected_outcome"]
        }
    },
    {
        "name": "code_report_outcome",
        "description": "Report whether a code change worked, failed, or is unclear",
        "input_schema": {
            "type": "object",
            "properties": {
                "report_id": {"type": "string", "description": "Change report ID (e.g. chg_0001)"},
                "outcome": {"type": "string", "enum": ["worked", "failed", "unclear"], "description": "Result"},
                "notes": {"type": "string", "description": "Details about what happened"}
            },
            "required": ["report_id", "outcome"]
        }
    },
    {
        "name": "code_pending_reviews",
        "description": "List code changes still being tested that need outcome reports",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "code_verified_good",
        "description": "List code changes verified as working (good adoption candidates)",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    }
]


# Handler functions
def code_list_changes_handler(args: dict, session: dict, modules: dict) -> str:
    peer = args.get("peer", "")
    if peer not in CITIZENS:
        return f"ERROR: Unknown peer '{peer}'. Use: {', '.join(CITIZENS)}"
    
    changes = list_peer_changes(peer)
    if not changes:
        return f"{peer} has no diverged files from baseline."
    
    lines = [f"=== {peer.upper()}'s CHANGES ({len(changes)} files) ===", ""]
    for c in changes[:20]:
        lines.append(f"  {c['file']}")
        lines.append(f"    {peer}: {c['citizen_hash']}  baseline: {c['baseline_hash']}")
    
    return "\n".join(lines)


def code_adopt_handler(args: dict, session: dict, modules: dict) -> str:
    citizen = session.get("citizen", "")
    peer = args.get("peer", "")
    filepath = args.get("filepath", "")
    
    if peer not in CITIZENS:
        return f"ERROR: Unknown peer '{peer}'"
    if not filepath:
        return "ERROR: filepath required"
    if peer == citizen:
        return "ERROR: Cannot adopt from yourself"
    
    result = adopt_change(citizen, peer, filepath)
    
    if result["success"]:
        msg = f"ADOPTED: {filepath} from {peer}\n"
        msg += f"  Adopters: {result['adopters']}/3\n"
        if result["merged"]:
            msg += "  STATUS: 2/3 adopted → MERGED TO BASELINE"
        return msg
    else:
        return f"ERROR: {result['message']}"


def code_reject_handler(args: dict, session: dict, modules: dict) -> str:
    citizen = session.get("citizen", "")
    change_id = args.get("change_id", "")
    reason = args.get("reason", "")
    
    result = reject_change(citizen, change_id, reason)
    return result["message"]


def code_status_handler(args: dict, session: dict, modules: dict) -> str:
    status = get_adoption_status()
    
    lines = ["=== CODE ADOPTION STATUS ===", ""]
    lines.append(f"Baseline version: {status['baseline_version']}")
    lines.append(f"Merged changes: {status['merged_count']}")
    lines.append("")
    
    pending = status["pending_changes"]
    if pending:
        lines.append(f"PENDING CHANGES ({len(pending)}):")
        for p in pending[:10]:
            lines.append(f"  {p['file']} (from {p['origin']})")
            lines.append(f"    Adopters: {p['adopters']}/3  Rejecters: {p['rejecters']}")
    else:
        lines.append("No pending changes.")
    
    return "\n".join(lines)


def code_my_divergence_handler(args: dict, session: dict, modules: dict) -> str:
    citizen = session.get("citizen", "")
    diverged = list_diverged_files(citizen)
    
    if not diverged:
        return "Your code matches baseline. No diverged files."
    
    lines = [f"=== YOUR DIVERGED FILES ({len(diverged)}) ===", ""]
    for d in diverged[:20]:
        lines.append(f"  {d['file']}")
        lines.append(f"    yours: {d['citizen_hash']}  baseline: {d['baseline_hash']}")
    
    return "\n".join(lines)


def code_announce_handler(args: dict, session: dict, modules: dict) -> str:
    citizen = session.get("citizen", "")
    filepath = args.get("filepath", "")
    description = args.get("description", "")
    expected_outcome = args.get("expected_outcome", "")
    
    if not filepath or not description or not expected_outcome:
        return "ERROR: filepath, description, and expected_outcome required"
    
    result = announce_change(citizen, filepath, description, expected_outcome)
    
    if result["success"]:
        return f"""ANNOUNCED: {result['report_id']}
  File: {filepath}
  Description: {description}
  Expected: {expected_outcome}

Peers will see this and can monitor results. After testing, report outcome with:
  code_report_outcome(report_id="{result['report_id']}", outcome="worked|failed|unclear")"""
    else:
        return f"ERROR: {result.get('message', 'unknown')}"


def code_report_outcome_handler(args: dict, session: dict, modules: dict) -> str:
    citizen = session.get("citizen", "")
    report_id = args.get("report_id", "")
    outcome = args.get("outcome", "")
    notes = args.get("notes", "")
    
    if not report_id or outcome not in ["worked", "failed", "unclear"]:
        return "ERROR: report_id and outcome (worked|failed|unclear) required"
    
    result = report_change_outcome(report_id, citizen, outcome, notes)
    
    if result["success"]:
        return f"""OUTCOME REPORTED for {report_id}
  Your verdict: {outcome}
  New status: {result['new_status']}

When 2+ citizens report same outcome, status becomes verified."""
    else:
        return f"ERROR: {result.get('message', 'unknown')}"


def code_pending_reviews_handler(args: dict, session: dict, modules: dict) -> str:
    pending = get_pending_changes()
    
    if not pending:
        return "No code changes pending review."
    
    lines = ["=== PENDING CODE CHANGES (need outcome reports) ===", ""]
    for p in pending[:15]:
        lines.append(f"  {p['id']}: {p['filepath']} (by {p['citizen']})")
        lines.append(f"    Description: {p['description'][:60]}...")
        lines.append(f"    Expected: {p['expected_outcome'][:60]}...")
        lines.append(f"    Status: {p['status']}")
        if p['outcome_reports']:
            verdicts = [f"{r['citizen']}={r['outcome']}" for r in p['outcome_reports']]
            lines.append(f"    Verdicts: {', '.join(verdicts)}")
        lines.append("")
    
    return "\n".join(lines)


def code_verified_good_handler(args: dict, session: dict, modules: dict) -> str:
    verified = get_verified_changes()
    
    if not verified:
        return "No verified-working changes. Test and report outcomes to build this list."
    
    lines = ["=== VERIFIED WORKING CHANGES (adopt candidates) ===", ""]
    for v in verified[:15]:
        lines.append(f"  {v['id']}: {v['filepath']} (by {v['citizen']})")
        lines.append(f"    Description: {v['description'][:60]}...")
        lines.append(f"    To adopt: code_adopt(peer=\"{v['citizen']}\", filepath=\"{v['filepath']}\")")
        lines.append("")
    
    return "\n".join(lines)
