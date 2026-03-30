import logging
from abc import ABC
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from utils.config import load_config
from utils.gemini import GeminiClient

if TYPE_CHECKING:
    from utils.operation_log import OperationLogger
    from utils.signals import SignalStore

logger = logging.getLogger("fireant")

# Path to shared Kaplay API reference
_KAPLAY_API_REF = Path(__file__).resolve().parent.parent.parent / "shared" / "kaplay" / "kaplay.md"

PRD_FILENAME = "prd.md"


class BaseAgent(ABC):
    """Base class for all FireAnt agents.

    Provides:
        - GeminiClient with role-specific config
        - Simple file I/O helpers
        - Kaplay API reference loader
        - Operation logging
    """

    role: str = "base"

    def __init__(
        self,
        signals: Optional['SignalStore'] = None,
        temperature_override: Optional[float] = None,
    ):
        self.config = load_config()
        self.llm = GeminiClient(role=self.role, temperature_override=temperature_override)
        self.signals = signals
        self.operation_logger: Optional['OperationLogger'] = None

    def set_operation_logger(self, op_logger: 'OperationLogger') -> None:
        self.operation_logger = op_logger

    def log_operation(self, action: str, directory: Path, details: Optional[dict] = None) -> None:
        if self.operation_logger:
            self.operation_logger.log(self.role, action, str(directory), details)

    # ── File helpers ─────────────────────────────────────────────────

    @staticmethod
    def read_prd(project_dir: Path) -> Optional[str]:
        prd_path = project_dir / PRD_FILENAME
        if prd_path.exists():
            return prd_path.read_text()
        return None

    @staticmethod
    def write_prd(project_dir: Path, content: str) -> None:
        prd_path = project_dir / PRD_FILENAME
        prd_path.parent.mkdir(parents=True, exist_ok=True)
        prd_path.write_text(content)

    @staticmethod
    def write_file(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    @staticmethod
    def read_file_content(path: Path) -> Optional[str]:
        if path.exists():
            return path.read_text()
        return None

    # ── Context helpers ──────────────────────────────────────────────

    def get_kaplay_api_reference(self) -> str:
        """Load the Kaplay API reference from shared/kaplay/kaplay.md."""
        if _KAPLAY_API_REF.exists():
            return _KAPLAY_API_REF.read_text()
        return ""

    @staticmethod
    def get_code_files(directory: Path) -> list[Path]:
        if not directory.exists():
            return []
        code_extensions = {".py", ".js", ".ts", ".jsx", ".tsx"}
        return sorted([
            f for f in directory.rglob("*")
            if f.is_file() and f.suffix in code_extensions
            and not f.name.startswith("_")
            and "test" not in f.parts
            and "node_modules" not in f.parts
        ])
