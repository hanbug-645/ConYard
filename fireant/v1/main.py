"""FireAnt Entry Point.

Usage:
    python3 -m ConYard.fireant.v1.main --task "Build a snake game" --name "snake_game"
    python3 -m ConYard.fireant.v1.main --task "Build a REST API for todo app" --name "todo_api" --max-iterations 100

The project will be created under:
    ConYard/fireant/v1/projects/<name>_<timestamp>/
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from .orchestrator.pipeline import Pipeline
from .utils.config import load_config
from .utils.manifest import STANDARD_FILES


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


def create_project(task: str, name: str, base_dir: Path) -> Path:
    """Create a new project directory with a seeded prd.md."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    project_name = f"{name}_{timestamp}"
    project_dir = base_dir / project_name
    project_dir.mkdir(parents=True, exist_ok=True)

    prd_path = project_dir / STANDARD_FILES["prd"]
    prd_path.write_text(
        f"# {name}\n\n"
        f"## Task\n\n{task}\n"
    )

    logging.getLogger("fireant").info(f"Created project: {project_dir}")
    return project_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FireAnt — Hierarchical Stigmergic Agent Framework",
    )
    parser.add_argument(
        "--task",
        required=True,
        help="The task description / high-level requirement for the project.",
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Short project name (used in the directory name).",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=50,
        help="Maximum pipeline iterations (default: 50).",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config.yaml (default: auto-detect).",
    )
    parser.add_argument(
        "--projects-dir",
        default=None,
        help="Base directory for projects (default: v1/projects/).",
    )

    args = parser.parse_args()

    config = load_config(args.config)

    log_cfg = config.get("logging", {})
    setup_logging(
        log_level=log_cfg.get("level", "INFO"),
        log_file=log_cfg.get("file"),
    )

    logger = logging.getLogger("fireant")

    if args.projects_dir:
        base_dir = Path(args.projects_dir)
    else:
        base_dir = Path(__file__).parent / "projects"

    project_dir = create_project(args.task, args.name, base_dir)

    logger.info(f"Task: {args.task}")
    logger.info(f"Project directory: {project_dir}")
    logger.info(f"Max iterations: {args.max_iterations}")

    pipeline = Pipeline(max_iterations=args.max_iterations)
    success = pipeline.run(project_dir)

    if success:
        logger.info("Project completed successfully!")
    else:
        logger.warning("Project did not fully complete within the iteration limit.")

    logger.info(f"Results are in: {project_dir}")


if __name__ == "__main__":
    main()
