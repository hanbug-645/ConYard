import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from ..utils.config import get_orchestrator_config
from ..utils.manifest import STANDARD_FILES, load_manifest, rollup_tree, all_passed, get_blocked_deliverables
from ..utils.operation_log import OperationLogger
from ..agents.architect import ArchitectAgent
from ..agents.debugger import DebuggerAgent
from ..agents.engineer import EngineerAgent
from ..agents.qa_engineer import QAEngineerAgent

logger = logging.getLogger("fireant")

# Directories to skip during tree scanning
_SKIP_DIRS = {"lib", "test", "node_modules", "__pycache__"}


class Pipeline:
    """Two-phase pipeline: Architect top-down, then Engineer bottom-up.

    Phase 1 — ARCHITECT (top-down):
      Start at root, create manifests + subdirectory PRDs.
      Repeat until all directories have manifests.
      Order: parent before children (BFS).

    Phase 2 — ENGINEER (bottom-up):
      Build code from leaves to root.
      Deepest directories first, so parent files can see
      actual child code/exports when they are written.
      Includes QA + Debugger cycles per directory.
    """

    def __init__(self, max_iterations: Optional[int] = None, poll_interval: Optional[float] = None, max_concurrent_agents: Optional[int] = None):
        config = get_orchestrator_config()
        self.max_iterations = max_iterations if max_iterations is not None else config["max_iterations"]
        self.poll_interval = poll_interval if poll_interval is not None else config["poll_interval"]
        self.max_concurrent_agents = max_concurrent_agents if max_concurrent_agents is not None else config["max_concurrent_agents"]

        self._architect = ArchitectAgent()
        self._engineer = EngineerAgent()
        self._qa_engineer = QAEngineerAgent()
        self._debugger = DebuggerAgent()

        self._error_counts: dict[tuple[Path, str], int] = {}  # keyed by (directory, agent_role)
        self._max_consecutive_errors = 3
        self._handled_escalation_ids: set[str] = set()
        self._error_lock = threading.Lock()

    def run(self, project_root: Path) -> bool:
        """Run the two-phase pipeline.

        Returns True if the project reached completion.
        """
        logger.info(f"[pipeline] Starting on {project_root}")

        # Initialize operation logger for all agents
        op_logger = OperationLogger(project_root)
        for agent in (self._architect, self._engineer, self._qa_engineer, self._debugger):
            agent.set_operation_logger(op_logger)

        # Phase 1: Architect top-down
        logger.info("[pipeline] === PHASE 1: ARCHITECT (top-down) ===")
        if not self._run_architect_phase(project_root):
            logger.warning("[pipeline] Architect phase did not complete")
            return False

        # Phase 2: Engineer bottom-up
        logger.info("[pipeline] === PHASE 2: ENGINEER (bottom-up) ===")
        if not self._run_engineer_phase(project_root):
            logger.warning("[pipeline] Engineer phase did not complete")
            return False

        logger.info("[pipeline] Project complete!")
        return True

    # ── Phase 1: Architect (top-down) ─────────────────────────────────

    def _run_architect_phase(self, project_root: Path) -> bool:
        """Run architect on all directories top-down until all have manifests.

        Uses BFS ordering so parents are processed before children.
        """
        for iteration in range(1, self.max_iterations + 1):
            needs_architect = self._find_dirs_needing_architect(project_root)
            if not needs_architect:
                logger.info(f"[pipeline] Architect phase complete after {iteration - 1} iterations")
                return True

            logger.info(f"[pipeline] Architect iteration {iteration}: {len(needs_architect)} dirs need manifests")

            # Process in BFS order (shallowest first = top-down)
            needs_architect.sort(key=lambda d: len(d.parts))

            dispatched = self._execute_parallel(self._architect, needs_architect, iteration)
            if dispatched == 0:
                logger.warning("[pipeline] Architect phase stalled — no agents dispatched")
                return False

            time.sleep(self.poll_interval)

        logger.warning("[pipeline] Architect phase hit max iterations")
        return False

    def _find_dirs_needing_architect(self, root: Path) -> list[Path]:
        """Find all directories that have a PRD but no manifest (BFS).
        
        Enforces a max depth of 3 levels below root as a safety cap
        to prevent infinite subdirectory recursion.
        """
        max_depth = 3
        root_depth = len(root.parts)
        result = []
        queue = [root]
        while queue:
            directory = queue.pop(0)
            depth = len(directory.parts) - root_depth

            has_prd = (directory / STANDARD_FILES["prd"]).exists()
            has_manifest = load_manifest(directory) is not None

            if has_prd and not has_manifest:
                if depth <= max_depth:
                    result.append(directory)
                else:
                    logger.warning(f"[pipeline] Skipping {directory.name} — depth {depth} exceeds max {max_depth}")

            # Recurse into subdirs
            if has_manifest and depth < max_depth:
                for child in sorted(directory.iterdir()):
                    if child.is_dir() and not child.name.startswith((".", "_")):
                        if child.name not in _SKIP_DIRS:
                            queue.append(child)

        return result

    # ── Phase 2: Engineer (bottom-up) ─────────────────────────────────

    def _run_engineer_phase(self, project_root: Path) -> bool:
        """Run engineer + QA + debugger on all directories.

        Bottom-up: deepest directories first so child code exists before
        parent files are written. Stops early if nothing is actionable
        for 3 consecutive iterations.
        """
        stale_count = 0
        max_stale = 3

        for iteration in range(1, self.max_iterations + 1):
            rollup_tree(project_root)

            blocked_without_escalation = self._collect_terminal_blocked_deliverables(project_root)
            if blocked_without_escalation:
                logger.warning(
                    f"[pipeline] Engineer phase blocked — unresolved deliverables without escalation: {blocked_without_escalation}"
                )
                return False

            # Check if everything is complete
            if all_passed(project_root):
                logger.info(f"[pipeline] Engineer phase complete after {iteration - 1} iterations")
                return True

            work_groups = self._plan_engineer_phase_work(project_root)
            if not work_groups:
                stale_count += 1
                if stale_count >= max_stale:
                    logger.warning(f"[pipeline] Engineer phase stalled — nothing actionable for {max_stale} iterations. Stopping.")
                    return False
                logger.warning(f"[pipeline] Engineer iteration {iteration}: nothing actionable ({stale_count}/{max_stale})")
                time.sleep(self.poll_interval)
                continue

            group_count = sum(len(group) for group in work_groups)
            logger.info(f"[pipeline] Engineer iteration {iteration}: {group_count} dirs need work")

            dispatched_any = False

            for index, group in enumerate(work_groups, start=1):
                if not group:
                    continue

                # Filter out error-capped and duplicate escalations
                actionable = []
                for directory, agent in group:
                    with self._error_lock:
                        error_key = (directory, agent.role)
                        if self._error_counts.get(error_key, 0) >= self._max_consecutive_errors:
                            logger.warning(f"[pipeline] Skipping {agent.role} on {directory} — too many errors")
                            continue
                    if agent.role == "debugger":
                        esc_id = self._read_escalation_id(directory)
                        if esc_id and esc_id in self._handled_escalation_ids:
                            continue
                    actionable.append((directory, agent))

                if not actionable:
                    continue

                dispatched_any = True
                label = f"group {index}"
                if len(actionable) == 1 or self.max_concurrent_agents == 1:
                    for directory, agent in actionable:
                        logger.info(f"[pipeline] Engineer: {agent.role} → {directory.name}")
                        self._execute_agent(agent, directory, project_root)
                else:
                    logger.info(f"[pipeline] Engineer: {len(actionable)} dirs in {label} in parallel")
                    with ThreadPoolExecutor(max_workers=self.max_concurrent_agents) as executor:
                        futures = {}
                        for directory, agent in actionable:
                            logger.info(f"[pipeline] Engineer: {agent.role} → {directory.name} (parallel)")
                            future = executor.submit(self._execute_agent, agent, directory, project_root)
                            futures[future] = (directory, agent)
                        for future in as_completed(futures):
                            directory, agent = futures[future]
                            try:
                                future.result()
                            except Exception as e:
                                logger.error(f"[pipeline] Parallel engineer error in {directory}: {e}")

            # If work was planned but everything got filtered out (error-capped),
            # count it as stale — otherwise reset the stale counter.
            if dispatched_any:
                stale_count = 0
            else:
                stale_count += 1
                if stale_count >= max_stale:
                    logger.warning(f"[pipeline] Engineer phase stalled — all work error-capped for {max_stale} iterations. Stopping.")
                    return False
                logger.warning(f"[pipeline] Engineer iteration {iteration}: all work filtered ({stale_count}/{max_stale})")

            time.sleep(self.poll_interval)

        logger.warning("[pipeline] Engineer phase hit max iterations")
        return False

    def _collect_terminal_blocked_deliverables(self, root: Path) -> list[str]:
        """Collect blocked deliverables that have no escalation for debugger to handle."""
        blocked: list[str] = []

        def scan(directory: Path) -> None:
            if not directory.is_dir():
                return

            if not (directory / STANDARD_FILES["escalation"]).exists():
                for deliverable in get_blocked_deliverables(directory):
                    blocked.append(f"{directory.relative_to(root) or Path('.')}/{deliverable['name']}")

            for child in sorted(directory.iterdir()):
                if child.is_dir() and not child.name.startswith((".", "_")):
                    if child.name not in _SKIP_DIRS:
                        scan(child)

        scan(root)
        return blocked

    def _collect_manifest_dirs(self, directory: Path, result: list[Path]) -> None:
        """Collect all directories in the project tree that have manifests."""
        if not directory.is_dir():
            return

        manifest = load_manifest(directory)
        if manifest is not None:
            result.append(directory)

        for child in sorted(directory.iterdir()):
            if child.is_dir() and not child.name.startswith((".", "_")):
                if child.name not in _SKIP_DIRS:
                    self._collect_manifest_dirs(child, result)

    def _directory_has_pending_engineer_work(self, directory: Path) -> bool:
        manifest = load_manifest(directory)
        if manifest is None:
            return False
        for deliverable in manifest.get("deliverables", []):
            if deliverable.get("type") != "file":
                continue
            if deliverable.get("coding_status") == "blocked":
                continue
            if deliverable.get("qa_status") == "fail":
                return True
            if deliverable.get("coding_status") == "pending":
                return True
        return False

    def _plan_engineer_phase_work(self, root: Path) -> list[list[tuple[Path, object]]]:
        """Plan work groups: debugger first, then QA, then flat engineer list.

        Engineers are sorted deepest-first so child directories are
        built before parent files that depend on them.
        """
        manifest_dirs: list[Path] = []
        self._collect_manifest_dirs(root, manifest_dirs)
        manifest_dirs = [directory for directory in manifest_dirs if not all_passed(directory)]

        debugger_group: list[tuple[Path, object]] = []
        qa_group: list[tuple[Path, object]] = []
        debugger_dirs: set[Path] = set()

        for directory in sorted(manifest_dirs, key=lambda d: len(d.parts), reverse=True):
            if self._debugger.check_trigger(directory):
                debugger_group.append((directory, self._debugger))
                debugger_dirs.add(directory)
                continue
            # QA and engineer can coexist on the same directory —
            # QA tests coded files, engineer writes pending files.
            if self._qa_engineer.check_trigger(directory):
                qa_group.append((directory, self._qa_engineer))

        # Flat engineer list — deepest dirs first so child code exists
        # before parent files are written.
        # Only debugger blocks engineer (structural fix in progress).
        engineer_candidates = [
            directory for directory in manifest_dirs
            if directory not in debugger_dirs
            and self._directory_has_pending_engineer_work(directory)
            and self._engineer.check_trigger(directory)
        ]
        engineer_candidates.sort(key=lambda d: (len(d.parts), str(d)), reverse=True)
        engineer_group: list[tuple[Path, object]] = [
            (directory, self._engineer) for directory in engineer_candidates
        ]

        groups: list[list[tuple[Path, object]]] = []
        if debugger_group:
            groups.append(debugger_group)
        if qa_group:
            groups.append(qa_group)
        if engineer_group:
            groups.append(engineer_group)
        return groups

    # ── Shared execution helpers ──────────────────────────────────────

    def _execute_parallel(self, agent, directories: list[Path], iteration: int) -> int:
        """Execute agent on multiple directories. Returns count of successes."""
        dispatched = 0

        if self.max_concurrent_agents == 1:
            for directory in directories:
                logger.info(f"[pipeline] Iteration {iteration}: {agent.role} → {directory}")
                if self._execute_agent(agent, directory):
                    dispatched += 1
            return dispatched

        with ThreadPoolExecutor(max_workers=self.max_concurrent_agents) as executor:
            future_to_dir = {}
            for directory in directories:
                logger.info(f"[pipeline] Iteration {iteration}: {agent.role} → {directory} (parallel)")
                future = executor.submit(self._execute_agent, agent, directory)
                future_to_dir[future] = directory

            for future in as_completed(future_to_dir):
                directory = future_to_dir[future]
                try:
                    if future.result():
                        dispatched += 1
                except Exception as e:
                    logger.error(f"[pipeline] Error in parallel execution for {directory}: {e}")

        return dispatched

    def _execute_agent(self, agent, directory: Path, project_root: Path | None = None) -> bool:
        """Execute a single agent on a directory. Returns True if successful."""
        esc_id = None
        if agent.role == "debugger":
            esc_id = self._read_escalation_id(directory)
        if agent.role == "engineer" and project_root is not None:
            agent.set_project_root(directory, project_root)

        try:
            agent.execute(directory)
            with self._error_lock:
                self._error_counts.pop((directory, agent.role), None)
                if esc_id:
                    self._handled_escalation_ids.add(esc_id)
            return True
        except Exception as e:
            with self._error_lock:
                error_key = (directory, agent.role)
                self._error_counts[error_key] = self._error_counts.get(error_key, 0) + 1
                error_count = self._error_counts[error_key]
            logger.error(
                f"[pipeline] {agent.role} failed on {directory} "
                f"(attempt {error_count}/{self._max_consecutive_errors}): {e}",
            )
            return False
        finally:
            if agent.role == "engineer":
                agent.clear_project_root(directory)

    def _read_escalation_id(self, directory: Path) -> str | None:
        """Read the escalation ID from a directory's escalation.json."""
        import json
        path = directory / STANDARD_FILES["escalation"]
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return data.get("id")
        except (json.JSONDecodeError, ValueError, OSError):
            return None
