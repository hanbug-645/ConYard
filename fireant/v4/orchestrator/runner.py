"""Orchestration logic — spawns worker threads and runs the PM loop."""

import logging
import threading
from pathlib import Path

from agents.manager import ManagerAgent
from agents.pm import PMAgent
from agents.engineer import EngineerAgent
from agents.qa_engineer import QAEngineerAgent
from utils.operation_log import OperationLogger
from utils.signals import SignalStore

logger = logging.getLogger("fireant")


def run_project(
    task: str,
    project_dir: Path,
    signals: SignalStore,
    op_logger: OperationLogger,
    config: dict,
) -> bool:
    """Run the full agent pipeline for a project.

    1. Manager creates detailed PRD
    2. Spawn Engineer + QA worker threads
    3. PM planning loop on calling thread
    4. Post-completion (README)

    Returns True if the project converged.
    """
    # ── Step 1: Manager creates detailed PRD ─────────────────────────
    manager = ManagerAgent(signals=signals)
    manager.set_operation_logger(op_logger)
    manager.handle_do(task, project_dir)

    # ── Step 2: Spawn worker threads ─────────────────────────────────
    stop_event = threading.Event()
    workers_cfg = config.get("workers", {})
    num_engineers = workers_cfg.get("engineers", 3)
    num_qa = workers_cfg.get("qa_engineers", 1)

    threads: list[threading.Thread] = []

    for i in range(num_engineers):
        eng = EngineerAgent(
            project_dir=project_dir,
            agent_id=f"engineer-{i}",
            signals=signals,
        )
        eng.set_operation_logger(op_logger)
        t = threading.Thread(
            target=eng.run_loop,
            kwargs={"poll_interval": 1.0, "stop_event": stop_event},
            name=f"engineer-{i}",
            daemon=True,
        )
        threads.append(t)

    for i in range(num_qa):
        qa = QAEngineerAgent(
            project_dir=project_dir,
            agent_id=f"qa-{i}",
            signals=signals,
        )
        qa.set_operation_logger(op_logger)
        t = threading.Thread(
            target=qa.run_loop,
            kwargs={"poll_interval": 1.0, "stop_event": stop_event},
            name=f"qa-{i}",
            daemon=True,
        )
        threads.append(t)

    for t in threads:
        t.start()
    logger.info(f"Started {num_engineers} engineer(s) and {num_qa} QA worker(s)")

    # ── Step 3: PM planning loop (runs on calling thread) ────────────
    pm = PMAgent(project_dir=project_dir, signals=signals)
    pm.set_operation_logger(op_logger)

    try:
        converged = pm.run_loop(poll_interval=2.0, max_iterations=50)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        converged = False
    finally:
        stop_event.set()
        for t in threads:
            t.join(timeout=5.0)

    # ── Step 4: Post-completion ──────────────────────────────────────
    if converged:
        manager.generate_readme(project_dir)
        logger.info(f"Project complete! Results in: {project_dir}")
    else:
        logger.warning(f"Project did not fully converge. Partial results in: {project_dir}")

    summary = op_logger.get_summary()
    if summary:
        logger.info(f"Operation summary: {summary}")

    return converged
