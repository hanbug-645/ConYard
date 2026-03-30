"""FireAnt Entry Point — Signal-Based Agent Framework.

Usage:
    python3 main.py --task "Build a snake game" --name "snake_game"

The project will be created under:
    projects/<name>_<timestamp>/
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from orchestrator.runner import run_project
from utils.config import load_config
from utils.operation_log import OperationLogger
from utils.signals import SignalStore


def setup_logging(log_level: str = "INFO", log_file: str | None = None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


def bootstrap_project(project_dir: Path, title: str = "project") -> None:
    """Bootstrap a project directory with Kaplay runtime files.

    Sets up package.json (ES modules), kaplay.js symlink, and index.html.
    Safe to call on an existing directory — skips files that already exist.
    """
    project_dir.mkdir(parents=True, exist_ok=True)

    # Enable ES module imports in Node.js (for QA test execution)
    pkg_json = project_dir / "package.json"
    if not pkg_json.exists():
        pkg_json.write_text('{"type": "module"}\n')

    # Symlink shared Kaplay lib into project root so it's self-contained
    kaplay_src = Path(__file__).resolve().parent.parent / "shared" / "kaplay" / "kaplay.js"
    kaplay_link = project_dir / "kaplay.js"
    if kaplay_src.exists() and not kaplay_link.exists():
        kaplay_link.symlink_to(kaplay_src)

    # Bootstrap index.html with Kaplay from project root
    index_path = project_dir / "index.html"
    if not index_path.exists():
        index_path.write_text(
            '<!DOCTYPE html>\n'
            '<html lang="en">\n'
            '<head>\n'
            '  <meta charset="UTF-8">\n'
            '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            f'  <title>{title}</title>\n'
            '</head>\n'
            '<body>\n'
            '  <script src="kaplay.js"></script>\n'
            '  <script type="module" src="main.js"></script>\n'
            '</body>\n'
            '</html>\n'
        )


def create_project(task: str, name: str, base_dir: Path) -> Path:
    """Create a new project directory with a seeded prd.md and Kaplay runtime."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    project_name = f"{name}_{timestamp}"
    project_dir = base_dir / project_name

    bootstrap_project(project_dir, title=name)

    prd_path = project_dir / "prd.md"
    prd_path.write_text(
        f"# {name}\n\n"
        f"## Task\n\n{task}\n"
    )

    logging.getLogger("fireant").info(f"Created project: {project_dir}")
    return project_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FireAnt — Signal-Based Agent Framework",
    )
    parser.add_argument(
        "--task", required=True,
        help="The task description / high-level requirement for the project.",
    )
    parser.add_argument(
        "--name", required=True,
        help="Short project name (used in the directory name).",
    )
    parser.add_argument(
        "--projects-dir", default=None,
        help="Base directory for projects (default: projects/).",
    )

    args = parser.parse_args()
    config = load_config()

    # ── Logging ──────────────────────────────────────────────────────
    log_cfg = config.get("logging", {})
    setup_logging(
        log_level=log_cfg.get("level", "INFO"),
        log_file=log_cfg.get("file"),
    )
    logger = logging.getLogger("fireant")

    # ── Redis ────────────────────────────────────────────────────────
    redis_cfg = config.get("redis", {})
    signals = SignalStore(
        redis_url=redis_cfg.get("url", "redis://localhost:6379"),
        prefix=redis_cfg.get("prefix", "fireant:"),
    )
    signals.flush_project()

    # ── Project directory ────────────────────────────────────────────
    base_dir = Path(args.projects_dir) if args.projects_dir else Path(__file__).parent / "projects"
    project_dir = create_project(args.task, args.name, base_dir)
    op_logger = OperationLogger(project_dir)

    logger.info(f"Task: {args.task}")
    logger.info(f"Project directory: {project_dir}")

    # ── Run ──────────────────────────────────────────────────────────
    run_project(
        task=args.task,
        project_dir=project_dir,
        signals=signals,
        op_logger=op_logger,
        config=config,
    )


if __name__ == "__main__":
    main()
