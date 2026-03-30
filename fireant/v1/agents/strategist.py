import json
import logging
from pathlib import Path
from typing import Optional

from .base import BaseAgent
from ..utils.config import get_escalation_config, get_parallel_config
from ..utils.manifest import STANDARD_FILES, create_manifest, load_manifest, save_manifest

logger = logging.getLogger("fireant")


class StrategistAgent(BaseAgent):
    """Risk assessment, escalation handling, and parallel approach spawning.

    Trigger (escalation): escalation.md in a child dir, or child status is blocked.
    Trigger (risk):       After Architect creates structure, reviews manifest for risk flags.
    Actions: re-plan, spawn parallel approaches, issue change_request.md to PM.
    """

    role = "strategist"

    def __init__(self, temperature_override: Optional[float] = None):
        super().__init__(temperature_override)
        self.parallel_config = get_parallel_config(self.config)
        self.escalation_config = get_escalation_config(self.config)

    def check_trigger(self, directory: Path) -> bool:
        if self._has_escalation_in_children(directory):
            return True
        if self._has_blocked_children(directory):
            return True
        if self._has_unreviewed_risk(directory):
            return True
        return False

    def _execute_impl(self, directory: Path) -> None:
        if self._has_escalation_in_children(directory):
            self._handle_escalation(directory)
        elif self._has_blocked_children(directory):
            self._handle_blocked(directory)
        elif self._has_unreviewed_risk(directory):
            self._review_risk(directory)

    # ── Trigger checks ───────────────────────────────────────────────

    def _has_escalation_in_children(self, directory: Path) -> bool:
        return len(self.get_child_escalations(directory)) > 0

    def _has_blocked_children(self, directory: Path) -> bool:
        return len(self.get_blocked(directory)) > 0

    def _has_unreviewed_risk(self, directory: Path) -> bool:
        """Disabled - no longer spawning parallel approaches."""
        return False

    # ── Actions ──────────────────────────────────────────────────────

    def _handle_escalation(self, directory: Path) -> None:
        """Respond to child escalations: re-plan, re-route, spawn parallel, or escalate further."""
        escalated_children = self.get_child_escalations(directory)
        manifest = self.read_manifest(directory)
        if manifest is None:
            return

        for child_dir in escalated_children:
            child_name = child_dir.name
            escalation_content = self.read_escalation(child_dir)
            prd_content = self.read_prd(directory)

            response = self._decide_escalation_response(
                prd_content or "",
                child_name,
                escalation_content or "",
            )

            action = response.get("action", "escalate_further")

            if action == "simplify":
                self._issue_change_request(child_dir, response.get("new_requirements", ""))
            elif action == "restructure":
                logger.info(f"[strategist] Restructure requested for {child_name} — Architect re-trigger needed")
                for d in manifest["deliverables"]:
                    if d["name"] == child_name:
                        d["status"] = "blocked"
                save_manifest(directory, manifest)
            elif action == "escalate_further":
                self.write_escalation(directory, (
                    f"# Escalation from {directory.name}\n\n"
                    f"Child `{child_name}` failed and could not be resolved at this level.\n\n"
                    f"Original escalation:\n{escalation_content}\n"
                ))
                logger.info(f"[strategist] Escalated further from {directory}")

            # Remove handled escalation to prevent re-triggering
            escalation_file = child_dir / STANDARD_FILES["escalation"]
            if escalation_file.exists():
                escalation_file.unlink()
                logger.debug(f"[strategist] Removed escalation.md from {child_dir}")

    def _handle_blocked(self, directory: Path) -> None:
        """Handle blocked deliverables by escalating further."""
        manifest = self.read_manifest(directory)
        if manifest is None:
            return

        for d in manifest["deliverables"]:
            if d["status"] == "blocked":
                self.write_escalation(directory, (
                    f"# Escalation: {d['name']}\n\n"
                    f"Deliverable '{d['name']}' is blocked and cannot proceed.\n\n"
                    f"Recommend simplifying requirements or restructuring.\n"
                ))
                logger.info(f"[strategist] Escalated blocked deliverable '{d['name']}' from {directory}")
                break

    def _review_risk(self, directory: Path) -> None:
        """Disabled - no longer spawning parallel approaches."""
        pass


    def _issue_change_request(self, target_dir: Path, new_requirements: str) -> None:
        self.write_change_request(target_dir, (
            f"# Change Request\n\n"
            f"The Strategist has determined the current PRD needs simplification.\n\n"
            f"## Updated Requirements\n\n{new_requirements}\n"
        ))
        logger.info(f"[strategist] Issued change_request.md to {target_dir}")

    # ── LLM calls ────────────────────────────────────────────────────

    def _decide_escalation_response(
        self, prd: str, child_name: str, escalation: str
    ) -> dict:
        prompt = (
            "A child component has escalated a failure. Decide the best response.\n\n"
            f"Parent PRD:\n{prd}\n\n"
            f"Failed child: {child_name}\n"
            f"Escalation details:\n{escalation}\n\n"
            "Return a JSON object with:\n"
            "- \"action\": one of \"simplify\", \"restructure\", \"escalate_further\"\n"
            "- \"reasoning\": brief explanation\n"
            "- \"new_requirements\": (only if action is \"simplify\") the simplified requirements\n"
        )
        raw = self.llm.generate_json(prompt)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error(f"[strategist] Failed to parse escalation response: {raw[:200]}")
            return {"action": "escalate_further"}
