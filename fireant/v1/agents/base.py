import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from ..utils.config import load_config
from ..utils.gemini import GeminiClient
from ..utils.manifest import (
    STANDARD_FILES,
    all_passed,
    get_blocked_deliverables,
    get_parallel_deliverables,
    get_pending_deliverables,
    has_file,
    load_manifest,
    read_file,
    save_manifest,
    write_file,
)

logger = logging.getLogger("fireant")


class BaseAgent(ABC):
    """Base class for all FireAnt agents.

    Provides:
        - GeminiClient with role-specific config
        - Common file I/O helpers (read/write prd, manifest, etc.)
        - Manifest querying shortcuts
        - Abstract methods for trigger detection and action execution
    """

    role: str = "base"

    def __init__(self, temperature_override: Optional[float] = None):
        self.config = load_config()
        self.llm = GeminiClient(role=self.role, temperature_override=temperature_override)
        self.temperature_override = temperature_override

    # ── Trigger & Action (subclasses implement) ──────────────────────

    @abstractmethod
    def check_trigger(self, directory: Path) -> bool:
        """Return True if this agent's activation condition is met in the directory."""
        ...

    @abstractmethod
    def execute(self, directory: Path) -> None:
        """Perform the agent's action on the given directory."""
        ...

    def run(self, directory: Path) -> bool:
        """Check trigger, execute if met. Returns True if action was taken."""
        if self.check_trigger(directory):
            logger.info(f"[{self.role}] Triggered on {directory}")
            self.execute(directory)
            return True
        return False

    # ── File helpers ─────────────────────────────────────────────────

    def read_prd(self, directory: Path) -> Optional[str]:
        return read_file(directory, STANDARD_FILES["prd"])

    def write_prd(self, directory: Path, content: str) -> None:
        write_file(directory, STANDARD_FILES["prd"], content)

    def read_manifest(self, directory: Path) -> Optional[dict]:
        return load_manifest(directory)

    def write_manifest(self, directory: Path, manifest: dict) -> None:
        save_manifest(directory, manifest)

    def read_review(self, directory: Path) -> Optional[str]:
        return read_file(directory, STANDARD_FILES["review"])

    def write_review(self, directory: Path, content: str) -> None:
        write_file(directory, STANDARD_FILES["review"], content)

    def read_escalation(self, directory: Path) -> Optional[str]:
        return read_file(directory, STANDARD_FILES["escalation"])

    def write_escalation(self, directory: Path, content: str) -> None:
        write_file(directory, STANDARD_FILES["escalation"], content)

    def write_change_request(self, directory: Path, content: str) -> None:
        write_file(directory, STANDARD_FILES["change_request"], content)

    def read_change_request(self, directory: Path) -> Optional[str]:
        return read_file(directory, STANDARD_FILES["change_request"])

    def write_vote_result(self, directory: Path, content: str) -> None:
        write_file(directory, STANDARD_FILES["vote_result"], content)

    def write_status_pass(self, directory: Path) -> None:
        write_file(directory, STANDARD_FILES["status_pass"], "")

    def read_execution_errors(self, directory: Path) -> Optional[str]:
        return read_file(directory, STANDARD_FILES["execution_errors"])

    def has_prd(self, directory: Path) -> bool:
        return has_file(directory, STANDARD_FILES["prd"])

    def has_manifest(self, directory: Path) -> bool:
        return has_file(directory, STANDARD_FILES["manifest"])

    def has_escalation(self, directory: Path) -> bool:
        return has_file(directory, STANDARD_FILES["escalation"])

    def has_change_request(self, directory: Path) -> bool:
        return has_file(directory, STANDARD_FILES["change_request"])

    def has_status_pass(self, directory: Path) -> bool:
        return has_file(directory, STANDARD_FILES["status_pass"])

    def has_vote_result(self, directory: Path) -> bool:
        return has_file(directory, STANDARD_FILES["vote_result"])

    # ── Manifest query shortcuts ─────────────────────────────────────

    def get_pending(self, directory: Path) -> list[dict]:
        return get_pending_deliverables(directory)

    def get_blocked(self, directory: Path) -> list[dict]:
        return get_blocked_deliverables(directory)

    def get_parallel(self, directory: Path) -> list[dict]:
        return get_parallel_deliverables(directory)

    def is_all_passed(self, directory: Path) -> bool:
        return all_passed(directory)

    # ── Directory helpers ────────────────────────────────────────────

    def get_subdirs(self, directory: Path) -> list[Path]:
        if not directory.exists():
            return []
        return sorted([d for d in directory.iterdir() if d.is_dir()])

    def get_code_files(self, directory: Path) -> list[Path]:
        if not directory.exists():
            return []
        code_extensions = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs"}
        return sorted([
            f for f in directory.iterdir()
            if f.is_file() and f.suffix in code_extensions
        ])

    def get_child_escalations(self, directory: Path) -> list[Path]:
        """Return child directories that contain an escalation.md."""
        escalated = []
        for subdir in self.get_subdirs(directory):
            if has_file(subdir, STANDARD_FILES["escalation"]):
                escalated.append(subdir)
        return escalated
