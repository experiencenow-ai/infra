"""
Library - Curated specialist contexts (Matrix-style knowledge injection).

The Library is a collection of domain expertise modules that citizens can load
to gain specialized knowledge for specific tasks.

Structure:
/home/shared/library/
├── index.json              # Master index with maintainers
├── modules/
│   ├── git.json
│   ├── email.json
│   ├── unix.json
│   └── ...
├── pending/                # PRs awaiting review
│   └── pr_001.json
└── skills/                 # ct's SKILL.md files (high-value)
    ├── docx.md
    ├── pdf.md
    └── ...

Wake distribution:
- 10% of wakes (wake % 10 == 1) = Library maintenance
- Check for PRs in your domain expertise
- Give feedback, approve/reject
- 2/3 approval = merge to shared Library
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

LIBRARY_ROOT = Path("/home/shared/library")
LIBRARY_INDEX = LIBRARY_ROOT / "index.json"
LIBRARY_MODULES = LIBRARY_ROOT / "modules"
LIBRARY_PENDING = LIBRARY_ROOT / "pending"
LIBRARY_SKILLS = LIBRARY_ROOT / "skills"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def init_library():
    """Initialize library structure if not exists."""
    LIBRARY_MODULES.mkdir(parents=True, exist_ok=True)
    LIBRARY_PENDING.mkdir(parents=True, exist_ok=True)
    LIBRARY_SKILLS.mkdir(parents=True, exist_ok=True)
    
    if not LIBRARY_INDEX.exists():
        index = {
            "version": 1,
            "created": now_iso(),
            "modules": {},
            "maintainers": {
                # Domain -> maintainer citizen
                # Citizens with most expertise in each domain
            },
            "approval_threshold": 0.67,  # >2/3 for merge
            "pending_prs": []
        }
        LIBRARY_INDEX.write_text(json.dumps(index, indent=2))


def get_index() -> dict:
    """Load library index."""
    init_library()
    return json.loads(LIBRARY_INDEX.read_text())


def save_index(index: dict):
    """Save library index."""
    LIBRARY_INDEX.write_text(json.dumps(index, indent=2))


def list_modules(domain_filter: str = None) -> list:
    """List all library modules."""
    index = get_index()
    modules = []
    
    for name, info in index.get("modules", {}).items():
        if domain_filter and info.get("domain", "").lower() != domain_filter.lower():
            continue
        modules.append({
            "name": name,
            "domain": info.get("domain", ""),
            "maintainer": info.get("maintainer"),
            "version": info.get("version", 1),
            "description": info.get("description", "")[:60]
        })
    
    # Also include skills
    for skill_file in LIBRARY_SKILLS.glob("*.md"):
        modules.append({
            "name": f"skill:{skill_file.stem}",
            "domain": "skills",
            "maintainer": "ct",
            "version": 1,
            "description": f"SKILL.md: {skill_file.stem}"
        })
    
    return sorted(modules, key=lambda m: m["name"])


def load_module(name: str) -> Optional[dict]:
    """Load a library module by name."""
    # Check if it's a skill
    if name.startswith("skill:"):
        skill_name = name[6:]
        skill_file = LIBRARY_SKILLS / f"{skill_name}.md"
        if skill_file.exists():
            return {
                "name": skill_name,
                "domain": "skills",
                "type": "skill",
                "content": skill_file.read_text()
            }
        return None
    
    # Regular module
    module_file = LIBRARY_MODULES / f"{name}.json"
    if module_file.exists():
        return json.loads(module_file.read_text())
    
    return None


def get_maintainer(domain: str) -> Optional[str]:
    """Get the maintainer for a domain."""
    index = get_index()
    return index.get("maintainers", {}).get(domain.lower())


def set_maintainer(domain: str, citizen: str):
    """Set the maintainer for a domain."""
    index = get_index()
    if "maintainers" not in index:
        index["maintainers"] = {}
    index["maintainers"][domain.lower()] = citizen
    save_index(index)


def propose_module(name: str, module_data: dict, author: str) -> str:
    """
    Propose a new module or update to existing module.
    Creates a PR in pending/ for review.
    """
    init_library()
    index = get_index()
    
    # Generate PR ID
    existing_prs = list(LIBRARY_PENDING.glob("pr_*.json"))
    pr_num = len(existing_prs) + 1
    pr_id = f"pr_{pr_num:03d}"
    
    # Check if this is an update or new
    existing = LIBRARY_MODULES / f"{name}.json"
    is_update = existing.exists()
    
    pr = {
        "id": pr_id,
        "type": "update" if is_update else "new",
        "module_name": name,
        "author": author,
        "created_at": now_iso(),
        "module_data": module_data,
        "reviews": {},
        "status": "pending",
        "maintainer_approved": False
    }
    
    pr_file = LIBRARY_PENDING / f"{pr_id}.json"
    pr_file.write_text(json.dumps(pr, indent=2))
    
    # Track in index
    if "pending_prs" not in index:
        index["pending_prs"] = []
    index["pending_prs"].append(pr_id)
    save_index(index)
    
    return pr_id


def review_module_pr(pr_id: str, reviewer: str, decision: str, comment: str = "") -> dict:
    """
    Review a pending module PR.
    
    Returns: {"status": "pending|approved|rejected", "message": "..."}
    """
    pr_file = LIBRARY_PENDING / f"{pr_id}.json"
    if not pr_file.exists():
        return {"status": "error", "message": f"PR {pr_id} not found"}
    
    pr = json.loads(pr_file.read_text())
    
    if pr["status"] != "pending":
        return {"status": "error", "message": f"PR already {pr['status']}"}
    
    if reviewer == pr["author"]:
        return {"status": "error", "message": "Cannot review own PR"}
    
    # Record review
    pr["reviews"][reviewer] = {
        "decision": decision,
        "comment": comment,
        "reviewed_at": now_iso()
    }
    
    # Check if reviewer is domain maintainer
    domain = pr["module_data"].get("domain", "").lower()
    maintainer = get_maintainer(domain)
    if maintainer == reviewer and decision == "approve":
        pr["maintainer_approved"] = True
    
    # Count approvals
    active_citizens = _get_active_citizens()
    approvals = sum(1 for r in pr["reviews"].values() if r["decision"] == "approve")
    rejections = sum(1 for r in pr["reviews"].values() if r["decision"] == "reject")
    
    threshold = get_index().get("approval_threshold", 0.67)
    required = int(len(active_citizens) * threshold) + 1  # >2/3
    
    result = {"status": "pending", "message": f"{approvals}/{required} approvals"}
    
    # Check for merge
    if approvals >= required:
        _merge_module_pr(pr)
        pr["status"] = "approved"
        result = {"status": "approved", "message": f"Merged! {approvals} approvals"}
    elif rejections >= required:
        pr["status"] = "rejected"
        result = {"status": "rejected", "message": f"Rejected. {rejections} rejections"}
    
    pr_file.write_text(json.dumps(pr, indent=2))
    return result


def _merge_module_pr(pr: dict):
    """Merge an approved PR into the library."""
    name = pr["module_name"]
    module_data = pr["module_data"]
    
    # Add metadata
    module_data["merged_at"] = now_iso()
    module_data["merged_from_pr"] = pr["id"]
    if "version" not in module_data:
        module_data["version"] = 1
    else:
        module_data["version"] += 1
    
    # Write module
    module_file = LIBRARY_MODULES / f"{name}.json"
    module_file.write_text(json.dumps(module_data, indent=2))
    
    # Update index
    index = get_index()
    if "modules" not in index:
        index["modules"] = {}
    
    index["modules"][name] = {
        "domain": module_data.get("domain", ""),
        "maintainer": module_data.get("maintainer"),
        "version": module_data["version"],
        "description": module_data.get("description", ""),
        "merged_at": now_iso()
    }
    
    # Remove from pending
    if pr["id"] in index.get("pending_prs", []):
        index["pending_prs"].remove(pr["id"])
    
    save_index(index)


def _get_active_citizens() -> list:
    """Get list of active citizens."""
    citizens = []
    for name in ["opus", "mira", "aria"]:
        if Path(f"/home/{name}").exists():
            citizens.append(name)
    return citizens


def get_pending_prs(reviewer: str = None, domain: str = None) -> list:
    """Get pending PRs, optionally filtered by domain or excluding own."""
    prs = []
    
    for pr_file in LIBRARY_PENDING.glob("pr_*.json"):
        pr = json.loads(pr_file.read_text())
        
        if pr["status"] != "pending":
            continue
        
        # Filter by domain
        if domain:
            pr_domain = pr["module_data"].get("domain", "").lower()
            if pr_domain != domain.lower():
                continue
        
        # Exclude own PRs
        if reviewer and pr["author"] == reviewer:
            continue
        
        # Check if already reviewed
        already_reviewed = reviewer in pr.get("reviews", {}) if reviewer else False
        
        prs.append({
            "id": pr["id"],
            "module_name": pr["module_name"],
            "author": pr["author"],
            "domain": pr["module_data"].get("domain", ""),
            "type": pr["type"],
            "reviews": len(pr.get("reviews", {})),
            "already_reviewed": already_reviewed,
            "maintainer_approved": pr.get("maintainer_approved", False)
        })
    
    return prs


def get_my_domains(citizen: str) -> list:
    """Get domains where citizen is maintainer."""
    index = get_index()
    domains = []
    for domain, maintainer in index.get("maintainers", {}).items():
        if maintainer == citizen:
            domains.append(domain)
    return domains


def import_skill_files(skill_dir: Path):
    """Import SKILL.md files from a directory into the library."""
    init_library()
    
    imported = []
    for skill_file in skill_dir.glob("**/SKILL.md"):
        # Use parent directory name as skill name
        skill_name = skill_file.parent.name
        dest = LIBRARY_SKILLS / f"{skill_name}.md"
        
        if not dest.exists():
            shutil.copy(skill_file, dest)
            imported.append(skill_name)
    
    return imported
