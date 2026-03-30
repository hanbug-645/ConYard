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
    get_engineer_actionable,
    has_file,
    load_manifest,
    read_file,
    save_manifest,
    write_file,
)

logger = logging.getLogger("fireant")

# Path to shared Kaplay API reference
_KAPLAY_API_REF = Path(__file__).resolve().parent.parent.parent.parent / "shared" / "kaplay" / "kaplay.md"


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

    def has_prd(self, directory: Path) -> bool:
        return has_file(directory, STANDARD_FILES["prd"])

    def has_manifest(self, directory: Path) -> bool:
        return has_file(directory, STANDARD_FILES["manifest"])

    def has_escalation(self, directory: Path) -> bool:
        return has_file(directory, STANDARD_FILES["escalation"])

    # ── Manifest query shortcuts ─────────────────────────────────────

    def get_pending(self, directory: Path) -> list[dict]:
        return get_engineer_actionable(directory)

    def get_blocked(self, directory: Path) -> list[dict]:
        return get_blocked_deliverables(directory)

    def is_all_passed(self, directory: Path) -> bool:
        return all_passed(directory)

    # ── Folder context (shared by all agents for LLM calls) ────────

    def get_kaplay_api_reference(self) -> str:
        """Load the Kaplay API reference from shared/kaplay/kaplay.md."""
        if _KAPLAY_API_REF.exists():
            return _KAPLAY_API_REF.read_text()
        return ""

    def get_current_dir_context(self, directory: Path) -> str:
        """Get context for the current directory only."""
        manifest = self.read_manifest(directory)
        if manifest:
            parts = [f"=== Current Folder: {directory.name} ==="]
            parts.append(self._format_manifest_concise(manifest))
            return "\n".join(parts)
        return ""

    def get_parent_dir_context(self, directory: Path) -> str:
        """Get context for the parent directory only."""
        parent = self.get_parent_dir(directory)
        if parent and (parent / STANDARD_FILES["manifest"]).exists():
            parent_manifest = load_manifest(parent)
            if parent_manifest:
                parts = [f"=== Parent Folder: {parent.name} ==="]
                parts.append(self._format_manifest_concise(parent_manifest))
                return "\n".join(parts)
        return ""

    def get_subdir_context(self, directory: Path) -> str:
        """Get context for all subdirectories that have manifests."""
        parts = []
        for subdir in self.get_subdirs(directory):
            if (subdir / STANDARD_FILES["manifest"]).exists():
                subdir_manifest = load_manifest(subdir)
                if subdir_manifest:
                    parts.append(f"=== Subfolder: {subdir.name} ===")
                    parts.append(self._format_manifest_concise(subdir_manifest))
        return "\n".join(parts)

    def get_deep_child_exports(self, directory: Path, prefix: str = "") -> str:
        """Recursively collect exports from all descendant directories.

        Returns a formatted string showing the full interface tree:
          subdir_name/filename: function signatures
        This gives the engineer complete visibility into what child
        directories expose, preventing interface hallucination.
        """
        lines = []
        for subdir in self.get_subdirs(directory):
            if subdir.name.startswith((".", "_")) or subdir.name in {"lib", "test", "node_modules", "__pycache__"}:
                continue
            subdir_manifest = load_manifest(subdir)
            if not subdir_manifest:
                continue

            rel = f"{prefix}{subdir.name}" if prefix else subdir.name
            lines.append(f"=== {rel}/ ===")

            for d in subdir_manifest.get("deliverables", []):
                name = d.get("name", "?")
                exports = d.get("exports", {})
                d_type = d.get("type", "file")

                if d_type == "file" and exports:
                    lines.append(f"  {rel}/{name}:")
                    for sig, desc in exports.items():
                        lines.append(f"    {sig} — {desc}")

                    # Also include actual code snippet if file exists
                    code_path = subdir / name
                    if code_path.exists():
                        code = code_path.read_text()
                        # Show first 50 lines as interface reference
                        preview = "\n".join(code.splitlines()[:50])
                        lines.append(f"    [actual code preview]:")
                        lines.append(f"    ```")
                        lines.append(f"    {preview}")
                        lines.append(f"    ```")

            # Recurse deeper
            deep = self.get_deep_child_exports(subdir, prefix=f"{rel}/")
            if deep:
                lines.append(deep)

        return "\n".join(lines)

    def build_folder_context(self, directory: Path) -> str:
        """Build a concise context string from current + parent manifest.

        Gives the LLM awareness of:
        - Current folder deliverables (names, types, contracts, statuses)
        - Parent folder deliverables (siblings and how this folder fits in)

        Returns an empty string if no manifest exists in either location.
        """
        parts = []

        # Current folder context
        current_context = self.get_current_dir_context(directory)
        if current_context:
            parts.append(current_context)

        # Parent folder context
        parent_context = self.get_parent_dir_context(directory)
        if parent_context:
            parts.append(parent_context)

        return "\n".join(parts)

    @staticmethod
    def _format_manifest_concise(manifest: dict) -> str:
        """Format manifest deliverables as a compact string."""
        lines = []
        for d in manifest.get("deliverables", []):
            name = d.get("name", "?")
            # Status: use per-field statuses for files, single status for dirs
            if d.get("type") == "file":
                status = f"code:{d.get('coding_status','?')} qa:{d.get('qa_status','?')}"
            else:
                status = d.get("status", "?")
            entry = f"- {name} ({d.get('type', 'file')}, {status})"
            desc = d.get("description", "")
            if desc:
                entry += f": {desc}"
            exports = d.get("exports", {})
            if exports:
                lines.append(entry)
                for sig, sig_desc in exports.items():
                    lines.append(f"    export: {sig} — {sig_desc}")
            else:
                lines.append(entry)
        return "\n".join(lines)

    # ── Directory helpers ────────────────────────────────────────────

    def get_subdirs(self, directory: Path) -> list[Path]:
        if not directory.exists():
            return []
        return sorted([d for d in directory.iterdir() if d.is_dir()])

    def get_parent_dir(self, directory: Path) -> Optional[Path]:
        """Get the parent directory if it exists and is different from current."""
        if not directory.exists():
            return None
        parent = directory.parent
        return parent if parent != directory else None

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
