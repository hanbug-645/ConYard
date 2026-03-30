import logging
from pathlib import Path

from .base import BaseAgent
from ..utils.manifest import STANDARD_FILES, update_status

logger = logging.getLogger("fireant")


class EngineerAgent(BaseAgent):
    """Writes code for a single pending file deliverable.
    
    ═══════════════════════════════════════════════════════════════
    DUTY: CODE IMPLEMENTATION (Step 3)
    ═══════════════════════════════════════════════════════════════
    Engineer picks ONE pending file from the manifest and writes
    its code. Called repeatedly by the pipeline until all files
    in the folder are written.
    
    Responsibilities:
    - Pick one pending file deliverable
    - Write code based on PRD + deliverable instructions
    - Mark file as in_progress after writing
    
    What Engineer DOES NOT do:
    - Decide what files to create (→ Architect agent)
    - Review code quality (→ Reviewer agent)
    - Fix escalated issues (→ Debugger agent)
    ═══════════════════════════════════════════════════════════════

    Trigger: manifest has file deliverables with status 'pending' or 'fail'
    Action:  Writes code for ONE file, marks it 'in_progress'
    """

    role = "engineer"

    def check_trigger(self, directory: Path) -> bool:
        manifest = self.read_manifest(directory)
        if manifest is None:
            return False
        return any(
            d.get("type") == "file" and d["status"] in ("pending", "fail")
            for d in manifest.get("deliverables", [])
        )

    def _execute_impl(self, directory: Path) -> None:
        prd_content = self.read_prd(directory)
        if not prd_content:
            logger.warning(f"[engineer] No prd.md in {directory}")
            return

        # Pick ONE pending/fail file deliverable
        pending = [
            d for d in self.get_pending(directory)
            if d.get("type") == "file"
        ]
        if not pending:
            return

        deliverable = pending[0]
        filename = deliverable["name"]
        description = deliverable.get("description", "")
        inputs = deliverable.get("inputs", "")
        outputs = deliverable.get("outputs", "")
        deps = deliverable.get("dependencies", [])

        # Read existing code if retrying after fail
        code_path = directory / filename
        existing_code = code_path.read_text() if code_path.exists() else None

        # Read review feedback if retrying
        review_content = self.read_review(directory) if deliverable["status"] == "fail" else None

        folder_ctx = self.build_folder_context(directory)

        code = self._generate_code(
            prd=prd_content,
            filename=filename,
            description=description,
            inputs=inputs,
            outputs=outputs,
            dependencies=deps,
            existing_code=existing_code,
            review_feedback=review_content,
            folder_context=folder_ctx,
        )

        code_path.parent.mkdir(parents=True, exist_ok=True)
        action = "edit" if existing_code else "create"
        code_path.write_text(code)
        self.log_operation(f"file_{action}", directory, {
            "file": filename, "type": "code",
        })

        update_status(directory, filename, "in_progress")
        logger.info(f"[engineer] {action.capitalize()}d {filename} in {directory}")

        # Clean up review file after addressing feedback
        review_path = directory / STANDARD_FILES["review"]
        if review_content and review_path.exists():
            review_path.unlink(missing_ok=True)

    # ── LLM calls ────────────────────────────────────────────────────

    def _generate_code(
        self,
        prd: str,
        filename: str,
        description: str,
        inputs: str = "",
        outputs: str = "",
        dependencies: list | None = None,
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

        # Build contract section
        contract = f"File purpose: {description}\n"
        if inputs:
            contract += f"Inputs: {inputs}\n"
        if outputs:
            contract += f"Outputs: {outputs}\n"
        if dependencies:
            contract += f"Dependencies: {', '.join(dependencies)}\n"

        if existing_code and review_feedback:
            prompt = (
                f"Fix the code in `{filename}` based on the review feedback.\n\n"
                f"CONTRACT:\n{contract}\n"
                "Return ONLY the complete, corrected source code. No markdown fences."
            )
        else:
            prompt = (
                f"Write the source code for `{filename}`.\n\n"
                f"CONTRACT:\n{contract}\n"
                "IMPORTANT: Your code MUST match the contract above — accept the "
                "specified inputs and produce the specified outputs.\n\n"
                "Return ONLY the complete source code. No markdown fences.\n"
                "Include necessary imports, docstrings, and error handling."
            )

        return self.llm.generate(prompt, context=context)
