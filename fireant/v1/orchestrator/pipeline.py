import logging
import time
from pathlib import Path
from typing import Optional

from .scanner import TreeScanner
from ..utils.manifest import load_manifest, rollup_tree
from ..utils.operation_log import OperationLogger
from ..agents.architect import ArchitectAgent
from ..agents.strategist import StrategistAgent
from ..agents.pm import PMAgent
from ..agents.engineer import EngineerAgent
from ..agents.reviewer import ReviewerAgent

logger = logging.getLogger("fireant")


class Pipeline:
    """Orchestrates agents by scanning the project tree and dispatching
    the appropriate agent to each directory that needs work.

    The pipeline runs in a loop:
      1. Scan the entire tree → list of (directory, state)
      2. For each directory with pending work, dispatch the matching agent
      3. Repeat until the root is complete or max iterations reached

    Agents are dispatched in priority order per scan cycle:
      Architect → Strategist → PM → Engineer → Reviewer → Voter
    This ensures upstream work (decomposition, risk review, PRD expansion)
    happens before downstream work (coding, reviewing, voting).
    """

    # Dispatch priority: agents that create structure run first
    DISPATCH_ORDER = [
        TreeScanner.NEEDS_ARCHITECT,
        TreeScanner.NEEDS_STRATEGIST_RISK,
        TreeScanner.NEEDS_STRATEGIST_ESCALATION,
        TreeScanner.NEEDS_PM,
        TreeScanner.NEEDS_ENGINEER,
        TreeScanner.NEEDS_REVIEWER,
    ]

    def __init__(self, max_iterations: int = 50, poll_interval: float = 1.0):
        self.max_iterations = max_iterations
        self.poll_interval = poll_interval
        self.scanner = TreeScanner()

        # Agent instances
        self.agents = {
            TreeScanner.NEEDS_ARCHITECT: ArchitectAgent(),
            TreeScanner.NEEDS_STRATEGIST_RISK: StrategistAgent(),
            TreeScanner.NEEDS_STRATEGIST_ESCALATION: StrategistAgent(),
            TreeScanner.NEEDS_PM: PMAgent(),
            TreeScanner.NEEDS_ENGINEER: EngineerAgent(),
            TreeScanner.NEEDS_REVIEWER: ReviewerAgent(),
        }
        
        # Cache of completed directories to skip in future scans
        self._completed_dirs: set[Path] = set()
        
        # Track consecutive errors per directory to avoid endless retries
        self._error_counts: dict[Path, int] = {}
        self._max_consecutive_errors = 3

    def run(self, project_root: Path) -> bool:
        """Run the pipeline until the project is complete or iterations exhausted.

        Returns True if the project reached completion.
        """
        logger.info(f"[pipeline] Starting on {project_root} (max {self.max_iterations} iterations)")

        # Initialize operation logger for this project
        op_logger = OperationLogger(project_root)
        for agent in self.agents.values():
            agent.set_operation_logger(op_logger)

        for iteration in range(1, self.max_iterations + 1):
            # Roll up child statuses to parent manifests (bottom-up)
            rollup_tree(project_root)

            scan_results = self.scanner.scan(project_root)

            # Separate actionable from terminal states
            # Skip directories we've already marked as complete
            actionable = [
                (d, state) for d, state in scan_results
                if state not in (TreeScanner.COMPLETE, TreeScanner.BLOCKED)
                and d not in self._completed_dirs
            ]
            
            # Update completed dirs cache
            for d, state in scan_results:
                if state == TreeScanner.COMPLETE:
                    self._completed_dirs.add(d)

            # Check if root is complete
            root_state = next(
                (state for d, state in scan_results if d == project_root),
                None,
            )
            if root_state == TreeScanner.COMPLETE:
                logger.info(f"[pipeline] Project complete after {iteration} iterations")
                return True

            if not actionable:
                # Nothing to do but root isn't marked complete — might be waiting
                # for child roll-up. Check if everything is actually done.
                all_complete = all(
                    state in (TreeScanner.COMPLETE, TreeScanner.BLOCKED)
                    for _, state in scan_results
                )
                if all_complete:
                    logger.info(f"[pipeline] All directories resolved after {iteration} iterations")
                    return True

                logger.warning(f"[pipeline] Iteration {iteration}: no actionable directories, but not complete")
                time.sleep(self.poll_interval)
                continue

            # Dispatch in priority order
            dispatched = 0
            for priority_state in self.DISPATCH_ORDER:
                dirs_for_state = [d for d, state in actionable if state == priority_state]
                if not dirs_for_state or priority_state not in self.agents:
                    continue

                agent = self.agents[priority_state]
                for directory in dirs_for_state:
                    logger.info(
                        f"[pipeline] Iteration {iteration}: "
                        f"dispatching {agent.role} → {directory}"
                    )
                    # Skip directories that have failed too many times consecutively
                    if self._error_counts.get(directory, 0) >= self._max_consecutive_errors:
                        if directory not in self._completed_dirs:
                            logger.warning(f"[pipeline] Skipping {directory} after {self._max_consecutive_errors} consecutive errors")
                            self._completed_dirs.add(directory)
                        continue

                    try:
                        agent.execute(directory)
                        dispatched += 1
                        self._error_counts.pop(directory, None)  # Reset on success
                    except Exception as e:
                        self._error_counts[directory] = self._error_counts.get(directory, 0) + 1
                        logger.error(
                            f"[pipeline] {agent.role} failed on {directory} "
                            f"(attempt {self._error_counts[directory]}/{self._max_consecutive_errors}): {e}",
                        )

            if dispatched == 0:
                logger.warning(f"[pipeline] Iteration {iteration}: no agents dispatched")

            self._log_progress(iteration, scan_results)
            time.sleep(self.poll_interval)

        logger.warning(f"[pipeline] Reached max iterations ({self.max_iterations})")
        return False

    def _log_progress(self, iteration: int, scan_results: list) -> None:
        """Log a compact progress summary."""
        counts = {}
        for _, state in scan_results:
            counts[state] = counts.get(state, 0) + 1

        parts = [f"{state}={count}" for state, count in sorted(counts.items())]
        logger.info(f"[pipeline] Iteration {iteration} progress: {', '.join(parts)}")
