import json
from pathlib import Path
from typing import Any, Optional


STANDARD_FILES = {
    "prd": "_prd.md",
    "manifest": "_manifest.json",
    "review": "_review.md",
    "escalation": "_escalation.json",
}

MAX_ESCALATION_DEPTH = 8

# ── Per-field status values (each controlled by one agent) ────────
CODING_STATUSES = ("pending", "in_progress", "done", "blocked")
QA_STATUSES = ("pending", "pass", "fail")

# Directory deliverables use a single rolled-up status
DIR_STATUSES = ("pending", "in_progress", "complete", "blocked")


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
        - exports: dict mapping function signature to description
          e.g. {"parse_json(raw: str) -> dict": "Parse raw JSON into dict"}
        - risk: str

    File deliverables get two independent status fields:
        coding_status (Engineer), qa_status (QA)
    Directory deliverables get a single rolled-up status.
    """
    items = []
    for d in deliverables:
        entry = {
            "name": d["name"],
            "type": d.get("type", "file"),
            "description": d.get("description", ""),
            "exports": d.get("exports", {}),
            "fail_count": 0,
            "risk": d.get("risk", "low"),
        }
        if entry["type"] == "file":
            entry["coding_status"] = "pending"
            entry["qa_status"] = "pending"
        else:
            entry["status"] = "pending"
        items.append(entry)
    return {"deliverables": items}


def rebuild_manifest_with_statuses(old_manifest: dict | None, deliverables: list[dict]) -> dict:
    """Create a new manifest while preserving statuses for unchanged entries by name/type."""
    new_manifest = create_manifest(deliverables)
    if old_manifest is None:
        return new_manifest

    old_index = {
        (d.get("name"), d.get("type")): d
        for d in old_manifest.get("deliverables", [])
    }

    for d in new_manifest.get("deliverables", []):
        old = old_index.get((d.get("name"), d.get("type")))
        if not old:
            continue
        if d.get("type") == "file":
            d["coding_status"] = old.get("coding_status", d.get("coding_status"))
            d["qa_status"] = old.get("qa_status", d.get("qa_status"))
            d["fail_count"] = old.get("fail_count", d.get("fail_count", 0))
        else:
            d["status"] = old.get("status", d.get("status", "pending"))

    return new_manifest


def diff_manifest(old_manifest: dict | None, new_manifest: dict | None) -> dict[str, set[str]]:
    """Return added/removed/changed deliverable names between two manifests."""
    old_map = {
        d["name"]: d for d in (old_manifest or {}).get("deliverables", [])
    }
    new_map = {
        d["name"]: d for d in (new_manifest or {}).get("deliverables", [])
    }

    old_names = set(old_map.keys())
    new_names = set(new_map.keys())
    added = new_names - old_names
    removed = old_names - new_names
    changed = set()

    for name in old_names & new_names:
        old = old_map[name]
        new = new_map[name]
        if (
            old.get("type") != new.get("type")
            or old.get("description", "") != new.get("description", "")
            or old.get("exports", {}) != new.get("exports", {})
        ):
            changed.add(name)

    return {"added": added, "removed": removed, "changed": changed}


def _reset_file_statuses_in_manifest(manifest: dict, affected_names: set[str] | None = None) -> bool:
    changed = False
    for d in manifest.get("deliverables", []):
        if d.get("type") != "file":
            continue
        if affected_names is not None and d.get("name") not in affected_names:
            continue
        d["coding_status"] = "pending"
        d["qa_status"] = "pending"
        d["fail_count"] = 0
        changed = True
    return changed


def soft_invalidate_files(directory: Path, affected_names: set[str] | None = None) -> None:
    """Reset selected file deliverables in a manifest back to pending."""
    manifest = load_manifest(directory)
    if manifest is None:
        return
    if _reset_file_statuses_in_manifest(manifest, affected_names):
        save_manifest(directory, manifest)


def hard_invalidate_subtree(directory: Path) -> None:
    """Remove manifest/review/escalation artifacts for a subtree, preserving PRDs and code files."""
    if not directory.exists() or not directory.is_dir():
        return

    for child in sorted(directory.iterdir()):
        if child.is_dir() and not child.name.startswith((".", "_")):
            hard_invalidate_subtree(child)

    for key in ("manifest", "review", "escalation"):
        path = directory / STANDARD_FILES[key]
        if path.exists():
            path.unlink()


def tree_shake_after_manifest_update(directory: Path, old_manifest: dict | None, new_manifest: dict) -> dict[str, list[str]]:
    """Invalidate affected children and dependent files after a parent manifest update."""
    diff = diff_manifest(old_manifest, new_manifest)
    impacted_children: list[str] = []
    reset_files: list[str] = []

    changed_names = diff["added"] | diff["removed"] | diff["changed"]
    if not changed_names:
        return {"children": impacted_children, "files": reset_files}

    old_map = {
        d["name"]: d for d in (old_manifest or {}).get("deliverables", [])
    }
    new_map = {
        d["name"]: d for d in new_manifest.get("deliverables", [])
    }

    # Hard invalidate child subtrees whose directory contracts changed, were removed, or were added.
    for name in changed_names:
        old = old_map.get(name)
        new = new_map.get(name)
        was_dir = old is not None and old.get("type") == "directory"
        is_dir = new is not None and new.get("type") == "directory"
        if was_dir or is_dir:
            child_dir = directory / name
            if child_dir.exists() and child_dir.is_dir():
                hard_invalidate_subtree(child_dir)
                impacted_children.append(name)

    # Soft reset files in this directory that changed.
    affected_files = set()
    for d in new_manifest.get("deliverables", []):
        if d.get("type") != "file":
            continue
        if d.get("name") in changed_names:
            affected_files.add(d.get("name"))

    if affected_files:
        soft_invalidate_files(directory, affected_files)
        reset_files.extend(sorted(affected_files))

    return {"children": impacted_children, "files": reset_files}


def _find_deliverable(manifest: dict, name: str) -> Optional[dict]:
    for d in manifest.get("deliverables", []):
        if d["name"] == name:
            return d
    return None


def update_field(directory: Path, deliverable_name: str, field: str, value: str) -> dict:
    """Update a single status field on a deliverable and save."""
    manifest = load_manifest(directory)
    if manifest is None:
        raise FileNotFoundError(f"No manifest.json in {directory}")
    d = _find_deliverable(manifest, deliverable_name)
    if d is None:
        raise KeyError(f"Deliverable '{deliverable_name}' not found")
    d[field] = value
    if field == "qa_status" and value == "fail":
        d["fail_count"] = d.get("fail_count", 0) + 1
    save_manifest(directory, manifest)
    return manifest


def mark_code_done(directory: Path, deliverable_name: str) -> dict:
    """Engineer finished writing/rewriting code.

    Sets coding_status=done and resets qa_status to pending
    (because the code changed, previous tests are stale).
    """
    manifest = load_manifest(directory)
    if manifest is None:
        raise FileNotFoundError(f"No manifest.json in {directory}")
    d = _find_deliverable(manifest, deliverable_name)
    if d is None:
        raise KeyError(f"Deliverable '{deliverable_name}' not found")
    d["coding_status"] = "done"
    d["qa_status"] = "pending"
    save_manifest(directory, manifest)
    return manifest


def is_file_complete(d: dict) -> bool:
    """A file deliverable is complete when QA has passed."""
    return d.get("qa_status") == "pass"


def is_deliverable_complete(d: dict) -> bool:
    """Check if any deliverable (file or directory) is complete."""
    if d.get("type") == "file":
        return is_file_complete(d)
    return d.get("status") == "complete"


def all_passed(directory: Path) -> bool:
    manifest = load_manifest(directory)
    if manifest is None:
        return False
    deliverables = manifest.get("deliverables", [])
    if not deliverables:
        return False
    return all(is_deliverable_complete(d) for d in deliverables)


def get_engineer_actionable(directory: Path) -> list[dict]:
    """Return file deliverables that need Engineer work.

    Engineer triggers when:
    - coding_status == 'pending' (ready for initial code write)
    - qa_status == 'fail' (QA failed → rework)

    No dependency gating — the pipeline scans bottom-up so child
    directories are always complete before parent files are attempted.
    """
    manifest = load_manifest(directory)
    if manifest is None:
        return []

    result = []
    for d in manifest.get("deliverables", []):
        if d.get("type") != "file" or d.get("coding_status") == "blocked":
            continue

        if d.get("qa_status") == "fail":
            result.append(d)
            continue

        if d.get("coding_status") == "pending":
            result.append(d)

    return result


def get_blocked_deliverables(directory: Path) -> list[dict]:
    manifest = load_manifest(directory)
    if manifest is None:
        return []
    return [
        d for d in manifest["deliverables"]
        if d.get("coding_status") == "blocked" or d.get("status") == "blocked"
    ]


def compute_child_status(directory: Path, child_name: str) -> str:
    """Determine the effective status of a child directory by inspecting its artifacts."""
    child_dir = directory / child_name
    if not child_dir.is_dir():
        return "pending"

    if (child_dir / STANDARD_FILES["escalation"]).exists():
        return "blocked"

    child_manifest = load_manifest(child_dir)
    if child_manifest is None:
        return "pending"

    deliverables = child_manifest.get("deliverables", [])
    if not deliverables:
        return "pending"

    if all(is_deliverable_complete(d) for d in deliverables):
        return "complete"

    # Check for blocked
    if any(d.get("coding_status") == "blocked" or d.get("status") == "blocked"
           for d in deliverables):
        return "blocked"

    return "in_progress"


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

    return changed


def rollup_tree(root: Path) -> None:
    """Recursively roll up statuses from leaves to root (bottom-up)."""
    for child in sorted(root.iterdir()):
        if child.is_dir() and not child.name.startswith((".", "__")):
            rollup_tree(child)

    rollup_status(root)


def has_file(directory: Path, filename: str) -> bool:
    """Check if a file exists in the directory."""
    return (directory / filename).exists()


def read_file(directory: Path, filename: str) -> Optional[str]:
    """Read file content from directory, return None if not found."""
    path = directory / filename
    if not path.exists():
        return None
    return path.read_text()


def write_file(directory: Path, filename: str, content: str) -> None:
    """Write content to file in directory, creating parent dirs if needed."""
    path = directory / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


_SKIP_DIRS = {"lib", "test", "node_modules", "__pycache__"}


def collect_implemented_interfaces(project_root: Path) -> list[dict]:
    """Walk the project tree and collect all implemented file interfaces.

    Returns a list of dicts, each with:
        - path: relative path from project_root (e.g. "game/entities.js")
        - exports: dict of signature -> description from manifest
        - description: file description from manifest
        - code_preview: first 40 lines of actual code (if file exists)

    A file is considered "implemented" when coding_status == "done"
    or qa_status == "pass".  This represents ground truth — what
    actually exists and can be imported.
    """
    results: list[dict] = []

    def _scan(directory: Path) -> None:
        manifest = load_manifest(directory)
        if manifest is not None:
            for d in manifest.get("deliverables", []):
                if d.get("type") != "file":
                    continue
                coding = d.get("coding_status", "pending")
                qa = d.get("qa_status", "pending")
                if coding not in ("done",) and qa not in ("pass",):
                    continue

                file_path = directory / d["name"]
                rel_path = str(file_path.relative_to(project_root))
                code_preview = ""
                if file_path.exists():
                    lines = file_path.read_text().splitlines()[:40]
                    code_preview = "\n".join(lines)

                results.append({
                    "path": rel_path,
                    "exports": d.get("exports", {}),
                    "description": d.get("description", ""),
                    "code_preview": code_preview,
                })

        for child in sorted(directory.iterdir()):
            if child.is_dir() and not child.name.startswith((".", "_")):
                if child.name not in _SKIP_DIRS:
                    _scan(child)

    _scan(project_root)
    return results
