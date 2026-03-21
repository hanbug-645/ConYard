import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

from .base import BaseAgent
from ..utils.config import get_escalation_config
from ..utils.manifest import (
    STANDARD_FILES,
    load_manifest,
    save_manifest,
    update_status,
    increment_fail_count,
    all_passed,
)

logger = logging.getLogger("fireant")


class ReviewerAgent(BaseAgent):
    """Code Reviewer / QA — verifies code against PRD and runs tests.

    Trigger: A deliverable in manifest.json has status "in_progress" and the
             corresponding file exists.
    Action:  Compares code against prd.md, optionally runs tests.
             On pass → status "pass", creates status_pass.flag if all done.
             On fail → status "fail", writes review.md. If fail_count exceeds
             threshold, writes escalation.md.
    """

    role = "reviewer"

    def __init__(self, temperature_override: Optional[float] = None):
        super().__init__(temperature_override)
        self.escalation_config = get_escalation_config(self.config)

    def check_trigger(self, directory: Path) -> bool:
        manifest = self.read_manifest(directory)
        if manifest is None:
            return False
        for d in manifest.get("deliverables", []):
            if d["status"] == "in_progress" and (directory / d["name"]).exists():
                return True
        return False

    def execute(self, directory: Path) -> None:
        prd_content = self.read_prd(directory)
        if not prd_content:
            return

        manifest = self.read_manifest(directory)
        if manifest is None:
            return

        for deliverable in manifest["deliverables"]:
            if deliverable["status"] != "in_progress":
                continue
            filename = deliverable["name"]
            code_path = directory / filename
            if not code_path.exists():
                continue

            code_content = code_path.read_text()

            test_output = self._run_tests(directory, filename)

            review = self._review_code(prd_content, filename, code_content, test_output)

            if review["passed"]:
                update_status(directory, filename, "pass")
                logger.info(f"[reviewer] {filename} PASSED in {directory}")
            else:
                fail_count = increment_fail_count(directory, filename)
                update_status(directory, filename, "fail")
                self.write_review(directory, (
                    f"# Review: {filename}\n\n"
                    f"## Status: FAIL (attempt {fail_count})\n\n"
                    f"## Issues\n\n{review['feedback']}\n"
                ))
                logger.info(f"[reviewer] {filename} FAILED (attempt {fail_count}) in {directory}")

                threshold = self.escalation_config.get("fail_threshold", 3)
                if fail_count >= threshold:
                    self._escalate(directory, filename, fail_count, review["feedback"])

        if all_passed(directory):
            self.write_status_pass(directory)
            logger.info(f"[reviewer] All deliverables passed in {directory}")

    # ── Test execution ───────────────────────────────────────────────

    def _run_tests(self, directory: Path, filename: str) -> str:
        """Attempt to run test files if they exist."""
        stem = Path(filename).stem
        suffix = Path(filename).suffix

        test_candidates = [
            f"test_{filename}",
            f"{stem}_test{suffix}",
            f"test_{stem}{suffix}",
        ]

        for test_file in test_candidates:
            test_path = directory / test_file
            if test_path.exists():
                try:
                    result = subprocess.run(
                        self._get_test_command(test_path),
                        capture_output=True,
                        text=True,
                        timeout=30,
                        cwd=str(directory),
                    )
                    output = result.stdout + result.stderr
                    if result.returncode != 0:
                        from ..utils.manifest import write_file
                        write_file(directory, STANDARD_FILES["execution_errors"], output)
                    return output
                except subprocess.TimeoutExpired:
                    return "ERROR: Test execution timed out after 30 seconds"
                except Exception as e:
                    return f"ERROR: Could not run tests: {e}"

        return ""

    def _get_test_command(self, test_path: Path) -> list[str]:
        suffix = test_path.suffix
        if suffix == ".py":
            return ["python3", "-m", "pytest", str(test_path), "-v"]
        elif suffix == ".js":
            return ["node", str(test_path)]
        elif suffix == ".ts":
            return ["npx", "ts-node", str(test_path)]
        else:
            return ["python3", str(test_path)]

    # ── Escalation ───────────────────────────────────────────────────

    def _escalate(self, directory: Path, filename: str, fail_count: int, feedback: str) -> None:
        self.write_escalation(directory, (
            f"# Escalation: {filename}\n\n"
            f"This deliverable has failed {fail_count} review cycles.\n\n"
            f"## Last Review Feedback\n\n{feedback}\n\n"
            f"## Recommendation\n\n"
            f"Consider simplifying requirements, restructuring the component, "
            f"or launching parallel approaches.\n"
        ))
        update_status(directory, filename, "blocked")
        logger.warning(f"[reviewer] Escalated {filename} in {directory} after {fail_count} failures")

    # ── LLM calls ────────────────────────────────────────────────────

    def _review_code(
        self, prd: str, filename: str, code: str, test_output: str
    ) -> dict:
        context = (
            f"PRD:\n{prd}\n\n"
            f"Code for {filename}:\n```\n{code}\n```"
        )
        if test_output:
            context += f"\n\nTest execution output:\n```\n{test_output}\n```"

        prompt = (
            f"Review the code in `{filename}` against the PRD.\n\n"
            "Evaluate:\n"
            "1. Does it satisfy all functional requirements?\n"
            "2. Are there bugs or logic errors?\n"
            "3. Is error handling adequate?\n"
            "4. Did the tests pass (if test output is provided)?\n\n"
            "Return a JSON object with:\n"
            "- \"passed\": true or false\n"
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
