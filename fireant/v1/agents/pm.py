import json
import logging
from pathlib import Path

from .base import BaseAgent
from ..utils.manifest import load_manifest, save_manifest

logger = logging.getLogger("fireant")


class PMAgent(BaseAgent):
    """Product Manager — expands skeletal PRDs into detailed requirements.

    Trigger: manifest.json exists and all deliverables are pending (freshly
             initialized by Architect), OR a change_request.md is present.
    Action:  Expands prd.md into detailed PRD, updates manifest.json with
             concrete file names. For change requests, rewrites prd.md and
             manifest.json.
    """

    role = "pm"

    def check_trigger(self, directory: Path) -> bool:
        if self.has_change_request(directory):
            return True
        if self._is_freshly_initialized(directory):
            return True
        return False

    def _execute_impl(self, directory: Path) -> None:
        if self.has_change_request(directory):
            self._handle_change_request(directory)
        elif self._is_freshly_initialized(directory):
            self._expand_prd(directory)

    # ── Trigger checks ───────────────────────────────────────────────

    def _is_freshly_initialized(self, directory: Path) -> bool:
        """Check if this directory needs PM expansion.
        
        Returns True only if:
        1. No deliverables yet (Architect just created skeleton), OR
        2. Deliverables exist but are directory-type (not files - Architect's work)
        
        Returns False if deliverables are file-type (PM already ran).
        """
        manifest = self.read_manifest(directory)
        if manifest is None:
            return False
        
        deliverables = manifest.get("deliverables", [])
        
        # No deliverables yet - PM needs to run
        if not deliverables:
            prd = self.read_prd(directory)
            return prd is not None and len(prd.strip()) > 0
        
        # If deliverables are all directory-type, Architect created them - PM needs to run
        # If deliverables are file-type, PM already ran - skip
        has_files = any(d.get("type") == "file" for d in deliverables)
        if has_files:
            # PM already created file deliverables - don't run again
            return False
        
        # All directory-type and pending - this is Architect's work, PM should run
        return all(d["status"] == "pending" and d.get("type") == "directory" for d in deliverables)

    # ── Actions ──────────────────────────────────────────────────────

    def _expand_prd(self, directory: Path) -> None:
        """Expand a skeletal PRD into a detailed, scoped requirement."""
        skeletal_prd = self.read_prd(directory)
        if not skeletal_prd:
            return

        parent_prd = self._read_parent_prd(directory)

        detailed_prd = self._generate_detailed_prd(skeletal_prd, parent_prd)
        self.write_prd(directory, detailed_prd)

        deliverables = self._generate_deliverables(detailed_prd)
        manifest = self.read_manifest(directory)
        if manifest is not None:
            from ..utils.manifest import create_manifest
            new_manifest = create_manifest(deliverables)
            self.write_manifest(directory, new_manifest)
        else:
            from ..utils.manifest import create_manifest
            self.write_manifest(directory, create_manifest(deliverables))

        logger.info(f"[pm] Expanded PRD in {directory} with {len(deliverables)} deliverables")

    def _handle_change_request(self, directory: Path) -> None:
        """Rewrite PRD and manifest based on a change_request.md."""
        change_request = self.read_change_request(directory)
        current_prd = self.read_prd(directory)

        new_prd = self._apply_change_request(current_prd or "", change_request or "")
        self.write_prd(directory, new_prd)

        deliverables = self._generate_deliverables(new_prd)
        from ..utils.manifest import create_manifest
        self.write_manifest(directory, create_manifest(deliverables))

        (directory / "change_request.md").unlink(missing_ok=True)
        logger.info(f"[pm] Applied change request in {directory}")

    # ── Helpers ──────────────────────────────────────────────────────

    def _read_parent_prd(self, directory: Path) -> str:
        parent = directory.parent
        parent_prd_path = parent / "prd.md"
        if parent_prd_path.exists():
            return parent_prd_path.read_text()
        return ""

    # ── LLM calls ────────────────────────────────────────────────────

    def _generate_detailed_prd(self, skeletal_prd: str, parent_prd: str) -> str:
        context = ""
        if parent_prd:
            context = f"Parent PRD for broader context:\n{parent_prd}"

        prompt = (
            "Expand the following skeletal PRD into a detailed, scoped product requirement document.\n"
            "Include:\n"
            "- Clear functional requirements\n"
            "- Input/output specifications\n"
            "- Edge cases and constraints\n"
            "- Dependencies on sibling components (if any)\n"
            "- Acceptance criteria\n\n"
            f"Skeletal PRD:\n{skeletal_prd}"
        )
        return self.llm.generate(prompt, context=context)

    def _generate_deliverables(self, detailed_prd: str) -> list[dict]:
        prompt = (
            "Based on the following PRD, list the concrete code files that need to be created.\n\n"
            "Return a JSON array where each element has:\n"
            "- \"name\": the filename (e.g. \"auth.py\", \"index.js\")\n"
            "- \"type\": \"file\"\n"
            "- \"description\": one sentence describing the file's purpose\n\n"
            f"PRD:\n{detailed_prd}"
        )
        raw = self.llm.generate_json(prompt)
        try:
            deliverables = json.loads(raw)
            if isinstance(deliverables, list):
                return deliverables
        except json.JSONDecodeError:
            logger.error(f"[pm] Failed to parse deliverables JSON: {raw[:200]}")
        return []

    def _apply_change_request(self, current_prd: str, change_request: str) -> str:
        prompt = (
            "Rewrite the following PRD to incorporate the change request.\n"
            "Simplify or redirect requirements as specified.\n\n"
            f"Current PRD:\n{current_prd}\n\n"
            f"Change Request:\n{change_request}"
        )
        return self.llm.generate(prompt)
