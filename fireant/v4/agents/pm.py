"""Product Manager agent — drives the project forward via gap analysis.

Continuous loop:
    1. Read PRD (target state)
    2. Read verified (green) code on disk
    3. Identify what is missing
    4. Determine the correct dependency layer for each new file
    5. Push `task` signals to Redis for Engineers
    6. Sleep until new `green` signals arrive
    7. Terminate when gap analysis returns zero missing features
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

from agents.base import BaseAgent

logger = logging.getLogger("fireant")


class PMAgent(BaseAgent):
    """Technical PM that plans tasks and tracks progress via signals."""

    role = "pm"

    def __init__(self, project_dir: Path, **kwargs):
        super().__init__(**kwargs)
        self.project_dir = project_dir

    # ── Main loop ────────────────────────────────────────────────────

    def run_loop(self, poll_interval: float = 2.0, max_iterations: int = 50) -> bool:
        """Run the PM planning loop until convergence or max iterations.

        Returns True if the project converged (all tasks done).
        """
        logger.info(f"[pm] Starting planning loop for {self.project_dir}")

        for iteration in range(1, max_iterations + 1):
            logger.info(f"[pm] ── Iteration {iteration}/{max_iterations} ──")

            prd = self.read_prd(self.project_dir)
            if not prd:
                logger.error("[pm] No PRD found — cannot plan")
                return False

            green_files = self._collect_green_files()
            green_code = self._read_green_code(green_files)

            tasks = self._gap_analysis(prd, green_code)

            if not tasks:
                logger.info("[pm] Gap analysis returned 0 tasks — project complete!")
                self.log_operation("convergence", self.project_dir, {
                    "iteration": iteration,
                    "green_files": len(green_files),
                })
                return True

            # Push task signals
            for task in tasks:
                self.signals.push_signal("task", task, producer="pm")
                logger.info(f"[pm] Pushed task: {task.get('file', '?')} → {task.get('layer', '?')}")

            self.log_operation("gap_analysis", self.project_dir, {
                "iteration": iteration,
                "tasks_pushed": len(tasks),
                "green_files": len(green_files),
            })

            # Wait for Engineers and QA to process before next iteration
            self._wait_for_progress(poll_interval, max_wait=poll_interval * 30)

        logger.warning(f"[pm] Max iterations ({max_iterations}) reached without convergence")
        return False

    # ── Green file collection ────────────────────────────────────────

    def _collect_green_files(self) -> list[str]:
        """Get all verified file paths from Redis."""
        if not self.signals:
            return []
        return sorted(self.signals.all_green_paths())

    def _read_green_code(self, green_files: list[str]) -> dict[str, str]:
        """Read the actual code content of verified files."""
        result = {}
        for rel_path in green_files:
            full_path = self.project_dir / rel_path
            if full_path.exists():
                result[rel_path] = full_path.read_text()
        return result

    # ── Gap analysis (LLM) ───────────────────────────────────────────

    def _gap_analysis(self, prd: str, green_code: dict[str, str]) -> list[dict]:
        """Compare PRD requirements against verified code. Return missing tasks.

        Each task dict:
            file: str        — filename to create (e.g. "config.js")
            layer: str       — target layer directory (e.g. "layer_1")
            description: str — what this file should implement
            depends_on: list — files this depends on (must already be green)
        """
        # Format green code for context
        if green_code:
            code_sections = []
            for path, code in green_code.items():
                preview = "\n".join(code.splitlines()[:60])
                code_sections.append(f"=== {path} ===\n{preview}")
            code_context = "\n\n".join(code_sections)
        else:
            code_context = "(no verified code yet)"

        # Include Kaplay API reference
        api_ref = self.get_kaplay_api_reference()
        api_section = f"Kaplay API Reference:\n{api_ref}\n\n" if api_ref else ""

        context = f"{api_section}PRD:\n{prd}\n\nVerified (green) code:\n{code_context}"

        prompt = (
            "You are a technical PM. Compare the PRD requirements against the "
            "verified code and identify what is STILL MISSING.\n\n"
            "DIRECTORY STRUCTURE RULES:\n"
            "- Use the structure described in the PRD's Framework & Technical Requirements section.\n"
            "- If the PRD specifies subdirectories (e.g. config/, game/), use those as the 'layer' field.\n"
            "- If no structure is specified, use numbered layers: layer_1/, layer_2/, etc.\n"
            "- Files with NO dependencies go in the first layer/subdirectory.\n"
            "- Files that depend on other project files go in subsequent layers/subdirectories.\n"
            "- main.js goes in the project root (layer='') and is ALWAYS the LAST file created.\n"
            "- Each directory is flat — no nesting within directories.\n\n"
            "RULES:\n"
            "- Only create tasks for files whose dependencies are ALL already green\n"
            "- If a file depends on something not yet green, wait for the next iteration\n"
            "- Keep files small and focused (one concern per file)\n"
            "- Maximum 6 files per directory\n"
            "- If ALL requirements are satisfied by the green code, return an empty array []\n\n"
            "Return a JSON array of task objects:\n"
            "[{\"file\": \"filename.js\", \"layer\": \"config\", "
            "\"description\": \"what to implement\", "
            "\"depends_on\": [\"config/constants.js\"]}]\n\n"
            "Return [] if the project is complete."
        )

        raw = self.llm.generate_json(prompt, context=context)
        try:
            tasks = json.loads(raw)
            if not isinstance(tasks, list):
                logger.error(f"[pm] Gap analysis returned non-list: {raw[:200]}")
                return []
            return tasks
        except json.JSONDecodeError:
            logger.error(f"[pm] Failed to parse gap analysis: {raw[:200]}")
            return []

    # ── Wait for progress ────────────────────────────────────────────

    def _wait_for_progress(self, poll_interval: float, max_wait: float = 60.0) -> None:
        """Wait until pending task/task_done queues drain or timeout."""
        waited = 0.0
        while waited < max_wait:
            pending_tasks = self.signals.count_pending("task")
            pending_done = self.signals.count_pending("task_done")
            if pending_tasks == 0 and pending_done == 0:
                logger.debug("[pm] All queues drained — resuming")
                return
            time.sleep(poll_interval)
            waited += poll_interval
        logger.debug(f"[pm] Wait timeout ({max_wait}s) — resuming anyway")
