import json
import logging
from pathlib import Path

from .base import BaseAgent
from ..utils.manifest import create_manifest

logger = logging.getLogger("fireant")


class ArchitectAgent(BaseAgent):
    """Pure structural decomposition.

    Trigger: A directory has prd.md but no sub-directories, no code files,
             and no manifest.json.
    Action:  Reads prd.md, creates sub-directories with skeletal prd.md and
             manifest.json in each. Updates own manifest.json.
    """

    role = "architect"

    def check_trigger(self, directory: Path) -> bool:
        if not self.has_prd(directory):
            return False
        if self.has_manifest(directory):
            return False
        if self.get_subdirs(directory):
            return False
        if self.get_code_files(directory):
            return False
        return True

    def _execute_impl(self, directory: Path) -> None:
        prd_content = self.read_prd(directory)
        if not prd_content:
            logger.warning(f"[architect] Empty prd.md in {directory}")
            return

        decomposition = self._decompose(prd_content)
        parent_deliverables = []

        for component in decomposition:
            name = component["name"]
            description = component["description"]
            subdir = directory / name
            subdir.mkdir(parents=True, exist_ok=True)

            skeletal_prd = f"# {name}\n\n{description}\n"
            self.write_prd(subdir, skeletal_prd)

            child_manifest = create_manifest([])
            self.write_manifest(subdir, child_manifest)

            parent_deliverables.append({
                "name": name,
                "type": "directory",
                "description": description,
                "risk": component.get("risk", "low"),
            })

        parent_manifest = create_manifest(parent_deliverables)
        self.write_manifest(directory, parent_manifest)
        logger.info(f"[architect] Decomposed {directory} into {len(decomposition)} components")

    def _decompose(self, prd_content: str) -> list[dict]:
        """Ask Gemini to decompose the PRD into sub-components.

        Returns a list of dicts with keys: name, description, risk.
        """
        prompt = (
            "Decompose the following PRD into 4-6 TINY, atomic sub-components.\n\n"
            "CRITICAL RULES:\n"
            "1. Create a WIDE, FLAT structure - all components at the SAME LEVEL (siblings)\n"
            "2. NEVER create nested hierarchies - prefer many small siblings\n"
            "3. Each component must be implementable in under 100 lines TOTAL\n"
            "4. Each component does ONE micro-task only (e.g., 'render-snake', 'detect-collision', 'handle-input')\n"
            "5. Break down into the SMALLEST possible units\n\n"
            "Return a JSON array where each element has:\n"
            "- \"name\": ultra-specific, lowercase, slug name (e.g. \"snake-movement\", \"food-spawner\", \"score-tracker\")\n"
            "- \"description\": ONE sentence describing the single micro-task\n"
            "- \"risk\": \"low\" (default), \"medium\" (if requires external deps), or \"high\" (if ambiguous)\n\n"
            f"PRD:\n{prd_content}"
        )

        raw = self.llm.generate_json(prompt)
        try:
            components = json.loads(raw)
            if isinstance(components, list):
                return components
        except json.JSONDecodeError:
            logger.error(f"[architect] Failed to parse decomposition JSON: {raw[:200]}")

        return []
