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
from utils.code_summary import summarize_file, format_summaries

logger = logging.getLogger("fireant")


class PMAgent(BaseAgent):
    """Technical PM that plans tasks and tracks progress via signals."""

    role = "pm"

    def __init__(self, project_dir: Path, **kwargs):
        super().__init__(**kwargs)
        self.project_dir = project_dir
        pm_cfg = self.config.get("agents", {}).get("pm", {})
        self.max_tasks_per_iteration: int = pm_cfg.get("max_tasks_per_iteration", 3)
        ft_cfg = self.config.get("fault_tolerance", {})
        self.stall_threshold: int = ft_cfg.get("pm_stall_threshold", 3)
        self._stall_counter: int = 0
        self._last_green_count: int = -1  # -1 so first iteration never counts as stall

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

            # ── Stall detection ───────────────────────────────────
            current_green = len(green_files)
            if current_green <= self._last_green_count:
                self._stall_counter += 1
                logger.info(
                    f"[pm] No new green files (stall {self._stall_counter}/{self.stall_threshold})"
                )
            else:
                self._stall_counter = 0
            self._last_green_count = current_green

            if self._stall_counter >= self.stall_threshold:
                logger.warning(
                    f"[pm] Stall detected — {self._stall_counter} iterations with no progress. "
                    f"Flushing pending task and fix_request queues."
                )
                self._flush_stuck_queues()
                self._stall_counter = 0

            green_summaries = self._summarize_green_files(green_files)

            tasks = self._gap_analysis(prd, green_summaries)

            # Hard cap — never exceed configured limit
            if len(tasks) > self.max_tasks_per_iteration:
                tasks = tasks[:self.max_tasks_per_iteration]

            if not tasks:
                # Hard guard: ensure main.js exists and is green before converging
                missing_entry = self._check_entry_point(green_files)
                if missing_entry:
                    tasks = [missing_entry]
                    logger.warning(f"[pm] Gap analysis returned 0 tasks but {missing_entry['file']} not green — forcing task")
                else:
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

    def _summarize_green_files(self, green_files: list[str]) -> str:
        """Build a compact summary of verified files (signatures + descriptions)."""
        summaries = {}
        for rel_path in green_files:
            full_path = self.project_dir / rel_path
            summary = summarize_file(full_path)
            if summary:
                summaries[rel_path] = summary
        return format_summaries(summaries)

    # ── Stall recovery ─────────────────────────────────────────────────

    def _flush_stuck_queues(self) -> None:
        """Drain pending task and fix_request queues to break a stall.

        After flushing, the next gap analysis will re-plan from scratch
        based on what is actually green.
        """
        for sig_type in ("task", "fix_request", "task_done"):
            drained = 0
            while self.signals.claim_signal(sig_type, "pm-flush") is not None:
                drained += 1
            if drained:
                logger.info(f"[pm] Flushed {drained} stuck {sig_type} signals")
        self.log_operation("stall_flush", self.project_dir, {})

    # ── Entry point guard ─────────────────────────────────────────────

    def _check_entry_point(self, green_files: list[str]) -> Optional[dict]:
        """Return a forced task for main.js if it isn't green yet."""
        entry = "main.js"
        if entry not in green_files:
            return {
                "file": entry,
                "layer": "",
                "description": "Application entry point — imports and wires all modules together",
                "depends_on": list(green_files),
            }
        return None

    # ── Gap analysis (LLM) ───────────────────────────────────────────

    def _gap_analysis(self, prd: str, green_summary: str) -> list[dict]:
        """Compare PRD requirements against verified code. Return missing tasks.

        Each task dict:
            file: str        — filename to create (e.g. "config.js")
            layer: str       — target layer directory (e.g. "layer_1")
            description: str — what this file should implement
            depends_on: list — files this depends on (must already be green)
        """
        code_context = green_summary if green_summary else "(no verified code yet)"

        # Include Kaplay API reference
        api_ref = self.get_kaplay_api_reference()
        api_section = f"Kaplay API Reference:\n{api_ref}\n\n" if api_ref else ""

        context = f"{api_section}PRD:\n{prd}\n\nVerified (green) code:\n{code_context}"

        prompt = (
            "You are a technical PM. Compare the PRD requirements against the "
            "verified code and identify what is STILL MISSING.\n\n"
            "CORE PRINCIPLE — Always Do The Next Right Thing:\n"
            "- Do NOT plan the entire project at once.\n"
            "- Look at what exists (green code) and ask: what is the ONE next layer "
            "of files that can be built right now?\n"
            f"- Return at most {self.max_tasks_per_iteration} tasks per iteration — the smallest useful batch.\n"
            "- Prefer files with ZERO unmet dependencies (leaf nodes first).\n"
            "- If many files are missing, pick only the ones that unblock the most "
            "downstream work.\n"
            "- You will be called again after these tasks are done — you do not need "
            "to plan ahead.\n\n"
            "DIRECTORY STRUCTURE RULES:\n"
            "- ALL directories MUST be named layer_1/, layer_2/, layer_3/, etc.\n"
            "- No other directory names are allowed (no config/, game/, utils/, etc.).\n"
            "- Files with NO dependencies on other project files go in layer_1/.\n"
            "- Files that depend on layer_1/ files go in layer_2/, and so on.\n"
            "- main.js goes in the project root (layer='') and is ALWAYS the LAST file created.\n"
            "- Each layer is flat — no nesting within a layer directory.\n\n"
            "RULES:\n"
            "- Only create tasks for files whose dependencies are ALL already green\n"
            "- If a file depends on something not yet green, wait for the next iteration\n"
            "- Keep files small and focused (one concern per file)\n"
            "- Maximum 6 files per layer\n"
            "- If ALL requirements are satisfied by the green code, return an empty array []\n\n"
            f"Return a JSON array of task objects (max {self.max_tasks_per_iteration}):\n"
            "[{\"file\": \"filename.js\", \"layer\": \"layer_1\", "
            "\"description\": \"what to implement\", "
            "\"depends_on\": [\"layer_1/constants.js\"]}]\n\n"
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
