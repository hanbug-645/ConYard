import json
import logging
from pathlib import Path
from typing import Optional

from .base import BaseAgent
from ..utils.config import get_escalation_config, get_parallel_config
from ..utils.manifest import create_manifest, load_manifest, save_manifest

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

    def execute(self, directory: Path) -> None:
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
        """True if manifest exists with high-risk items that haven't been
        converted to parallel mode yet."""
        manifest = self.read_manifest(directory)
        if manifest is None:
            return False
        for d in manifest.get("deliverables", []):
            if d.get("risk") == "high" and d.get("mode") == "single" and d.get("status") == "pending":
                return True
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

            if action == "spawn_parallel":
                self._spawn_parallel(directory, child_name, manifest)
            elif action == "simplify":
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

    def _handle_blocked(self, directory: Path) -> None:
        """Handle blocked deliverables by spawning parallel approaches."""
        manifest = self.read_manifest(directory)
        if manifest is None:
            return

        for d in manifest["deliverables"]:
            if d["status"] == "blocked" and d["mode"] == "single":
                self._spawn_parallel(directory, d["name"], manifest)

    def _review_risk(self, directory: Path) -> None:
        """Flag high-risk items for parallel execution."""
        manifest = self.read_manifest(directory)
        if manifest is None:
            return

        changed = False
        for d in manifest["deliverables"]:
            if d.get("risk") == "high" and d.get("mode") == "single" and d.get("status") == "pending":
                self._spawn_parallel(directory, d["name"], manifest)
                changed = True

        if changed:
            save_manifest(directory, manifest)

    def _spawn_parallel(self, directory: Path, deliverable_name: str, manifest: dict) -> None:
        """Create N competing candidate directories for a deliverable."""
        n_candidates = self.parallel_config.get("default_candidates", 3)
        temp_spread = self.parallel_config.get("temperature_spread", [0.3, 0.7, 1.0])

        original_dir = directory / deliverable_name
        original_prd = self.read_prd(original_dir) if original_dir.exists() else None

        candidates = []
        for i in range(n_candidates):
            suffix = chr(ord("A") + i)
            candidate_name = f"{deliverable_name}_{suffix}"
            candidate_dir = directory / candidate_name
            candidate_dir.mkdir(parents=True, exist_ok=True)

            if original_prd:
                self.write_prd(candidate_dir, original_prd)
            child_manifest = create_manifest([])
            candidate_temp = temp_spread[i] if i < len(temp_spread) else temp_spread[-1]
            child_manifest["temperature"] = candidate_temp
            self.write_manifest(candidate_dir, child_manifest)

            candidates.append(candidate_name)

        for d in manifest["deliverables"]:
            if d["name"] == deliverable_name:
                d["mode"] = "parallel"
                d["candidates"] = candidates
                d["status"] = "in_progress"
                d["temperature_spread"] = temp_spread[:n_candidates]
                break

        save_manifest(directory, manifest)
        logger.info(
            f"[strategist] Spawned {n_candidates} parallel candidates for "
            f"'{deliverable_name}' in {directory}"
        )

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
            "- \"action\": one of \"spawn_parallel\", \"simplify\", \"restructure\", \"escalate_further\"\n"
            "- \"reasoning\": brief explanation\n"
            "- \"new_requirements\": (only if action is \"simplify\") the simplified requirements\n"
        )
        raw = self.llm.generate_json(prompt)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error(f"[strategist] Failed to parse escalation response: {raw[:200]}")
            return {"action": "escalate_further"}
