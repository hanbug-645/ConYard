import json
import logging
from pathlib import Path

from .base import BaseAgent
from ..utils.manifest import load_manifest, save_manifest, update_status

logger = logging.getLogger("fireant")


class EngineerAgent(BaseAgent):
    """Implements source code for leaf-node directories.

    Trigger: manifest.json at a leaf node lists code deliverables with status
             "pending" or "fail" (after a review cycle).
    Action:  Writes source code AND a corresponding test file as specified by
             prd.md, deposits both into the directory, updates deliverable
             status to "in_progress".
    """

    role = "engineer"

    def check_trigger(self, directory: Path) -> bool:
        if self.get_subdirs(directory):
            return False
        pending = self.get_pending(directory)
        return len(pending) > 0

    def _execute_impl(self, directory: Path) -> None:
        prd_content = self.read_prd(directory)
        if not prd_content:
            logger.warning(f"[engineer] No prd.md in {directory}")
            return

        review_content = self.read_review(directory)
        error_log = self.read_execution_errors(directory)
        pending = self.get_pending(directory)

        for deliverable in pending:
            filename = deliverable["name"]
            description = deliverable.get("description", "")

            # Place code files in lib/ subdirectory
            code_path = directory / "lib" / filename
            existing_code = None
            if code_path.exists():
                existing_code = code_path.read_text()

            code = self._generate_code(
                prd=prd_content,
                filename=filename,
                description=description,
                existing_code=existing_code,
                review_feedback=review_content if deliverable["status"] == "fail" else None,
                error_log=error_log if deliverable["status"] == "fail" else None,
            )

            code_path.parent.mkdir(parents=True, exist_ok=True)
            action = "edit" if existing_code else "create"
            code_path.write_text(code)
            self.log_operation(f"file_{action}", directory, {"file": str(code_path.relative_to(directory)), "type": "code"})

            test_filename = self._test_filename(filename)
            # Place test files in lib/test/ subdirectory
            test_path = directory / "lib" / "test" / test_filename
            existing_test = None
            if test_path.exists():
                existing_test = test_path.read_text()

            test_code = self._generate_test(
                prd=prd_content,
                filename=filename,
                code=code,
                test_filename=test_filename,
                existing_test=existing_test,
                error_log=error_log if deliverable["status"] == "fail" else None,
            )
            test_path.parent.mkdir(parents=True, exist_ok=True)
            test_action = "edit" if existing_test else "create"
            test_path.write_text(test_code)
            self.log_operation(f"file_{test_action}", directory, {"file": str(test_path.relative_to(directory)), "type": "test"})

            update_status(directory, filename, "in_progress")
            logger.info(f"[engineer] {action.capitalize()}d {filename} + {test_action}d {test_filename} in {directory}")

        if review_content and (directory / "review.md").exists():
            (directory / "review.md").unlink(missing_ok=True)
        if error_log and (directory / "execution_errors.log").exists():
            (directory / "execution_errors.log").unlink(missing_ok=True)

    # ── LLM calls ────────────────────────────────────────────────────

    def _generate_code(
        self,
        prd: str,
        filename: str,
        description: str,
        existing_code: str | None = None,
        review_feedback: str | None = None,
        error_log: str | None = None,
    ) -> str:
        context_parts = [f"PRD:\n{prd}"]

        if existing_code:
            context_parts.append(f"Current code for {filename}:\n```\n{existing_code}\n```")
        if review_feedback:
            context_parts.append(f"Review feedback:\n{review_feedback}")
        if error_log:
            context_parts.append(f"Runtime errors:\n{error_log}")

        context = "\n\n".join(context_parts)

        if existing_code and (review_feedback or error_log):
            prompt = (
                f"Fix the code in `{filename}` based on the review feedback and/or runtime errors.\n"
                f"File purpose: {description}\n\n"
                "Return ONLY the complete, corrected source code. No markdown fences."
            )
        else:
            prompt = (
                f"Write the source code for `{filename}`.\n"
                f"File purpose: {description}\n\n"
                "Return ONLY the complete source code. No markdown fences.\n"
                "Include necessary imports, docstrings, and error handling."
            )

        return self.llm.generate(prompt, context=context)

    def _generate_test(
        self,
        prd: str,
        filename: str,
        code: str,
        test_filename: str,
        existing_test: str | None = None,
        error_log: str | None = None,
    ) -> str:
        context_parts = [
            f"PRD:\n{prd}",
            f"Source code for {filename}:\n```\n{code}\n```",
        ]
        if existing_test:
            context_parts.append(f"Current test file:\n```\n{existing_test}\n```")
        if error_log:
            context_parts.append(f"Previous runtime errors:\n{error_log}")

        context = "\n\n".join(context_parts)

        prompt = (
            f"Write a comprehensive test file `{test_filename}` for `{filename}`.\n\n"
            "Requirements:\n"
            "- Test all functional requirements from the PRD\n"
            "- Test edge cases and error handling\n"
            "- Use the appropriate test framework for the language "
            "(pytest for Python, built-in assert for JS)\n"
            "- Tests must be runnable standalone\n\n"
            "Return ONLY the complete test source code. No markdown fences."
        )
        return self.llm.generate(prompt, context=context)

    @staticmethod
    def _test_filename(filename: str) -> str:
        from pathlib import PurePosixPath
        p = PurePosixPath(filename)
        return f"test_{p.stem}{p.suffix}"
