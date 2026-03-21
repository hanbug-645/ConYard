import logging
import time
from pathlib import Path
from typing import Optional

from .scanner import TreeScanner
from ..utils.manifest import load_manifest, rollup_tree
from ..agents.architect import ArchitectAgent
from ..agents.strategist import StrategistAgent
from ..agents.pm import PMAgent
from ..agents.engineer import EngineerAgent
from ..agents.reviewer import ReviewerAgent
from ..agents.voter import VoterAgent

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
        TreeScanner.NEEDS_VOTER,
    ]

    def __init__(self, max_iterations: int = 50, poll_interval: float = 1.0):
        self.max_iterations = max_iterations
        self.poll_interval = poll_interval
        self.scanner = TreeScanner()

        # Default agent instances (no temperature override)
        self._default_agents = {
            TreeScanner.NEEDS_ARCHITECT: ArchitectAgent(),
            TreeScanner.NEEDS_STRATEGIST_RISK: StrategistAgent(),
            TreeScanner.NEEDS_STRATEGIST_ESCALATION: StrategistAgent(),
            TreeScanner.NEEDS_PM: PMAgent(),
            TreeScanner.NEEDS_ENGINEER: EngineerAgent(),
            TreeScanner.NEEDS_REVIEWER: ReviewerAgent(),
            TreeScanner.NEEDS_VOTER: VoterAgent(),
        }

        # Agent class lookup for creating temperature-overridden instances
        self._agent_classes = {
            TreeScanner.NEEDS_ARCHITECT: ArchitectAgent,
            TreeScanner.NEEDS_STRATEGIST_RISK: StrategistAgent,
            TreeScanner.NEEDS_STRATEGIST_ESCALATION: StrategistAgent,
            TreeScanner.NEEDS_PM: PMAgent,
            TreeScanner.NEEDS_ENGINEER: EngineerAgent,
            TreeScanner.NEEDS_REVIEWER: ReviewerAgent,
            TreeScanner.NEEDS_VOTER: VoterAgent,
        }

        # Cache for temperature-specific agent instances: (state, temp) → agent
        self._temp_agent_cache: dict[tuple[str, float], object] = {}

    def run(self, project_root: Path) -> bool:
        """Run the pipeline until the project is complete or iterations exhausted.

        Returns True if the project reached completion.
        """
        logger.info(f"[pipeline] Starting on {project_root} (max {self.max_iterations} iterations)")

        for iteration in range(1, self.max_iterations + 1):
            # Roll up child statuses to parent manifests (bottom-up)
            rollup_tree(project_root)

            scan_results = self.scanner.scan(project_root)

            # Separate actionable from terminal states
            actionable = [
                (d, state) for d, state in scan_results
                if state not in (TreeScanner.COMPLETE, TreeScanner.BLOCKED)
            ]

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
                if not dirs_for_state or priority_state not in self._default_agents:
                    continue

                for directory in dirs_for_state:
                    dispatch_agent = self._get_agent(priority_state, directory)
                    logger.info(
                        f"[pipeline] Iteration {iteration}: "
                        f"dispatching {dispatch_agent.role} → {directory}"
                    )
                    try:
                        dispatch_agent.execute(directory)
                        dispatched += 1
                    except Exception as e:
                        logger.error(
                            f"[pipeline] {dispatch_agent.role} failed on {directory}: {e}",
                            exc_info=True,
                        )

            if dispatched == 0:
                logger.warning(f"[pipeline] Iteration {iteration}: no agents dispatched")

            self._log_progress(iteration, scan_results)
            time.sleep(self.poll_interval)

        logger.warning(f"[pipeline] Reached max iterations ({self.max_iterations})")
        return False

    def _get_agent(self, state: str, directory: Path):
        """Return an agent for the given state and directory.

        If the directory's manifest.json contains a 'temperature' field
        (set by the Strategist for parallel candidate dirs), return a
        temperature-overridden agent instance. Otherwise return the default.
        """
        manifest = load_manifest(directory)
        if manifest and "temperature" in manifest:
            temp = manifest["temperature"]
            cache_key = (state, temp)
            if cache_key not in self._temp_agent_cache:
                agent_class = self._agent_classes.get(state)
                if agent_class:
                    self._temp_agent_cache[cache_key] = agent_class(temperature_override=temp)
                    logger.info(f"[pipeline] Created {agent_class.__name__} with temperature={temp}")
            if cache_key in self._temp_agent_cache:
                return self._temp_agent_cache[cache_key]

        return self._default_agents[state]

    def _log_progress(self, iteration: int, scan_results: list) -> None:
        """Log a compact progress summary."""
        counts = {}
        for _, state in scan_results:
            counts[state] = counts.get(state, 0) + 1

        parts = [f"{state}={count}" for state, count in sorted(counts.items())]
        logger.info(f"[pipeline] Iteration {iteration} progress: {', '.join(parts)}")
