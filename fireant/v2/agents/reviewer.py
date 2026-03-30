import json
import logging
from pathlib import Path
from .base import BaseAgent
from ..utils.manifest import (
    update_status,
    all_passed,
)

logger = logging.getLogger("fireant")


class ReviewerAgent(BaseAgent):
    """Reviews all code in a folder together at the folder level.
    
    ═══════════════════════════════════════════════════════════════
    DUTY: FOLDER-LEVEL CODE REVIEW (Step 4)
    ═══════════════════════════════════════════════════════════════
    Reviewer checks whether ALL code files in a folder collectively
    fulfill the PRD. Reviews files together, not individually.
    
    Triggers only when every file deliverable has been written
    (all are in_progress). This ensures a complete folder review.
    
    Responsibilities:
    - Review all code files in a folder together
    - Check if they collectively fulfill the folder's PRD
    - Mark all as pass or create escalation for Debugger
    
    What Reviewer DOES NOT do:
    - Write or fix code (→ Engineer/Debugger agents)
    - Define requirements (→ Architect agent)
    ═══════════════════════════════════════════════════════════════

    Trigger: ALL file deliverables in manifest are 'in_progress'
    Action:  Reviews all code together against PRD.
             On pass → mark all 'pass', create status_pass if fully done.
             On fail → mark all 'fail', create escalation.md for Debugger.
    """

    role = "reviewer"

    def check_trigger(self, directory: Path) -> bool:
        manifest = self.read_manifest(directory)
        if manifest is None:
            return False

        file_deliverables = [
            d for d in manifest.get("deliverables", [])
            if d.get("type") == "file"
        ]
        if not file_deliverables:
            return False

        # All file deliverables must be in_progress (all written by Engineer)
        return all(d["status"] == "in_progress" for d in file_deliverables)

    def _execute_impl(self, directory: Path) -> None:
        prd_content = self.read_prd(directory)
        if not prd_content:
            return

        manifest = self.read_manifest(directory)
        if manifest is None:
            return

        # Collect all in_progress file deliverables and their code
        file_deliverables = [
            d for d in manifest["deliverables"]
            if d.get("type") == "file" and d["status"] == "in_progress"
        ]
        if not file_deliverables:
            return

        code_contents: dict[str, str] = {}
        for d in file_deliverables:
            code_path = directory / d["name"]
            if code_path.exists():
                code_contents[d["name"]] = code_path.read_text()

        # Review all files together against the PRD
        folder_ctx = self.build_folder_context(directory)
        review = self._review_folder(prd_content, code_contents, folder_ctx)

        if review["passed"]:
            for d in file_deliverables:
                update_status(directory, d["name"], "pass")
            self.log_operation("review_pass", directory, {
                "files": list(code_contents.keys()),
            })
            logger.info(f"[reviewer] Folder PASSED review in {directory}")

            if all_passed(directory):
                self.write_status_pass(directory)
                logger.info(f"[reviewer] All deliverables passed in {directory}")
        else:
            # Mark files as fail
            for d in file_deliverables:
                update_status(directory, d["name"], "fail")

            # Write review feedback
            self.write_review(directory, (
                f"# Folder Review\n\n"
                f"## Status: FAIL\n\n"
                f"## Issues\n\n{review['feedback']}\n"
            ))

            # Create escalation for Debugger
            self.write_escalation(directory, (
                f"# Review Escalation\n\n"
                f"## Issues Found\n\n{review['feedback']}\n\n"
                f"## Files Reviewed\n\n"
                + "\n".join(f"- {name}" for name in code_contents.keys())
                + "\n"
            ))

            self.log_operation("review_fail", directory, {
                "files": list(code_contents.keys()),
            })
            logger.info(f"[reviewer] Folder FAILED review in {directory}, escalated to Debugger")

    # ── LLM calls ────────────────────────────────────────────────────

    def _review_folder(self, prd: str, code_contents: dict[str, str], folder_ctx: str = "") -> dict:
        """Review all code files in a folder together against the PRD."""
        # Build context with all files
        code_sections = []
        for filename, code in code_contents.items():
            code_sections.append(f"=== {filename} ===\n```\n{code}\n```")
        all_code = "\n\n".join(code_sections)

        ctx_parts = []
        if folder_ctx:
            ctx_parts.append(f"Folder Context:\n{folder_ctx}")
        ctx_parts.append(f"PRD:\n{prd}")
        ctx_parts.append(all_code)
        context = "\n\n".join(ctx_parts)

        prompt = (
            "Review ALL the code files in this folder together.\n\n"
            "Evaluate as a whole:\n"
            "1. Do the files collectively fulfill the PRD requirements?\n"
            "2. Are there bugs, logic errors, or missing functionality?\n"
            "3. Do the files work together correctly (imports, interfaces)?\n"
            "4. Is each file small and focused (<100 lines)?\n\n"
            "Return a JSON object with:\n"
            "- \"passed\": true if the folder's code fulfills the task, false otherwise\n"
            "- \"feedback\": detailed feedback string (empty if passed)\n"
        )

        raw = self.llm.generate_json(prompt, context=context)
        try:
            result = json.loads(raw)
            return {
                "passed": result.get("passed", False),
                "feedback": result.get("feedback", ""),
            }
        except json.JSONDecodeError:
            logger.error(f"[reviewer] Failed to parse review JSON: {raw[:200]}")
            return {"passed": False, "feedback": "Review parsing failed — treating as fail."}
