import json
from pathlib import Path
from typing import Any, Optional


STANDARD_FILES = {
    "prd": "prd.md",
    "manifest": "manifest.json",
    "review": "review.md",
    "escalation": "escalation.md",
    "change_request": "change_request.md",
    "vote_result": "vote_result.json",
    "status_pass": "status_pass.flag",
    "execution_errors": "execution_errors.log",
}

STATUS_VALUES = ("pending", "in_progress", "pass", "fail", "blocked")


def load_manifest(directory: Path) -> Optional[dict]:
    manifest_path = directory / STANDARD_FILES["manifest"]
    if not manifest_path.exists():
        return None
    with open(manifest_path, "r") as f:
        return json.load(f)


def save_manifest(directory: Path, manifest: dict) -> None:
    manifest_path = directory / STANDARD_FILES["manifest"]
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)


def create_manifest(deliverables: list[dict]) -> dict:
    """Create a new manifest.json structure.

    Each deliverable dict should have:
        - name: str (file or directory name)
        - type: "file" | "directory"
        - description: str
    Optional:
        - risk: "low" | "medium" | "high"
        - mode: "single" | "parallel"
        - candidates: list[str]  (only if mode == "parallel")
    """
    return {
        "deliverables": [
            {
                "name": d["name"],
                "type": d.get("type", "file"),
                "description": d.get("description", ""),
                "status": "pending",
                "fail_count": 0,
                "risk": d.get("risk", "low"),
                "mode": d.get("mode", "single"),
                "candidates": d.get("candidates", []),
            }
            for d in deliverables
        ]
    }


def update_status(directory: Path, deliverable_name: str, status: str) -> dict:
    assert status in STATUS_VALUES, f"Invalid status: {status}"
    manifest = load_manifest(directory)
    if manifest is None:
        raise FileNotFoundError(f"No manifest.json in {directory}")

    for d in manifest["deliverables"]:
        if d["name"] == deliverable_name:
            d["status"] = status
            if status == "fail":
                d["fail_count"] = d.get("fail_count", 0) + 1
            break

    save_manifest(directory, manifest)
    return manifest


def increment_fail_count(directory: Path, deliverable_name: str) -> int:
    manifest = load_manifest(directory)
    if manifest is None:
        raise FileNotFoundError(f"No manifest.json in {directory}")

    for d in manifest["deliverables"]:
        if d["name"] == deliverable_name:
            d["fail_count"] = d.get("fail_count", 0) + 1
            save_manifest(directory, manifest)
            return d["fail_count"]

    raise KeyError(f"Deliverable '{deliverable_name}' not found")


def all_passed(directory: Path) -> bool:
    manifest = load_manifest(directory)
    if manifest is None:
        return False
    return all(d["status"] == "pass" for d in manifest["deliverables"])


def get_pending_deliverables(directory: Path) -> list[dict]:
    manifest = load_manifest(directory)
    if manifest is None:
        return []
    return [d for d in manifest["deliverables"] if d["status"] in ("pending", "fail")]


def get_parallel_deliverables(directory: Path) -> list[dict]:
    manifest = load_manifest(directory)
    if manifest is None:
        return []
    return [d for d in manifest["deliverables"] if d.get("mode") == "parallel"]


def get_blocked_deliverables(directory: Path) -> list[dict]:
    manifest = load_manifest(directory)
    if manifest is None:
        return []
    return [d for d in manifest["deliverables"] if d["status"] == "blocked"]


def compute_child_status(directory: Path, child_name: str) -> str:
    """Determine the effective status of a child directory by inspecting its artifacts."""
    child_dir = directory / child_name
    if not child_dir.is_dir():
        return "pending"

    if (child_dir / STANDARD_FILES["status_pass"]).exists():
        return "pass"

    if (child_dir / STANDARD_FILES["escalation"]).exists():
        child_manifest = load_manifest(child_dir)
        if child_manifest:
            statuses = {d["status"] for d in child_manifest.get("deliverables", [])}
            if statuses <= {"blocked", "pass"}:
                return "blocked"
        return "blocked"

    child_manifest = load_manifest(child_dir)
    if child_manifest is None:
        if (child_dir / STANDARD_FILES["prd"]).exists():
            return "pending"
        return "pending"

    deliverables = child_manifest.get("deliverables", [])
    if not deliverables:
        return "pending"

    statuses = {d["status"] for d in deliverables}
    if statuses == {"pass"}:
        return "pass"
    if "blocked" in statuses and statuses <= {"blocked", "pass", "fail"}:
        return "blocked"
    if "fail" in statuses:
        return "fail"
    if "in_progress" in statuses:
        return "in_progress"
    return "pending"


def rollup_status(directory: Path) -> bool:
    """Update directory-type deliverables in this directory's manifest
    to reflect the actual status of their child directories.

    Returns True if any status changed.
    """
    manifest = load_manifest(directory)
    if manifest is None:
        return False

    changed = False
    for d in manifest["deliverables"]:
        if d["type"] != "directory":
            continue
        if d.get("mode") == "parallel":
            continue

        child_status = compute_child_status(directory, d["name"])
        if d["status"] != child_status:
            d["status"] = child_status
            changed = True

    if changed:
        save_manifest(directory, manifest)

        if all(d["status"] == "pass" for d in manifest["deliverables"]):
            flag_path = directory / STANDARD_FILES["status_pass"]
            if not flag_path.exists():
                flag_path.write_text("")

    return changed


def rollup_tree(root: Path) -> None:
    """Recursively roll up statuses from leaves to root (bottom-up)."""
    for child in sorted(root.iterdir()):
        if child.is_dir() and not child.name.startswith((".", "__")):
            rollup_tree(child)

    rollup_status(root)


def has_file(directory: Path, filename: str) -> bool:
    return (directory / filename).exists()


def read_file(directory: Path, filename: str) -> Optional[str]:
    path = directory / filename
    if not path.exists():
        return None
    return path.read_text()


def write_file(directory: Path, filename: str, content: str) -> None:
    path = directory / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
