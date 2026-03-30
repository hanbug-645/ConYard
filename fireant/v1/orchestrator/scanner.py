import logging
from pathlib import Path

from ..utils.manifest import STANDARD_FILES, load_manifest

logger = logging.getLogger("fireant")


class TreeScanner:
    """Walks the project directory tree and classifies each directory's state.

    Returns a list of (directory, state) tuples that the Pipeline uses to
    decide which agent to dispatch. States map directly to agent triggers.
    """

    # Directory states (in priority order for dispatch)
    NEEDS_ARCHITECT = "needs_architect"
    NEEDS_STRATEGIST_RISK = "needs_strategist_risk"
    NEEDS_STRATEGIST_ESCALATION = "needs_strategist_escalation"
    NEEDS_PM = "needs_pm"
    NEEDS_ENGINEER = "needs_engineer"
    NEEDS_REVIEWER = "needs_reviewer"
    COMPLETE = "complete"
    BLOCKED = "blocked"

    def scan(self, root: Path) -> list[tuple[Path, str]]:
        """Recursively scan the tree and return (directory, state) pairs."""
        results = []
        self._scan_dir(root, results)
        return results

    def _scan_dir(self, directory: Path, results: list) -> None:
        if not directory.is_dir():
            return

        state = self._classify(directory)
        results.append((directory, state))

        # Recurse into sub-directories (skip hidden dirs and __pycache__)
        for child in sorted(directory.iterdir()):
            if child.is_dir() and not child.name.startswith((".", "__")):
                self._scan_dir(child, results)

    def _classify(self, directory: Path) -> str:
        has_prd = (directory / STANDARD_FILES["prd"]).exists()
        has_manifest = (directory / STANDARD_FILES["manifest"]).exists()
        has_status_pass = (directory / STANDARD_FILES["status_pass"]).exists()
        has_escalation = (directory / STANDARD_FILES["escalation"]).exists()

        # Already complete
        if has_status_pass:
            return self.COMPLETE

        # Has PRD but no manifest → Architect hasn't decomposed yet
        if has_prd and not has_manifest:
            subdirs = [d for d in directory.iterdir() if d.is_dir() and not d.name.startswith((".", "__"))]
            code_exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs"}
            code_files = [f for f in directory.iterdir() if f.is_file() and f.suffix in code_exts]
            if not subdirs and not code_files:
                return self.NEEDS_ARCHITECT

        if not has_manifest:
            return self.COMPLETE  # Nothing actionable here

        manifest = load_manifest(directory)
        if manifest is None:
            return self.COMPLETE

        deliverables = manifest.get("deliverables", [])

        # Check for child escalations → Strategist
        for child in directory.iterdir():
            if child.is_dir() and (child / STANDARD_FILES["escalation"]).exists():
                return self.NEEDS_STRATEGIST_ESCALATION

        # Check for blocked children → Strategist
        if any(d["status"] == "blocked" for d in deliverables):
            return self.NEEDS_STRATEGIST_ESCALATION

        # Check for high-risk unhandled → Strategist risk review
        if any(
            d.get("risk") == "high" and d.get("mode") == "single" and d["status"] == "pending"
            for d in deliverables
        ):
            return self.NEEDS_STRATEGIST_RISK

        # Check for change_request.md → PM
        if (directory / STANDARD_FILES["change_request"]).exists():
            return self.NEEDS_PM

        # All deliverables pending (freshly initialized, empty deliverables list) → PM
        if not deliverables:
            if has_prd:
                return self.NEEDS_PM
            return self.COMPLETE

        # Only trigger PM if deliverables are directory-type (Architect's work)
        # Skip if file-type deliverables exist (PM already ran)
        has_files = any(d.get("type") == "file" for d in deliverables)
        if not has_files and all(d["status"] == "pending" and d.get("type") == "directory" for d in deliverables):
            return self.NEEDS_PM

        # Pending/fail file deliverables → Engineer (regardless of subdirs)
        if any(d.get("type") == "file" and d["status"] in ("pending", "fail") for d in deliverables):
            return self.NEEDS_ENGINEER

        # Deliverables in_progress → Reviewer
        if any(d["status"] == "in_progress" for d in deliverables):
            # Check both direct path and lib/ subdirectory (Engineer writes to lib/)
            if any(d["status"] == "in_progress" and 
                   ((directory / d["name"]).exists() or (directory / "lib" / d["name"]).exists())
                   for d in deliverables):
                return self.NEEDS_REVIEWER

        # All file deliverables passed
        if has_files and all(d.get("type") != "file" or d["status"] == "pass" for d in deliverables):
            return self.COMPLETE

        return self.COMPLETE
