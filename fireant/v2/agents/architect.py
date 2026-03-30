import json
import logging
from pathlib import Path

from .base import BaseAgent
from ..utils.manifest import create_manifest

logger = logging.getLogger("fireant")


class ArchitectAgent(BaseAgent):
    """Creates manifest with file instructions or subdirectory decomposition.
    
    ═══════════════════════════════════════════════════════════════
    DUTY: MANIFEST CREATION (Step 2)
    ═══════════════════════════════════════════════════════════════
    Architect reads the PRD and decides how to structure the work:
    - If simple enough: create FILE deliverables with instructions
    - If complex: create DIRECTORY deliverables with high-level scope
    - Can mix both (e.g., entry files + subdirectories)
    
    For subdirectories, writes a prd.md in each so the Architect
    is recursively triggered there by the pipeline scanner.
    
    Responsibilities:
    - Analyze PRD complexity
    - Create manifest.json with file and/or directory deliverables
    - For directories: create subdir with prd.md (recursive trigger)
    - For files: provide clear implementation instructions
    
    What Architect DOES NOT do:
    - Write code (→ Engineer agent)
    - Review code (→ Reviewer agent)
    ═══════════════════════════════════════════════════════════════

    Trigger: has prd.md but no manifest.json
    Re-trigger: any agent removes manifest.json → Architect re-triggers
    """

    role = "architect"

    def check_trigger(self, directory: Path) -> bool:
        if not self.has_prd(directory):
            return False
        if self.has_manifest(directory):
            return False
        return True

    def _execute_impl(self, directory: Path) -> None:
        prd_content = self.read_prd(directory)
        if not prd_content:
            logger.warning(f"[architect] Empty prd.md in {directory}")
            return

        # Note existing subdirs to avoid duplicates
        skip_names = {"lib", "test", "node_modules", "__pycache__"}
        existing_components = {
            d.name for d in self.get_subdirs(directory)
            if not d.name.startswith((".", "_")) and d.name not in skip_names
        }

        folder_ctx = self.build_folder_context(directory)
        deliverables = self._plan_deliverables(prd_content, folder_ctx)
        manifest_entries = []
        dir_count = 0
        file_count = 0

        for d in deliverables:
            d_type = d.get("type", "file")
            name = d["name"]
            description = d.get("description", "")
            inputs = d.get("inputs", "")
            outputs = d.get("outputs", "")
            deps = d.get("dependencies", [])

            if d_type == "directory":
                # Create subdirectory with contract-aware prd.md
                subdir = directory / name
                if name not in existing_components:
                    subdir.mkdir(parents=True, exist_ok=True)
                    self.write_prd(subdir, self._build_subdir_prd(
                        name, description, inputs, outputs, deps,
                    ))
                manifest_entries.append({
                    "name": name,
                    "type": "directory",
                    "description": description,
                    "inputs": inputs,
                    "outputs": outputs,
                    "dependencies": deps,
                })
                dir_count += 1
            else:
                # File deliverable with contract info
                manifest_entries.append({
                    "name": name,
                    "type": "file",
                    "description": description,
                    "inputs": inputs,
                    "outputs": outputs,
                    "dependencies": deps,
                })
                file_count += 1

        manifest = create_manifest(manifest_entries)
        self.write_manifest(directory, manifest)
        self.log_operation("create_manifest", directory, {
            "files": file_count, "directories": dir_count,
        })
        logger.info(
            f"[architect] Planned {directory}: "
            f"{file_count} files + {dir_count} subdirectories"
        )

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _build_subdir_prd(
        name: str,
        description: str,
        inputs: str,
        outputs: str,
        dependencies: list,
    ) -> str:
        """Build a contract-aware PRD for a subdirectory."""
        lines = [f"# {name}", "", f"## Core Function", f"{description}", ""]
        if inputs:
            lines += [f"## Inputs", f"{inputs}", ""]
        if outputs:
            lines += [f"## Outputs", f"{outputs}", ""]
        if dependencies:
            deps_str = ", ".join(f"`{d}`" for d in dependencies)
            lines += [f"## Dependencies", f"Depends on: {deps_str}", ""]
        return "\n".join(lines) + "\n"

    # ── LLM calls ────────────────────────────────────────────────────

    def _plan_deliverables(self, prd_content: str, folder_ctx: str = "") -> list[dict]:
        """Decide whether to create files or subdirectories for this PRD.

        Returns a list of dicts with keys: name, type, description,
        inputs, outputs, dependencies.
        """
        prompt = (
            "Analyze this PRD and plan the deliverables for this folder.\n\n"
            "DECISION CRITERIA:\n"
            "- If the task can be done with 1-4 small files (each <100 lines), "
            "create FILE deliverables\n"
            "- If the task is too complex, create DIRECTORY deliverables "
            "(subfolders)\n"
            "- You can mix both: some files at this level + some subdirectories\n\n"
            "RULES:\n"
            "- Each file should do ONE thing and be under 100 lines\n"
            "- Each directory should represent a coherent sub-component\n"
            "- Directory names: lowercase, hyphenated slugs (e.g. \"user-auth\")\n"
            "- File names: standard conventions (e.g. \"main.py\", \"index.html\")\n"
            "- Prefer FLAT structure: many siblings over deep nesting\n\n"
            "CONTRACT — for EVERY deliverable you MUST specify:\n"
            "- What it receives (inputs / arguments / data it reads)\n"
            "- What it produces (outputs / return values / side effects)\n"
            "- Its core function in one sentence\n"
            "- Which sibling files/directories it depends on or is depended on by\n\n"
            "Return a JSON array where each element has:\n"
            "- \"name\": filename (e.g. \"utils.py\") or directory name (e.g. \"auth\")\n"
            "- \"type\": \"file\" or \"directory\"\n"
            "- \"description\": core function — what this module does in one sentence\n"
            "- \"inputs\": what this module receives (args, data, events, imports)\n"
            "- \"outputs\": what this module produces (return values, exports, side effects)\n"
            "- \"dependencies\": list of sibling names this module depends on "
            "(empty [] if none)\n\n"
            f"PRD:\n{prd_content}"
        )

        raw = self.llm.generate_json(prompt, context=folder_ctx)
        try:
            result = json.loads(raw)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            logger.error(f"[architect] Failed to parse deliverables: {raw[:200]}")

        return []
