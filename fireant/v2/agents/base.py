import json as _json
import logging
import uuid as _uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from ..utils.config import load_config
from ..utils.gemini import GeminiClient

if TYPE_CHECKING:
    from ..utils.operation_log import OperationLogger
from ..utils.manifest import (
    MAX_ESCALATION_DEPTH,
    STANDARD_FILES,
    all_passed,
    get_blocked_deliverables,
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
        self.operation_logger: Optional['OperationLogger'] = None

    def set_operation_logger(self, logger: 'OperationLogger') -> None:
        """Set the operation logger for this agent."""
        self.operation_logger = logger

    def log_operation(self, action: str, directory: Path, details: Optional[dict] = None) -> None:
        """Log an operation if operation_logger is set."""
        if self.operation_logger:
            self.operation_logger.log(self.role, action, str(directory), details)

    # ── Trigger & Action (subclasses implement) ──────────────────────

    @abstractmethod
    def check_trigger(self, directory: Path) -> bool:
        """Return True if this agent's activation condition is met in the directory."""
        ...

    def execute(self, directory: Path) -> None:
        """Execute this agent's action with automatic start/end logging."""
        self.log_operation("start", directory)
        try:
            self._execute_impl(directory)
            self.log_operation("end", directory, {"status": "success"})
        except Exception as e:
            self.log_operation("end", directory, {"status": "error", "error": str(e)})
            raise

    @abstractmethod
    def _execute_impl(self, directory: Path) -> None:
        """Execute this agent's action in the directory. Subclasses implement this."""
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
        """Read escalation content string (backward compat)."""
        data = self.read_escalation_full(directory)
        if data is None:
            return None
        return data.get("content", "")

    def read_escalation_full(self, directory: Path) -> Optional[dict]:
        """Read full escalation data: {id, origin, chain, content}."""
        path = directory / STANDARD_FILES["escalation"]
        if not path.exists():
            return None
        try:
            return _json.loads(path.read_text())
        except (_json.JSONDecodeError, ValueError):
            # Backward compat: plain-text escalation from old format
            raw = path.read_text()
            return {"id": "legacy", "origin": "", "chain": [], "content": raw}

    def write_escalation(
        self, directory: Path, content: str, chain: list[str] | None = None,
    ) -> str:
        """Write a JSON escalation with unique ID and chain tracking.

        Args:
            directory: target folder
            content: human-readable escalation text
            chain: list of directory paths already visited by this
                   escalation lineage (for dead-loop prevention)

        Returns:
            The new escalation ID.
        """
        esc_id = f"esc-{_uuid.uuid4().hex[:8]}"
        if chain is None:
            chain = []
        chain_with_self = chain + [str(directory)]
        data = {
            "id": esc_id,
            "origin": directory.name,
            "chain": chain_with_self,
            "content": content,
        }
        path = directory / STANDARD_FILES["escalation"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json.dumps(data, indent=2))
        logger.debug(f"[escalation] Created {esc_id} in {directory.name} (chain len={len(chain_with_self)})")
        return esc_id

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

    def is_all_passed(self, directory: Path) -> bool:
        return all_passed(directory)

    # ── Folder context (shared by all agents for LLM calls) ────────

    def build_folder_context(self, directory: Path) -> str:
        """Build a concise context string from current + parent manifest.

        Gives the LLM awareness of:
        - Current folder deliverables (names, types, contracts, statuses)
        - Parent folder deliverables (siblings and how this folder fits in)

        Returns an empty string if no manifest exists in either location.
        """
        parts: list[str] = []

        # Current folder
        manifest = self.read_manifest(directory)
        if manifest:
            parts.append(f"=== Current Folder: {directory.name} ===")
            parts.append(self._format_manifest_concise(manifest))

        # Parent folder (if managed and not the same as current)
        parent = directory.parent
        if parent != directory and (parent / STANDARD_FILES["manifest"]).exists():
            parent_manifest = load_manifest(parent)
            if parent_manifest:
                parts.append(f"=== Parent Folder: {parent.name} ===")
                parts.append(self._format_manifest_concise(parent_manifest))

        return "\n".join(parts)

    @staticmethod
    def _format_manifest_concise(manifest: dict) -> str:
        """Format manifest deliverables as a compact string."""
        lines = []
        for d in manifest.get("deliverables", []):
            name = d.get("name", "?")
            entry = f"- {name} ({d.get('type', 'file')}, {d.get('status', '?')})"
            desc = d.get("description", "")
            if desc:
                entry += f": {desc}"
            inputs = d.get("inputs", "")
            if inputs:
                entry += f" | in: {inputs}"
            outputs = d.get("outputs", "")
            if outputs:
                entry += f" | out: {outputs}"
            deps = d.get("dependencies", [])
            if isinstance(deps, str):
                deps = [deps] if deps else []
            if deps:
                entry += f" | deps: {', '.join(deps)}"
            lines.append(entry)
        return "\n".join(lines)

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
