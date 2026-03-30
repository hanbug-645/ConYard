import logging
from pathlib import Path
from typing import TYPE_CHECKING

from ..utils.manifest import STANDARD_FILES

if TYPE_CHECKING:
    from ..agents.base import BaseAgent

logger = logging.getLogger("fireant")

# Directories to skip during tree scanning (not project components)
_SKIP_DIRS = {"lib", "test", "node_modules", "__pycache__"}


class TreeScanner:
    """Walks the project directory tree and classifies each directory's state.

    Delegates classification to agents' check_trigger methods — agents are
    the single source of truth for their own activation conditions.
    Scanner only handles terminal states (COMPLETE) and priority ordering.
    """

    COMPLETE = "complete"

    def __init__(self, agent_order: list[tuple[str, 'BaseAgent']]):
        """Initialize with ordered list of (state_name, agent) tuples.
        
        Agents are checked in this order — first agent whose check_trigger
        returns True determines the directory's state.
        """
        self.agent_order = agent_order

    def scan(self, root: Path) -> list[tuple[Path, str]]:
        """Recursively scan the tree and return (directory, state) pairs."""
        results = []
        self._scan_dir(root, results)
        return results

    def _scan_dir(self, directory: Path, results: list) -> None:
        if not directory.is_dir():
            return

        state = self._classify(directory)
        results.append((directory, state))

        # Recurse into sub-directories (skip utility and hidden dirs)
        for child in sorted(directory.iterdir()):
            if child.is_dir() and not child.name.startswith((".", "_")):
                if child.name not in _SKIP_DIRS:
                    self._scan_dir(child, results)

    def _classify(self, directory: Path) -> str:
        # Terminal: already marked complete
        if (directory / STANDARD_FILES["status_pass"]).exists():
            return self.COMPLETE

        # Ask each agent in priority order — first match wins
        for state_name, agent in self.agent_order:
            if agent.check_trigger(directory):
                return state_name

        return self.COMPLETE
