import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from .scanner import TreeScanner
from ..utils.config import get_orchestrator_config
from ..utils.manifest import STANDARD_FILES, load_manifest, rollup_tree
from ..utils.operation_log import OperationLogger
from ..agents.architect import ArchitectAgent
from ..agents.debugger import DebuggerAgent
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

    Agent flow (per folder):
      1. Manager creates PRD at root (pre-pipeline, not in this loop)
      2. Architect creates manifest (files or subdirs, recursive)
      3. Engineer writes one file at a time
      4. Reviewer reviews all code in folder together
      5. Debugger handles escalations from Reviewer

    Pipeline agent priority order:
      Architect → Debugger → Engineer → Reviewer
    """

    def __init__(self, max_iterations: Optional[int] = None, poll_interval: Optional[float] = None, max_concurrent_agents: Optional[int] = None):
        # Load config with overrides
        config = get_orchestrator_config()
        self.max_iterations = max_iterations if max_iterations is not None else config["max_iterations"]
        self.poll_interval = poll_interval if poll_interval is not None else config["poll_interval"]
        self.max_concurrent_agents = max_concurrent_agents if max_concurrent_agents is not None else config["max_concurrent_agents"]

        # Create agent instances (each created once)
        self._architect = ArchitectAgent()
        self._debugger = DebuggerAgent()
        self._engineer = EngineerAgent()
        self._reviewer = ReviewerAgent()

        # Agent dispatch order: (state_name, agent_instance)
        # Priority: structure → escalation → implementation → review
        self.agent_order = [
            ("architect", self._architect),
            ("debugger", self._debugger),
            ("engineer", self._engineer),
            ("reviewer", self._reviewer),
        ]

        # Lookup: state_name → agent
        self.agents = {name: agent for name, agent in self.agent_order}

        # Scanner delegates to agents' check_trigger (single source of truth)
        self.scanner = TreeScanner(self.agent_order)
        
        # Cache of completed directories to skip in future scans
        self._completed_dirs: set[Path] = set()
        
        # Track consecutive errors per directory to avoid endless retries
        self._error_counts: dict[Path, int] = {}
        self._max_consecutive_errors = 3
        
        # Track handled escalation IDs to prevent re-processing
        self._handled_escalation_ids: set[str] = set()
        
        # Thread-safe lock for shared state
        self._error_lock = threading.Lock()

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

            # Separate actionable from complete
            actionable = [
                (d, state) for d, state in scan_results
                if state != TreeScanner.COMPLETE
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
                all_complete = all(
                    state == TreeScanner.COMPLETE for _, state in scan_results
                )
                if all_complete:
                    logger.info(f"[pipeline] All directories resolved after {iteration} iterations")
                    return True

                logger.warning(f"[pipeline] Iteration {iteration}: no actionable directories, but not complete")
                time.sleep(self.poll_interval)
                continue

            # Dispatch agents in priority order
            # Scanner already classified using agent_order priority, so group by state
            dispatched = 0
            for state_name, agent in self.agent_order:
                dirs_for_state = [d for d, s in actionable if s == state_name]
                if not dirs_for_state:
                    continue

                # Filter out directories that have failed too many times
                valid_dirs = []
                for directory in dirs_for_state:
                    with self._error_lock:
                        if self._error_counts.get(directory, 0) >= self._max_consecutive_errors:
                            if directory not in self._completed_dirs:
                                logger.warning(f"[pipeline] Skipping {directory} after {self._max_consecutive_errors} consecutive errors")
                                self._completed_dirs.add(directory)
                            continue

                    # Dedup: skip debugger if this escalation ID was already handled
                    if state_name == "debugger":
                        esc_id = self._read_escalation_id(directory)
                        if esc_id and esc_id in self._handled_escalation_ids:
                            logger.warning(f"[pipeline] Escalation {esc_id} in {directory.name} already handled — skipping")
                            continue

                    valid_dirs.append(directory)
                
                if not valid_dirs:
                    continue
                
                dispatched += self._execute_parallel(agent, valid_dirs, iteration)

            if dispatched == 0:
                logger.warning(f"[pipeline] Iteration {iteration}: no agents dispatched")

            self._log_progress(iteration, scan_results)
            time.sleep(self.poll_interval)

        logger.warning(f"[pipeline] Reached max iterations ({self.max_iterations})")
        return False

    def _execute_parallel(self, agent, directories: list[Path], iteration: int) -> int:
        """Execute agent on multiple directories in parallel.
        
        Returns the number of successfully dispatched agents.
        """
        dispatched = 0
        
        # Sequential execution if max_concurrent_agents is 1
        if self.max_concurrent_agents == 1:
            for directory in directories:
                logger.info(
                    f"[pipeline] Iteration {iteration}: "
                    f"dispatching {agent.role} → {directory}"
                )
                if self._execute_agent(agent, directory):
                    dispatched += 1
            return dispatched
        
        # Parallel execution
        with ThreadPoolExecutor(max_workers=self.max_concurrent_agents) as executor:
            # Submit all tasks
            future_to_dir = {}
            for directory in directories:
                logger.info(
                    f"[pipeline] Iteration {iteration}: "
                    f"dispatching {agent.role} → {directory} (parallel)"
                )
                future = executor.submit(self._execute_agent, agent, directory)
                future_to_dir[future] = directory
            
            # Wait for all to complete and collect results
            for future in as_completed(future_to_dir):
                directory = future_to_dir[future]
                try:
                    if future.result():
                        dispatched += 1
                except Exception as e:
                    logger.error(f"[pipeline] Unexpected error in parallel execution for {directory}: {e}")
        
        return dispatched
    
    def _execute_agent(self, agent, directory: Path) -> bool:
        """Execute a single agent on a directory. Returns True if successful.
        
        Thread-safe execution with error tracking and escalation ID recording.
        """
        # Record escalation ID before debugger runs (file gets deleted after)
        esc_id = None
        if agent.role == "debugger":
            esc_id = self._read_escalation_id(directory)

        try:
            agent.execute(directory)
            with self._error_lock:
                self._error_counts.pop(directory, None)  # Reset on success
                if esc_id:
                    self._handled_escalation_ids.add(esc_id)
            return True
        except Exception as e:
            with self._error_lock:
                self._error_counts[directory] = self._error_counts.get(directory, 0) + 1
                error_count = self._error_counts[directory]
            logger.error(
                f"[pipeline] {agent.role} failed on {directory} "
                f"(attempt {error_count}/{self._max_consecutive_errors}): {e}",
            )
            return False

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

    def _log_progress(self, iteration: int, scan_results: list) -> None:
        """Log a compact progress summary."""
        counts = {}
        for _, state in scan_results:
            counts[state] = counts.get(state, 0) + 1

        parts = [f"{state}={count}" for state, count in sorted(counts.items())]
        logger.info(f"[pipeline] Iteration {iteration} progress: {', '.join(parts)}")
