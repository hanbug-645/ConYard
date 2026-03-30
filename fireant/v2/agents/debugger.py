import json
import logging
from pathlib import Path
from .base import BaseAgent
from ..utils.manifest import (
    MAX_ESCALATION_DEPTH,
    STANDARD_FILES,
    update_status,
)

logger = logging.getLogger("fireant")


class DebuggerAgent(BaseAgent):
    """Fixes code and propagates escalations through the folder tree.
    
    ═══════════════════════════════════════════════════════════════
    DUTY: DEBUG & PROPAGATE (Step 5)
    ═══════════════════════════════════════════════════════════════
    Triggered by escalation.json in a folder. Two abilities:
    
    1. LOCAL FIX — read the escalation, read all code in the folder,
       decide which files to rewrite, and rewrite them directly.
       After rewriting, files go back to 'in_progress' so Reviewer
       re-checks.
    
    2. PROPAGATE — analyze whether parent or child folders need to
       be notified about the issue. If so, create escalation.json
       there so Debugger runs recursively.
       - Parent: notify when the issue originates from a bad contract,
         missing dependency, or the folder cannot fulfill its role.
       - Children: notify when a child's output is wrong or its
         interface doesn't match expectations.
       - Siblings: NEVER directly. Sibling issues go through the
         parent, which decides how to propagate.
    
    Dead-loop prevention:
       Every escalation carries a chain (list of directory paths it
       has visited). Before propagating, check:
       a) target is not already in the chain → prevents A→B→A loops
       b) chain length < MAX_ESCALATION_DEPTH → hard safety cap
    
    What Debugger DOES NOT do:
    - Create new files (→ Architect + Engineer)
    - Review code (→ Reviewer)
    ═══════════════════════════════════════════════════════════════

    Trigger: escalation.json in current dir
    Action:  Fix files locally, then propagate up/down as needed.
    """

    role = "debugger"

    def check_trigger(self, directory: Path) -> bool:
        return self.has_escalation(directory)

    def _execute_impl(self, directory: Path) -> None:
        self._handle_escalation(directory)

    # ── Core logic ───────────────────────────────────────────────────

    def _handle_escalation(self, directory: Path) -> None:
        """Handle an escalation in this folder: fix locally, then propagate."""
        esc_data = self.read_escalation_full(directory) or {}
        esc_id = esc_data.get("id", "unknown")
        chain = esc_data.get("chain", [])
        escalation_content = esc_data.get("content", "")

        logger.info(f"[debugger] Handling escalation {esc_id} in {directory.name} (chain len={len(chain)})")

        prd_content = self.read_prd(directory) or ""
        manifest = self.read_manifest(directory)

        # Gather all code files in this folder
        code_snapshot = self._read_code_snapshot(directory, manifest)

        # ── Ability 1: decide what to fix locally ────────────────────
        folder_ctx = self.build_folder_context(directory)
        plan = self._analyze_escalation(
            prd_content, escalation_content, code_snapshot, folder_ctx,
        )

        # Rewrite files that need fixing
        rewrites = plan.get("rewrite_files", [])
        for entry in rewrites:
            filename = entry.get("filename", "")
            instructions = entry.get("fix_instructions", "")
            if not filename:
                continue
            self._rewrite_file(directory, filename, prd_content, instructions)

        # ── Ability 2: propagate to parent / children ────────────────
        self._propagate(directory, plan, escalation_content, chain)

        # ── Cleanup ──────────────────────────────────────────────────
        self._cleanup(directory)

        self.log_operation("handle_escalation", directory, {
            "escalation_id": esc_id,
            "chain_len": len(chain),
            "rewrites": [e.get("filename") for e in rewrites],
            "notify_parent": plan.get("notify_parent", False),
            "notify_children": [c.get("child_name") for c in plan.get("notify_children", [])],
        })

    # ── Ability 1: rewrite files ─────────────────────────────────────

    def _rewrite_file(
        self, directory: Path, filename: str, prd: str, fix_instructions: str,
    ) -> None:
        """Rewrite a single file based on fix instructions."""
        code_path = directory / filename
        existing_code = code_path.read_text() if code_path.exists() else ""

        prompt = (
            f"Fix the code in `{filename}` based on these instructions.\n\n"
            f"FIX INSTRUCTIONS:\n{fix_instructions}\n\n"
            "Return ONLY the complete, corrected source code. No markdown fences."
        )
        context = f"PRD:\n{prd}\n\nCurrent code:\n```\n{existing_code}\n```"

        new_code = self.llm.generate(prompt, context=context)

        code_path.parent.mkdir(parents=True, exist_ok=True)
        code_path.write_text(new_code)

        # Reset status to in_progress so Reviewer re-checks
        try:
            update_status(directory, filename, "in_progress")
        except (FileNotFoundError, KeyError):
            pass  # manifest may not track this file

        logger.info(f"[debugger] Rewrote {filename} in {directory}")

    def _read_code_snapshot(self, directory: Path, manifest: dict | None) -> dict[str, str]:
        """Read all file deliverables' code in this folder."""
        snapshot: dict[str, str] = {}
        if manifest is None:
            return snapshot
        for d in manifest.get("deliverables", []):
            if d.get("type") != "file":
                continue
            code_path = directory / d["name"]
            if code_path.exists():
                snapshot[d["name"]] = code_path.read_text()
        return snapshot

    # ── Ability 2: propagate (with dead-loop prevention) ─────────────

    def _propagate(
        self,
        directory: Path,
        plan: dict,
        original_escalation: str,
        chain: list[str],
    ) -> None:
        """Create escalation.json in parent or child folders as needed.

        Dead-loop prevention:
        - Skip if target directory path is already in the chain
        - Skip if chain length >= MAX_ESCALATION_DEPTH
        """
        # ── Check depth cap ──────────────────────────────────────────
        if len(chain) >= MAX_ESCALATION_DEPTH:
            logger.warning(
                f"[debugger] Escalation chain reached max depth ({MAX_ESCALATION_DEPTH}) "
                f"in {directory.name} — stopping propagation"
            )
            return

        # ── Notify parent ────────────────────────────────────────────
        if plan.get("notify_parent"):
            reason = plan.get("parent_reason", "Child folder could not resolve its issue.")
            parent = directory.parent
            parent_str = str(parent)

            if parent_str in chain:
                logger.warning(
                    f"[debugger] Loop detected: {directory.name} → parent {parent.name} "
                    f"already in chain — skipping"
                )
            elif not (parent / STANDARD_FILES["prd"]).exists():
                logger.debug(f"[debugger] Parent {parent.name} has no prd.md — skip")
            else:
                self.write_escalation(
                    parent,
                    (
                        f"# Escalation from child `{directory.name}`\n\n"
                        f"## Reason\n{reason}\n\n"
                        f"## Original Issue\n{original_escalation}\n"
                    ),
                    chain=chain,
                )
                logger.info(f"[debugger] Notified parent {parent.name} from {directory.name}")

        # ── Notify children ──────────────────────────────────────────
        for child_info in plan.get("notify_children", []):
            child_name = child_info.get("child_name", "")
            reason = child_info.get("reason", "")
            if not child_name:
                continue

            child_dir = directory / child_name
            child_str = str(child_dir)

            if child_str in chain:
                logger.warning(
                    f"[debugger] Loop detected: {directory.name} → child {child_name} "
                    f"already in chain — skipping"
                )
                continue

            if not child_dir.is_dir():
                logger.debug(f"[debugger] Child {child_name} not found — skip")
                continue

            self.write_escalation(
                child_dir,
                (
                    f"# Escalation from parent `{directory.name}`\n\n"
                    f"## Reason\n{reason}\n\n"
                    f"## Original Issue\n{original_escalation}\n"
                ),
                chain=chain,
            )
            logger.info(f"[debugger] Notified child {child_name} from {directory.name}")

    # ── Cleanup ──────────────────────────────────────────────────────

    def _cleanup(self, directory: Path) -> None:
        """Remove escalation and review artifacts from this folder."""
        for fname in (STANDARD_FILES["escalation"], STANDARD_FILES["review"]):
            path = directory / fname
            if path.exists():
                path.unlink()
        # Remove status_pass so folder can be re-evaluated
        status_path = directory / STANDARD_FILES["status_pass"]
        if status_path.exists():
            status_path.unlink()

    # ── Server-mode debug (called by Manager) ────────────────────────

    def analyze_and_fix(self, directory: Path, instructions: str) -> dict:
        """Create escalation and handle it immediately.
        
        Called directly by Manager for DEBUG commands.
        """
        logger.info(f"[debugger] Analyzing project for: {instructions}")
        self.log_operation("debug_start", directory, {"instructions": instructions})

        self.write_escalation(directory, (
            f"# Debug Request\n\n"
            f"## Issue Description\n{instructions}\n\n"
            f"## Action Required\n"
            f"Investigate and fix the reported issue.\n"
        ))
        self._handle_escalation(directory)

        self.log_operation("debug_complete", directory)
        return {"success": True, "message": "Debug escalation handled."}

    # ── LLM calls ────────────────────────────────────────────────────

    def _analyze_escalation(
        self,
        prd: str,
        escalation: str,
        code_snapshot: dict[str, str],
        folder_ctx: str = "",
    ) -> dict:
        """Analyze escalation and produce a fix + propagation plan.

        Returns dict with:
          rewrite_files: [{filename, reason, fix_instructions}, ...]
          notify_parent: bool
          parent_reason: str  (why parent needs to know)
          notify_children: [{child_name, reason}, ...]
        """
        # Build code context
        code_sections = []
        for fname, code in code_snapshot.items():
            code_sections.append(f"=== {fname} ===\n```\n{code}\n```")
        code_context = "\n\n".join(code_sections) if code_sections else "(no code files)"

        prompt = (
            "An escalation has been raised in this folder. Analyze it and produce a plan.\n\n"
            "You have TWO abilities:\n\n"
            "1. REWRITE FILES — decide which files in THIS folder need to be "
            "rewritten to fix the issue. Provide specific fix instructions for each.\n\n"
            "2. PROPAGATE — decide if parent or child folders need to be notified:\n"
            "   - notify_parent: true if the issue cannot be fully fixed here "
            "(e.g., bad contract from parent, this folder can't fulfill its role, "
            "or a sibling folder needs to change — sibling issues ALWAYS go through parent)\n"
            "   - notify_children: list children whose output/interface is wrong "
            "and need to adjust\n\n"
            "Return a JSON object with:\n"
            "- \"rewrite_files\": [{\"filename\": \"...\", \"reason\": \"...\", "
            "\"fix_instructions\": \"...\"}] (empty [] if no local files need rewriting)\n"
            "- \"notify_parent\": true/false\n"
            "- \"parent_reason\": string (only if notify_parent is true)\n"
            "- \"notify_children\": [{\"child_name\": \"...\", \"reason\": \"...\"}] "
            "(empty [] if no children need notification)\n"
        )

        ctx_parts = []
        if folder_ctx:
            ctx_parts.append(f"Folder Context:\n{folder_ctx}")
        ctx_parts.append(f"PRD:\n{prd}")
        ctx_parts.append(f"Escalation:\n{escalation}")
        ctx_parts.append(f"Code files:\n{code_context}")
        context = "\n\n".join(ctx_parts)

        raw = self.llm.generate_json(prompt, context=context)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error(f"[debugger] Failed to parse analysis: {raw[:200]}")
            return {"rewrite_files": [], "notify_parent": False, "notify_children": []}
