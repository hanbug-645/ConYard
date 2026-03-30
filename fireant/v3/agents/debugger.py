import json
import logging
from pathlib import Path
from .base import BaseAgent
from ..utils.manifest import (
    MAX_ESCALATION_DEPTH,
    STANDARD_FILES,
    mark_code_done,
    rebuild_manifest_with_statuses,
    tree_shake_after_manifest_update,
)

logger = logging.getLogger("fireant")


class DebuggerAgent(BaseAgent):
    """Fixes code and propagates escalations through the folder tree.
    
    ═══════════════════════════════════════════════════════════════
    DUTY: DEBUG & PROPAGATE (Step 5)
    ═══════════════════════════════════════════════════════════════
    Triggered by escalation.json in a folder (from QA test failures
    or structural issues). Two abilities:
    
    1. LOCAL FIX — read the escalation, read all code in the folder,
       decide which files to rewrite, and rewrite them directly.
       After rewriting, statuses reset so QA re-checks.
    
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
    ═══════════════════════════════════════════════════════════════

    Trigger: escalation.json in current dir
    Action:  Fix files locally, then propagate up/down as needed.
    """

    role = "debugger"

    def build_folder_context(self, directory: Path) -> str:
        """Build full hierarchical context: parent + current + subdirs."""
        parts = []

        # Parent folder context
        parent_context = self.get_parent_dir_context(directory)
        if parent_context:
            parts.append(parent_context)

        # Current folder context
        current_context = self.get_current_dir_context(directory)
        if current_context:
            parts.append(current_context)

        # Subdirectory context
        subdir_context = self.get_subdir_context(directory)
        if subdir_context:
            parts.append(subdir_context)

        return "\n".join(parts)

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
        is_root = not (directory.parent / STANDARD_FILES["prd"]).exists()
        plan = self._analyze_escalation(
            prd_content, escalation_content, code_snapshot, folder_ctx,
            is_root=is_root,
        )

        manifest_update = plan.get("manifest_update") or {}
        if manifest_update.get("deliverables"):
            self._update_manifest(directory, manifest, manifest_update.get("deliverables", []))
            manifest = self.read_manifest(directory)

        # Rewrite files that need fixing
        rewrites = plan.get("rewrite_files", [])
        for entry in rewrites:
            filename = entry.get("filename", "")
            instructions = entry.get("fix_instructions", "")
            if not filename:
                continue
            self._rewrite_file(directory, filename, prd_content, instructions, folder_ctx)

        # ── Ability 2: propagate to parent / children ────────────────
        self._propagate(directory, plan, escalation_content, chain)

        # ── Cleanup ──────────────────────────────────────────────────
        self._cleanup(directory)

        self.log_operation("handle_escalation", directory, {
            "escalation_id": esc_id,
            "chain_len": len(chain),
            "rewrites": [e.get("filename") for e in rewrites],
            "manifest_updated": bool(manifest_update.get("deliverables")),
            "notify_parent": plan.get("notify_parent", False),
            "notify_children": [c.get("child_name") for c in plan.get("notify_children", [])],
        })

    # ── Ability 1: rewrite files ─────────────────────────────────────

    def _rewrite_file(
        self, directory: Path, filename: str, prd: str, fix_instructions: str,
        folder_ctx: str = "",
    ) -> None:
        """Rewrite a single file based on fix instructions."""
        code_path = directory / filename
        existing_code = code_path.read_text() if code_path.exists() else ""

        prompt = (
            f"Fix the code in `{filename}` based on these instructions.\n\n"
            f"FIX INSTRUCTIONS:\n{fix_instructions}\n\n"
            "STRICT RULES:\n"
            "- NEVER write `import kaplay from 'kaplay'` or any bare kaplay import.\n"
            "  Kaplay is loaded globally via <script> tag. Use `const k = kaplay({...})` directly.\n"
            "- Use ONLY relative imports with the `.js` extension.\n"
            "- Import paths MUST match files that actually exist in the folder context above.\n"
            "  Do NOT invent paths like `./lib/constants.js` if the real file is `./config/constants.js`.\n\n"
            "Return ONLY the complete, corrected source code. No markdown fences."
        )

        api_ref = self.get_kaplay_api_reference()
        context_parts = []
        if api_ref:
            context_parts.append(api_ref)
        if folder_ctx:
            context_parts.append(f"Folder Context:\n{folder_ctx}")
        context_parts.append(f"PRD:\n{prd}")
        context_parts.append(f"Current code:\n```\n{existing_code}\n```")
        context = "\n\n".join(context_parts)

        new_code = self.llm.generate(prompt, context=context)

        code_path.parent.mkdir(parents=True, exist_ok=True)
        code_path.write_text(new_code)

        # Reset statuses so QA re-checks the new code
        try:
            mark_code_done(directory, filename)
        except (FileNotFoundError, KeyError):
            pass  # manifest may not track this file

        logger.info(f"[debugger] Rewrote {filename} in {directory}")

    def _update_manifest(self, directory: Path, old_manifest: dict | None, deliverables: list[dict]) -> None:
        """Replace manifest deliverables and tree-shake impacted dependents/subtrees."""
        new_manifest = rebuild_manifest_with_statuses(old_manifest, deliverables)
        self.write_manifest(directory, new_manifest)
        tree_shake = tree_shake_after_manifest_update(directory, old_manifest, new_manifest)
        logger.info(
            f"[debugger] Updated manifest in {directory} | reset_files={tree_shake['files']} | invalidated_children={tree_shake['children']}"
        )

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
        is_root = not (directory.parent / STANDARD_FILES["prd"]).exists()
        if plan.get("notify_parent") and is_root:
            logger.warning(
                f"[debugger] At project root {directory.name} — cannot notify parent. "
                f"Must fix locally or update manifest."
            )
        elif plan.get("notify_parent"):
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
        is_root: bool = False,
    ) -> dict:
        """Analyze escalation and produce a fix + propagation plan.

        Returns dict with:
          rewrite_files: [{filename, reason, fix_instructions}, ...]
          manifest_update: {deliverables: [...]}  (optional; replace manifest + tree-shake impacted nodes)
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
            + ("   *** THIS IS THE PROJECT ROOT — there is NO parent. You MUST fix locally "
               "(rewrite files or update manifest). Set notify_parent to false. ***\n"
               if is_root else "")
            + "   - notify_children: list children whose output/interface is wrong "
            "and need to adjust\n\n"
            "3. UPDATE MANIFEST — if the folder contract itself is wrong, you may return a new deliverables list.\n"
            "   Use this ONLY when exports or file split are structurally wrong.\n"
            "   If you update the manifest, impacted child folders and dependent files will be tree-shaken and rebuilt.\n\n"
            "Return a JSON object with:\n"
            "- \"rewrite_files\": [{\"filename\": \"...\", \"reason\": \"...\", "
            "\"fix_instructions\": \"...\"}] (empty [] if no local files need rewriting)\n"
            "- \"manifest_update\": {\"deliverables\": [{\"name\": \"...\", \"type\": \"file\"|\"directory\", \"description\": \"...\", \"exports\": {}}]} or {}\n"
            "- \"notify_parent\": true/false\n"
            "- \"parent_reason\": string (only if notify_parent is true)\n"
            "- \"notify_children\": [{\"child_name\": \"...\", \"reason\": \"...\"}] "
            "(empty [] if no children need notification)\n"
        )

        api_ref = self.get_kaplay_api_reference()
        ctx_parts = []
        if api_ref:
            ctx_parts.append(api_ref)
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
            return {"rewrite_files": [], "manifest_update": {}, "notify_parent": False, "notify_children": []}
