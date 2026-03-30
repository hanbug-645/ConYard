import json
import logging
from pathlib import Path
from typing import Optional

from .base import BaseAgent
from ..utils.manifest import (
    STANDARD_FILES,
    collect_implemented_interfaces,
    get_engineer_actionable,
    load_manifest,
    mark_code_done,
    update_field,
)
from ..utils.config import get_escalation_config

logger = logging.getLogger("fireant")


class EngineerAgent(BaseAgent):
    """Writes code for a single pending file deliverable.
    
    ═══════════════════════════════════════════════════════════════
    DUTY: CODE IMPLEMENTATION (Step 2)
    ═══════════════════════════════════════════════════════════════
    Controls: coding_status field only.
    
    Env-signal triggers (reads manifest, not called by other agents):
    - coding_status == 'pending' → initial code write
    - qa_status == 'fail'       → self-correct from escalation
    
    After writing code: sets coding_status=done, resets
    qa_status=pending (code changed, previous tests are stale).
    
    Retries up to max_retries before setting coding_status=blocked.
    
    What Engineer DOES NOT do:
    - Decide what files to create (→ Architect agent)
    - Execute tests (→ QA Engineer agent)
    - Fix escalated structural issues (→ Debugger agent)
    ═══════════════════════════════════════════════════════════════
    """

    role = "engineer"

    def __init__(self, temperature_override: Optional[float] = None):
        super().__init__(temperature_override=temperature_override)
        self._project_roots: dict[Path, Path] = {}

    def set_project_root(self, directory: Path, project_root: Path) -> None:
        self._project_roots[directory] = project_root

    def clear_project_root(self, directory: Path) -> None:
        self._project_roots.pop(directory, None)

    def build_folder_context(self, directory: Path) -> str:
        """Build implementation context: current + child interfaces + Kaplay API.

        Bottom-up build order means child code already exists,
        so we include actual child exports to prevent interface hallucination.
        """
        parts = []

        # Kaplay API reference — strict list of allowed functions
        api_ref = self.get_kaplay_api_reference()
        if api_ref:
            parts.append(api_ref)

        # Current folder context (manifest overview)
        current_context = self.get_current_dir_context(directory)
        if current_context:
            parts.append(current_context)

        # Already-written sibling code — actual implementations in this dir
        sibling_code = self._get_sibling_code(directory)
        if sibling_code:
            parts.append("=== Already-Written Sibling Files (use these exact signatures when importing) ===")
            parts.append(sibling_code)

        # Deep child exports — actual interfaces from all descendant dirs
        child_exports = self.get_deep_child_exports(directory)
        if child_exports:
            parts.append("=== Child Directory Interfaces (ACTUAL — use these exact signatures) ===")
            parts.append(child_exports)

        # Project-wide implemented interfaces (ground truth) —
        # only files OUTSIDE this directory tree (siblings/child already covered above).
        project_root = self._project_roots.get(directory)
        if project_root:
            interfaces = collect_implemented_interfaces(project_root)
            # Filter out files from the current directory and its descendants
            dir_prefix = str(directory.relative_to(project_root))
            external = [
                iface for iface in interfaces
                if not iface["path"].startswith(dir_prefix)
            ]
            if external:
                iface_lines = ["=== Other Implemented Interfaces (import targets outside this folder) ==="]
                for iface in external:
                    iface_lines.append(f"--- {iface['path']} ---")
                    if iface.get('description'):
                        iface_lines.append(f"  Purpose: {iface['description']}")
                    for sig, desc in iface.get('exports', {}).items():
                        iface_lines.append(f"  export: {sig} — {desc}")
                parts.append("\n".join(iface_lines))

        return "\n".join(parts)

    def _get_sibling_code(self, directory: Path) -> str:
        """Get actual code of already-written files in this directory.

        Shows the engineer real implementations so it uses correct
        function signatures when importing from siblings.
        """
        manifest = self.read_manifest(directory)
        if not manifest:
            return ""

        lines = []
        for d in manifest.get("deliverables", []):
            if d.get("type") != "file":
                continue
            if d.get("coding_status") != "done":
                continue

            code_path = directory / d["name"]
            if not code_path.exists():
                continue

            code = code_path.read_text()
            # Show first 80 lines — enough to see exports and signatures
            preview = "\n".join(code.splitlines()[:80])
            lines.append(f"--- {d['name']} ---")
            lines.append(preview)
            if len(code.splitlines()) > 80:
                lines.append(f"... ({len(code.splitlines()) - 80} more lines)")

        return "\n".join(lines)

    def check_trigger(self, directory: Path) -> bool:
        if not get_engineer_actionable(directory):
            return False
        # Wait for all child subdirectories to be complete (coded + tested)
        manifest = self.read_manifest(directory)
        if manifest:
            dir_deliverables = [
                d for d in manifest.get("deliverables", [])
                if d.get("type") == "directory"
            ]
            if dir_deliverables and not all(
                d.get("status") == "complete" for d in dir_deliverables
            ):
                return False
        return True

    def _execute_impl(self, directory: Path) -> None:
        prd_content = self.read_prd(directory)
        if not prd_content:
            logger.warning(f"[engineer] No prd.md in {directory}")
            return

        # Process ALL actionable file deliverables in one invocation
        actionable = get_engineer_actionable(directory)
        if not actionable:
            return

        max_retries = get_escalation_config().get("max_retries", 3)

        # Read QA feedback from _review.md (written by QA on test failure)
        review_content = self.read_review(directory)
        folder_ctx = self.build_folder_context(directory)

        manifest = self.read_manifest(directory)

        wrote_any = False
        for deliverable in actionable:
            filename = deliverable["name"]
            description = deliverable.get("description", "")
            exports = deliverable.get("exports", {})

            # Check retry limit before attempting
            fail_count = deliverable.get("fail_count", 0)
            if fail_count >= max_retries:
                update_field(directory, filename, "coding_status", "blocked")
                self.write_escalation(directory, (
                    f"# Engineer Blocked\n\n"
                    f"## File\n{filename}\n\n"
                    f"## Reason\n"
                    f"Max retries reached ({max_retries}). Engineer could not complete this file safely.\n\n"
                    f"## Requested Action\n"
                    f"Debugger should inspect this file, nearby contracts, and resolve the dependency or structural issue.\n"
                ))
                self.log_operation("file_blocked", directory, {
                    "file": filename,
                    "reason": f"max retries reached ({max_retries})",
                })
                logger.warning(
                    f"[engineer] {filename} hit max retries ({max_retries}) → blocked"
                )
                continue

            # Read existing code if retrying
            code_path = directory / filename
            existing_code = code_path.read_text() if code_path.exists() else None

            # Pick feedback source based on which status failed
            feedback = None
            if deliverable.get("qa_status") == "fail":
                feedback = review_content

            code = self._generate_code(
                prd=prd_content,
                filename=filename,
                description=description,
                exports=exports,
                existing_code=existing_code,
                review_feedback=feedback,
                folder_context=folder_ctx,
            )

            # Handle halt protocol — engineer signals missing dependency
            if code.strip().startswith("{") and '"halt"' in code:
                try:
                    halt_data = json.loads(code)
                    if halt_data.get("halt"):
                        reason = halt_data.get("reason", "unknown")
                        logger.warning(f"[engineer] HALT on {filename}: {reason}")
                        update_field(directory, filename, "coding_status", "blocked")
                        self.write_escalation(directory, (
                            f"# Engineer Halt\n\n"
                            f"## File\n{filename}\n\n"
                            f"## Reason\n{reason}\n\n"
                            f"## Requested Action\n"
                            f"Debugger should analyze the missing dependency, contradictory contract, or structural issue and either rewrite local files or propagate the escalation.\n"
                        ))
                        self.log_operation("file_blocked", directory, {
                            "file": filename,
                            "reason": reason,
                            "source": "halt_protocol",
                        })
                        continue
                except json.JSONDecodeError:
                    pass  # Not actually JSON, treat as code

            code_path.parent.mkdir(parents=True, exist_ok=True)
            action = "edit" if existing_code else "create"
            code_path.write_text(code)
            self.log_operation(f"file_{action}", directory, {
                "file": filename, "type": "code",
            })

            mark_code_done(directory, filename)
            logger.info(f"[engineer] {action.capitalize()}d {filename} in {directory}")
            wrote_any = True

        # Clean up review file after addressing all feedback
        if wrote_any:
            review_path = directory / STANDARD_FILES["review"]
            if review_path.exists():
                review_path.unlink(missing_ok=True)


    # ── LLM calls ────────────────────────────────────────────────────

    def _generate_code(
        self,
        prd: str,
        filename: str,
        description: str,
        exports: dict | None = None,
        existing_code: str | None = None,
        review_feedback: str | None = None,
        folder_context: str = "",
    ) -> str:
        context_parts = []
        if folder_context:
            context_parts.append(f"Folder Context:\n{folder_context}")
        context_parts.append(f"PRD:\n{prd}")
        if existing_code:
            context_parts.append(f"Current code for {filename}:\n```\n{existing_code}\n```")
        if review_feedback:
            context_parts.append(f"Review feedback:\n{review_feedback}")
        context = "\n\n".join(context_parts)

        # Build contract from exports
        contract = f"File purpose: {description}\n"
        if exports:
            contract += "Required exports (you MUST implement these exact signatures):\n"
            for sig, sig_desc in exports.items():
                contract += f"  - {sig}: {sig_desc}\n"
        contract += (
            "\nSTRICT RULES:\n"
            "- Write ONLY this file. Do not reference files outside the provided context.\n"
            "- NEVER invent properties, functions, or variables not defined in the contract or context.\n"
            "- NEVER call functions from sibling/child files unless they appear in the Folder Context.\n"
            "- KAPLAY LOADING: `kaplay` is a GLOBAL function loaded via <script> tag.\n"
            "  In main.js, call `const k = kaplay({...})` directly — do NOT write `import kaplay from 'kaplay'`.\n"
            "- IMPORTS: Use relative paths for project files (`import { x } from './file.js'`).\n"
            "  Never use bare module specifiers (e.g. `import x from 'package'`).\n"
            "  Import paths MUST match files that actually exist in the Folder Context.\n"
            "  Always include the `.js` extension in import paths.\n"
            "- If the contract is impossible to fulfill (e.g. a dependency is missing from context),\n"
            '  output ONLY: {"halt": true, "reason": "<what is missing>"}\n'
        )

        if existing_code and review_feedback:
            prompt = (
                f"Fix the code in `{filename}` based on the review feedback.\n\n"
                f"CONTRACT:\n{contract}\n"
                "Return ONLY the complete, corrected source code. No markdown fences.\n"
                "If the fix is impossible due to missing context, output a halt JSON instead."
            )
        else:
            prompt = (
                f"Write the source code for `{filename}`.\n\n"
                f"CONTRACT:\n{contract}\n"
                "IMPORTANT:\n"
                "- Implement ALL required exports with the exact signatures specified.\n"
                "- If Child Directory Interfaces are provided in the context, use ONLY\n"
                "  those exact function names and signatures when calling child code.\n"
                "- Do NOT invent functions, properties, or imports that aren't in the context.\n"
                "- If fulfilling the contract is impossible, output a halt JSON instead of code.\n\n"
                "Return ONLY the complete source code. No markdown fences."
            )

        return self.llm.generate(prompt, context=context)
