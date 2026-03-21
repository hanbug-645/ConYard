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

    def execute(self, directory: Path) -> None:
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
            "Decompose the following PRD into modular sub-components.\n"
            "Each component should be a directory that can be developed independently.\n\n"
            "Return a JSON array where each element has:\n"
            "- \"name\": a short, lowercase, slug-style directory name (e.g. \"auth\", \"frontend\", \"database\")\n"
            "- \"description\": a 2-3 sentence description of what this component is responsible for\n"
            "- \"risk\": \"low\", \"medium\", or \"high\" based on complexity and ambiguity\n\n"
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
