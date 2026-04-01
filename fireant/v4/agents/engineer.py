"""Engineer agent — claims task/fix_request signals and writes code.

Polls Redis for:
    - `task` signals (new coding work from PM)
    - `fix_request` signals (QA failures to fix)

Before writing code for a task, the Engineer *evaluates* whether the task
is achievable with the current green (verified) code:
    a) Completable → determine dependencies + layer, write the code.
    b) Not completable → build a smaller helper as the next right step,
       then re-queue the original task for a future iteration.

After writing code, pushes a `task_done` signal for QA.
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

from agents.base import BaseAgent
from utils.code_summary import summarize_file, format_summaries
from utils.config import get_escalation_config

logger = logging.getLogger("fireant")


class EngineerAgent(BaseAgent):
    """Writes code for tasks claimed from Redis.

    Embarrassingly parallel — multiple instances can run concurrently.
    Each Engineer claims one signal at a time, evaluates feasibility,
    writes code, and loops.
    """

    role = "engineer"

    def __init__(self, project_dir: Path, agent_id: str = "engineer-0", **kwargs):
        super().__init__(**kwargs)
        self.project_dir = project_dir
        self.agent_id = agent_id
        eng_cfg = self.config.get("agents", {}).get("engineer", {})
        self.max_defer_requeues: int = eng_cfg.get("max_defer_requeues", 3)

    # ── Main loop ────────────────────────────────────────────────────

    def run_loop(self, poll_interval: float = 1.0, stop_event=None) -> None:
        """Poll Redis for task/fix_request signals and process them.

        Args:
            poll_interval: seconds between polls when idle
            stop_event: threading.Event — when set, the loop exits
        """
        logger.info(f"[{self.agent_id}] Engineer started")
        max_retries = get_escalation_config().get("max_retries", 3)

        while stop_event is None or not stop_event.is_set():
            # Try fix_request first (higher priority — unblock QA cycle)
            signal = self.signals.claim_signal("fix_request", self.agent_id)
            if signal is None:
                signal = self.signals.claim_signal("task", self.agent_id)

            if signal is None:
                time.sleep(poll_interval)
                continue

            self._handle_signal(signal, max_retries)

        logger.info(f"[{self.agent_id}] Engineer stopped")

    # ── Signal handling ──────────────────────────────────────────────

    def _handle_signal(self, signal: dict, max_retries: int) -> None:
        """Process a single task or fix_request signal."""
        signal_type = signal.get("type", "task")
        file_rel = signal.get("file", "")
        layer = signal.get("layer", "")
        description = signal.get("description", "")
        details = signal.get("details", "")

        if not file_rel:
            logger.warning(f"[{self.agent_id}] Signal missing 'file' field: {signal.get('id')}")
            return

        # Enforce retry cap on fix_request signals — delete file so PM can re-plan
        if signal_type == "fix_request":
            retries = self.signals.increment_retries(file_rel)
            if retries > max_retries:
                logger.warning(
                    f"[{self.agent_id}] {file_rel} exceeded max retries ({max_retries}) "
                    f"— deleting file so PM can re-plan"
                )
                self._delete_failed_file(file_rel, layer)
                self.log_operation("retry_exhausted", self.project_dir, {
                    "file": file_rel, "retries": retries,
                })
                return

        logger.info(f"[{self.agent_id}] Processing {signal_type}: {file_rel} (layer={layer})")

        prd = self.read_prd(self.project_dir) or ""
        green_summary = self._get_green_summary()

        # ── fix_request: skip evaluation, go straight to fix ──────
        if signal_type == "fix_request":
            self._write_and_submit(file_rel, layer, description, prd,
                                   fix_details=details)
            return

        # ── task: evaluate feasibility first ──────────────────────
        evaluation = self._evaluate_task(file_rel, description, prd, green_summary)
        verdict = evaluation.get("verdict", "complete")

        if verdict == "complete":
            # Path A — task is completable with existing context
            resolved_layer = evaluation.get("layer", layer)
            deps = evaluation.get("dependencies", [])
            logger.info(
                f"[{self.agent_id}] Task completable: {file_rel} "
                f"(layer={resolved_layer}, deps={deps})"
            )
            self._write_and_submit(file_rel, resolved_layer, description, prd)
        else:
            # Path B — not completable; check defer cap first
            defer_count = self.signals.increment_defers(file_rel)
            if defer_count > self.max_defer_requeues:
                logger.warning(
                    f"[{self.agent_id}] {file_rel} deferred {defer_count} times "
                    f"(max {self.max_defer_requeues}) — forcing completion attempt"
                )
                self.signals.reset_defers(file_rel)
                self._write_and_submit(file_rel, layer, description, prd)
                return

            # Build a smaller sub-task first, then re-queue original
            sub = evaluation.get("sub_task", {})
            sub_file = sub.get("file", "")
            sub_layer = sub.get("layer", "")
            sub_desc = sub.get("description", "")

            if sub_file:
                logger.info(
                    f"[{self.agent_id}] Task deferred ({defer_count}/{self.max_defer_requeues}): "
                    f"{file_rel} → building sub-task {sub_file} first"
                )
                self._write_and_submit(sub_file, sub_layer, sub_desc, prd)
            else:
                logger.warning(
                    f"[{self.agent_id}] Evaluation returned 'defer' but no sub_task "
                    f"for {file_rel} — skipping"
                )

            # Re-queue the original task so it gets picked up later
            self.signals.push_signal("task", {
                "file": file_rel,
                "layer": layer,
                "description": description,
                "depends_on": signal.get("depends_on", []),
            }, producer=self.agent_id)
            self.log_operation("task_deferred", self.project_dir, {
                "file": file_rel, "sub_task": sub_file,
                "defer_count": defer_count,
            })

    # ── Task evaluation (LLM) ────────────────────────────────────────

    def _evaluate_task(
        self, file_rel: str, description: str, prd: str, green_summary: str,
    ) -> dict:
        """Ask the LLM whether the task can be completed with current green code.

        Returns a dict with:
            verdict: "complete" or "defer"
            layer: str           (path A — resolved layer for the file)
            dependencies: list   (path A — green files this will import)
            sub_task: dict       (path B — {file, layer, description})
        """
        context_parts = []
        api_ref = self.get_kaplay_api_reference()
        if api_ref:
            context_parts.append(f"Kaplay API Reference:\n{api_ref}")
        context_parts.append(f"PRD:\n{prd}")
        if green_summary:
            context_parts.append(green_summary)
        context = "\n\n".join(context_parts)

        prompt = (
            f"You are a senior engineer evaluating a coding task.\n\n"
            f"TASK: Write `{file_rel}`\n"
            f"DESCRIPTION: {description}\n\n"
            "Look at the verified (green) file signatures above and decide:\n\n"
            "A) Can you COMPLETE this file right now using only the Kaplay API "
            "and the green files as imports?\n"
            "   If YES, return:\n"
            "   {\"verdict\": \"complete\",\n"
            "    \"layer\": \"<layer_N directory, or empty string for root>\",\n"
            "    \"dependencies\": [\"<green file paths this file will import>\"]}\n\n"
            "B) Is there a MISSING helper, config, or utility that should exist first?\n"
            "   If YES, return:\n"
            "   {\"verdict\": \"defer\",\n"
            "    \"reason\": \"<what is missing>\",\n"
            "    \"sub_task\": {\n"
            "      \"file\": \"<helper filename to build now>\",\n"
            "      \"layer\": \"<layer_N directory for the helper>\",\n"
            "      \"description\": \"<what the helper should do>\"\n"
            "    }}\n\n"
            "DIRECTORY RULES:\n"
            "- ALL directories MUST be named layer_1, layer_2, layer_3, etc.\n"
            "- No other directory names are allowed.\n"
            "- main.js goes in root (layer='').\n\n"
            "RULES:\n"
            "- Always do the next right thing — pick the smallest useful step.\n"
            "- Only defer if a CONCRETE dependency is missing, not for vague reasons.\n"
            "- The sub_task must be a single file that is independently testable.\n"
            "- Return ONLY valid JSON, no markdown fences."
        )

        raw = self.llm.generate_json(prompt, context=context)
        try:
            result = json.loads(raw)
            if isinstance(result, dict) and result.get("verdict") in ("complete", "defer"):
                return result
            logger.warning(f"[{self.agent_id}] Unexpected evaluation format: {raw[:200]}")
        except json.JSONDecodeError:
            logger.warning(f"[{self.agent_id}] Failed to parse evaluation: {raw[:200]}")

        # Default: assume completable (don't block on bad LLM output)
        return {"verdict": "complete", "layer": "", "dependencies": []}

    # ── Write code and submit to QA ──────────────────────────────────

    def _write_and_submit(
        self,
        file_rel: str,
        layer: str,
        description: str,
        prd: str,
        fix_details: Optional[str] = None,
    ) -> None:
        """Generate code for a file, write it to disk, and push task_done."""
        # Resolve full path
        if layer:
            file_path = self.project_dir / layer / file_rel
        else:
            file_path = self.project_dir / file_rel

        existing_code = self.read_file_content(file_path)
        # Filter green summary to only include lower layers
        layer_summary = self._get_green_summary(target_layer=layer)
        context = self._build_context(prd, file_rel, layer, existing_code,
                                      fix_details, layer_summary)

        code = self._generate_code(
            filename=file_rel,
            description=description,
            context=context,
            existing_code=existing_code,
            fix_details=fix_details,
        )

        # Handle halt protocol
        if code.strip().startswith("{") and '"halt"' in code:
            try:
                halt_data = json.loads(code)
                if halt_data.get("halt"):
                    reason = halt_data.get("reason", "unknown")
                    logger.warning(f"[{self.agent_id}] HALT on {file_rel}: {reason}")
                    self.log_operation("halt", self.project_dir, {
                        "file": file_rel, "reason": reason,
                    })
                    return
            except json.JSONDecodeError:
                pass

        # Write the code
        self.write_file(file_path, code)
        action = "fix" if existing_code else "create"
        logger.info(f"[{self.agent_id}] {action.capitalize()}d {file_rel}")

        # Push task_done signal for QA
        done_path = f"{layer}/{file_rel}" if layer else file_rel
        self.signals.push_signal("task_done", {
            "file": file_rel,
            "layer": layer,
            "path": done_path,
        }, producer=self.agent_id)

        self.log_operation(f"file_{action}", self.project_dir, {
            "file": file_rel, "layer": layer,
        })

    # ── File cleanup ───────────────────────────────────────────────────

    def _delete_failed_file(self, file_rel: str, layer: str) -> None:
        """Delete a file that exhausted retries so PM can re-plan from scratch."""
        if layer:
            file_path = self.project_dir / layer / file_rel
            green_path = f"{layer}/{file_rel}"
        else:
            file_path = self.project_dir / file_rel
            green_path = file_rel

        if file_path.exists():
            file_path.unlink()
            logger.info(f"[{self.agent_id}] Deleted failed file: {file_path}")

        # Remove from green set and reset counters so PM sees it as missing
        self.signals.remove_green(green_path)
        self.signals.reset_retries(file_rel)
        self.signals.reset_defers(file_rel)

    # ── Green summary helper ─────────────────────────────────────────

    def _get_green_summary(self, target_layer: Optional[str] = None) -> str:
        """Build a compact summary of verified (green) files.

        Args:
            target_layer: Controls which files to include.
                None  — include ALL green files (used for evaluation).
                ""    — root layer: include ALL green files.
                "X"   — include only files from layers lower than X.
        """
        if not self.signals:
            return ""
        green_paths = sorted(self.signals.all_green_paths())
        if not green_paths:
            return ""

        # Filter by layer if a target is specified
        if target_layer is not None:
            green_paths = [
                gp for gp in green_paths
                if self._is_lower_layer(self._layer_of(gp), target_layer)
            ]

        # Sort by layer depth descending — highest (closest) layers first
        green_paths.sort(
            key=lambda gp: self._layer_depth(self._layer_of(gp)),
            reverse=True,
        )

        summaries = {}
        for gp in green_paths:
            full = self.project_dir / gp
            summary = summarize_file(full)
            if summary:
                summaries[gp] = summary
        return format_summaries(
            summaries,
            header="Verified (green) project file signatures",
            preserve_order=True,
        )

    # ── Layer ordering helpers ────────────────────────────────────────

    @staticmethod
    def _layer_of(file_path: str) -> str:
        """Extract the layer (first directory component) from a relative path."""
        parts = file_path.split("/")
        return parts[0] if len(parts) > 1 else ""

    @staticmethod
    def _extract_layer_num(layer: str) -> Optional[int]:
        """Extract a trailing number from a layer name (e.g. 'layer_2' → 2)."""
        m = re.search(r'(\d+)$', layer)
        return int(m.group(1)) if m else None

    @classmethod
    def _layer_depth(cls, layer: str) -> int:
        """Return a numeric depth for sorting. Higher number = later in build order.

        - layer_1 → 1, layer_2 → 2, etc.
        - Root ("") → 999 (always last / highest).
        """
        if not layer:
            return 999
        num = cls._extract_layer_num(layer)
        return num if num is not None else 0

    @classmethod
    def _is_lower_layer(cls, file_layer: str, target_layer: str) -> bool:
        """Check if file_layer is lower (earlier in build order) than target_layer.

        Only layer_X directories and root ("") are valid.
            - Root target ("") sees everything → always True.
            - Same layer → False.
            - Otherwise compare layer numbers: layer_1 < layer_2 < ... < root.
        """
        if not target_layer:
            # Root layer — include everything
            return True
        if not file_layer:
            # Root files are NOT deps of any layer_X
            return False
        if file_layer == target_layer:
            return False
        target_num = cls._extract_layer_num(target_layer)
        file_num = cls._extract_layer_num(file_layer)
        if target_num is not None and file_num is not None:
            return file_num < target_num
        return False

    # ── Context building ─────────────────────────────────────────────

    def _build_context(
        self, prd: str, file_rel: str, layer: str,
        existing_code: Optional[str], fix_details: Optional[str],
        green_summary: str = "",
    ) -> str:
        parts = []

        # Kaplay API reference
        api_ref = self.get_kaplay_api_reference()
        if api_ref:
            parts.append(api_ref)

        # Green files as dependency context (signatures + descriptions)
        if green_summary:
            parts.append(green_summary)

        parts.append(f"PRD:\n{prd}")

        if existing_code:
            parts.append(f"Current code for {file_rel}:\n```\n{existing_code}\n```")
        if fix_details:
            parts.append(f"Fix request details:\n{fix_details}")

        return "\n\n".join(parts)

    # ── Code generation (LLM) ────────────────────────────────────────

    def _generate_code(
        self,
        filename: str,
        description: str,
        context: str,
        existing_code: Optional[str] = None,
        fix_details: Optional[str] = None,
    ) -> str:
        contract = f"File: {filename}\nPurpose: {description}\n"
        contract += (
            "\nSTRICT RULES:\n"
            "- Write ONLY this file.\n"
            "- NEVER invent functions, properties, or variables not in the context.\n"
            "- KAPLAY LOADING: `kaplay` is a GLOBAL function loaded via <script> tag.\n"
            "  In main.js, call `const k = kaplay({...})` directly — do NOT import kaplay.\n"
            "- IMPORTS: Use relative paths with `.js` extension.\n"
            "  Import paths MUST match files that exist in the green files context.\n"
            "- If the contract is impossible to fulfill,\n"
            '  output ONLY: {"halt": true, "reason": "<what is missing>"}\n'
        )

        if existing_code and fix_details:
            prompt = (
                f"Fix the code in `{filename}` based on the test failure details.\n\n"
                f"CONTRACT:\n{contract}\n"
                "Return ONLY the complete, corrected source code. No markdown fences."
            )
        else:
            prompt = (
                f"Write the source code for `{filename}`.\n\n"
                f"CONTRACT:\n{contract}\n"
                "Return ONLY the complete source code. No markdown fences."
            )

        return self.llm.generate(prompt, context=context)
