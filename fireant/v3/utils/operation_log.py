import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("fireant")


class OperationLogger:
    """Tracks key operations with timestamps in a project-level log file."""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()
        self.log_file = self.project_root / "operations.jsonl"
        self.log_file.touch(exist_ok=True)

    def log(
        self,
        agent: str,
        action: str,
        directory: str,
        details: Optional[dict] = None,
    ) -> None:
        """Log an operation to the project's operations.jsonl file.

        Args:
            agent: Agent role (e.g., "architect", "engineer")
            action: Action taken (e.g., "start", "end", "decomposed")
            directory: Directory path where action occurred (will be converted to relative)
            details: Optional dict with additional context
        """
        # Convert to relative path
        try:
            dir_path = Path(directory).resolve()
            relative_dir = dir_path.relative_to(self.project_root)
            dir_str = str(relative_dir) if str(relative_dir) != "." else "<root>"
        except (ValueError, Exception):
            # If path is not relative to project_root, use as-is
            dir_str = str(directory)

        # Timestamp with seconds precision only
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        entry = {
            "timestamp": timestamp,
            "directory": dir_str,
            "agent": agent,
            "action": action,
        }
        if details:
            entry["details"] = details

        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.warning(f"[operation_log] Failed to write log entry: {e}")

    def get_summary(self) -> dict:
        """Return a summary of operations by agent and action type."""
        summary = {}
        try:
            with open(self.log_file, "r") as f:
                for line in f:
                    if not line.strip():
                        continue
                    entry = json.loads(line)
                    agent = entry.get("agent", "unknown")
                    action = entry.get("action", "unknown")
                    key = f"{agent}.{action}"
                    summary[key] = summary.get(key, 0) + 1
        except Exception as e:
            logger.warning(f"[operation_log] Failed to read log: {e}")

        return summary
