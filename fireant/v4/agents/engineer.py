"""Engineer agent — claims task/fix_request signals and writes code.

Polls Redis for:
    - `task` signals (new coding work from PM)
    - `fix_request` signals (QA failures to fix)

After writing code, pushes a `task_done` signal for QA.
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

from agents.base import BaseAgent
from utils.config import get_escalation_config

logger = logging.getLogger("fireant")


class EngineerAgent(BaseAgent):
    """Writes code for tasks claimed from Redis.

    Embarrassingly parallel — multiple instances can run concurrently.
    Each Engineer claims one signal at a time, writes code, and loops.
    """

    role = "engineer"

    def __init__(self, project_dir: Path, agent_id: str = "engineer-0", **kwargs):
        super().__init__(**kwargs)
        self.project_dir = project_dir
        self.agent_id = agent_id

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

        # Enforce retry cap on fix_request signals
        if signal_type == "fix_request":
            retries = self.signals.increment_retries(file_rel)
            if retries > max_retries:
                logger.warning(
                    f"[{self.agent_id}] {file_rel} exceeded max retries ({max_retries}) — giving up"
                )
                self.log_operation("retry_exhausted", self.project_dir, {
                    "file": file_rel, "retries": retries,
                })
                return

        # Resolve full path
        if layer:
            file_path = self.project_dir / layer / file_rel
        else:
            file_path = self.project_dir / file_rel

        logger.info(f"[{self.agent_id}] Processing {signal_type}: {file_rel} (layer={layer})")

        prd = self.read_prd(self.project_dir) or ""
        existing_code = self.read_file_content(file_path)

        # Build context from green (verified) files
        context = self._build_context(prd, file_rel, layer, existing_code, details)

        # Generate code
        code = self._generate_code(
            filename=file_rel,
            description=description,
            context=context,
            existing_code=existing_code,
            fix_details=details if signal_type == "fix_request" else None,
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

    # ── Context building ─────────────────────────────────────────────

    def _build_context(
        self, prd: str, file_rel: str, layer: str,
        existing_code: Optional[str], fix_details: Optional[str],
    ) -> str:
        parts = []

        # Kaplay API reference
        api_ref = self.get_kaplay_api_reference()
        if api_ref:
            parts.append(api_ref)

        # Green files as dependency context
        if self.signals:
            green_paths = sorted(self.signals.all_green_paths())
            if green_paths:
                dep_lines = ["=== Verified (green) project files ==="]
                for gp in green_paths:
                    full = self.project_dir / gp
                    if full.exists():
                        code = full.read_text()
                        preview = "\n".join(code.splitlines()[:60])
                        dep_lines.append(f"--- {gp} ---\n{preview}")
                parts.append("\n".join(dep_lines))

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
