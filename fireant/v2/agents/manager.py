import logging
from pathlib import Path

from .base import BaseAgent

logger = logging.getLogger("fireant")


class ManagerAgent(BaseAgent):
    """User-facing agent that creates the high-level PRD from user input.
    
    ═══════════════════════════════════════════════════════════════
    DUTY: PRD CREATION (Step 1)
    ═══════════════════════════════════════════════════════════════
    Manager is the entry point of the agent flow. It takes user
    input and produces a detailed PRD in the root folder.
    
    Runs ONCE before the pipeline loop, not as a pipeline agent.
    
    Responsibilities:
    - Take user input (task description)
    - Create high-level PRD in root folder
    - Handle user commands (DO, ASK)
    
    What Manager DOES NOT do:
    - Architecture decomposition (→ Architect agent)
    - Code generation (→ Engineer agent)
    - Code review (→ Reviewer agent)
    ═══════════════════════════════════════════════════════════════
    """

    role = "manager"

    def check_trigger(self, directory: Path) -> bool:
        # Manager is called explicitly before pipeline, not via scan
        return False

    def _execute_impl(self, directory: Path) -> None:
        """Expand a stub PRD into a detailed PRD."""
        prd_content = self.read_prd(directory)
        if not prd_content:
            logger.warning(f"[manager] No prd.md in {directory}")
            return

        detailed_prd = self._expand_prd(prd_content)
        self.write_prd(directory, detailed_prd)
        self.log_operation("create_prd", directory)
        logger.info(f"[manager] Created detailed PRD in {directory}")

    # ── Interaction Modes ────────────────────────────────────────────

    def handle_do_mode(self, task: str, directory: Path) -> None:
        """Handle DO mode: create PRD and let pipeline take over.
        
        Args:
            task: User's task description
            directory: Project root directory
        """
        prd_content = self._generate_prd_from_task(task)
        self.write_prd(directory, prd_content)
        logger.info(f"[manager] DO mode: Created PRD for task: {task}")

    def handle_ask_mode(self, question: str, directory: Path) -> str:
        """Handle ASK mode: answer user questions.
        
        Args:
            question: User's question
            directory: Project root directory
            
        Returns:
            Answer from LLM
        """
        prd_content = self.read_prd(directory) or ""
        context = f"PRD:\n{prd_content}"

        prompt = (
            f"User question: {question}\n\n"
            "Provide a clear, concise answer based on the project context."
        )

        answer = self.llm.generate(prompt, context=context)
        logger.info(f"[manager] ASK mode: Answered question: {question[:50]}...")
        return answer

    # ── LLM calls ────────────────────────────────────────────────────

    def _expand_prd(self, stub_prd: str) -> str:
        """Expand a stub PRD into a detailed PRD."""
        prompt = (
            "Expand the following stub PRD into a detailed Product Requirements Document.\n\n"
            "Include:\n"
            "- Clear objective\n"
            "- Functional requirements\n"
            "- Technical stack\n"
            "- Deliverables overview\n\n"
            f"Stub PRD:\n{stub_prd}"
        )
        return self.llm.generate(prompt)

    def _generate_prd_from_task(self, task: str) -> str:
        """Generate a detailed PRD from user task description."""
        prompt = (
            f"User task: {task}\n\n"
            "Generate a concise PRD (Product Requirements Document) for this task.\n\n"
            "Format:\n"
            "# [Project Name]\n\n"
            "## Objective\n"
            "[What to build]\n\n"
            "## Requirements\n"
            "- [Requirement 1]\n"
            "- [Requirement 2]\n"
            "...\n\n"
            "## Technical Stack\n"
            "[Languages, frameworks, etc.]\n\n"
            "## Deliverables\n"
            "[What files/components to create]\n"
        )
        return self.llm.generate(prompt)
