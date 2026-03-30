import logging
from pathlib import Path

from .base import BaseAgent
from ..utils.config import get_llm_config

# Template directory lives alongside the agents package
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_DEFAULT_TEMPLATE = "kaplay_web_game.txt"

logger = logging.getLogger("fireant")


class ManagerAgent(BaseAgent):
    """User-facing agent that creates the initial PRD.
    
    ═══════════════════════════════════════════════════════════════
    DUTY: USER INTERFACE & PRD CREATION (Step 0)
    ═══════════════════════════════════════════════════════════════
    Manager is the user-facing entry point that creates the initial PRD.
    
    On DO command it:
      1. Loads the project template (hard requirements from .txt)
      2. Combines template + user task description
      3. Uses LLM to brainstorm and expand into a detailed PRD
      4. Writes _prd.md directly
    
    The Architect agent then reads _prd.md and creates the manifest.
    
    What Manager DOES NOT do:
    - Write code (→ Engineer agent)
    - Create manifest (→ Architect agent)
    - Architecture decomposition (→ Architect agent)
    ═══════════════════════════════════════════════════════════════
    """

    role = "manager"

    def check_trigger(self, directory: Path) -> bool:
        # Manager is called explicitly before pipeline, not via scan
        return False

    def _execute_impl(self, directory: Path) -> None:
        # Manager is not a pipeline agent; triggered explicitly via server
        pass

    # ── Interaction Modes ────────────────────────────────────────────

    def handle_do_mode(self, task: str, directory: Path, template: str = _DEFAULT_TEMPLATE) -> None:
        """Handle DO mode: combine template + user input → LLM → _prd.md.
        """
        template_path = _TEMPLATES_DIR / template
        if template_path.exists():
            template_text = template_path.read_text()
        else:
            template_text = ""
            logger.warning(f"[manager] Template not found: {template_path}")

        # Generate PRD using LLM
        prd_content = self._generate_prd(task, template_text)
        
        self.write_prd(directory, prd_content)
        self.log_operation("user_do", directory, {
            "task": task[:200],
            "template": template,
        })
        logger.info(f"[manager] DO mode: Created PRD (template={template})")

    def _generate_prd(self, task: str, template_text: str) -> str:
        """Generate a detailed PRD from user task and template using LLM.

        The PRD has two parts:
        - Part 1 (LLM-generated): Framework-agnostic user needs
        - Part 2 (verbatim template): Framework-specific hard requirements
        """
        prompt = (
            "You are a Product Manager. Expand the user's request into a "
            "Product Requirements Document (PRD) focused on USER NEEDS.\n\n"
            "YOUR FOCUS — the WHAT, not the HOW:\n"
            "- What does the user experience? Describe gameplay, interactions, visual feel.\n"
            "- What are the user flows? (e.g. menu → game → game over → restart)\n"
            "- What features and mechanics does the user expect?\n"
            "- What does the user see? Describe visual elements, feedback, animations.\n"
            "- What are the win/lose conditions, scoring rules, difficulty progression?\n"
            "- What edge cases affect the user? (e.g. what happens at boundaries)\n\n"
            "DO NOT include:\n"
            "- Code architecture, file structure, or module decomposition\n"
            "- Function signatures, data types, or implementation patterns\n"
            "- Framework-specific API calls or technical solutions\n"
            "  (Framework requirements are appended separately after your output.)\n\n"
            f"User Request:\n{task}\n\n"
            "Output format:\n\n"
            "# [Project Name]\n\n"
            "## Objective\n"
            "[What this project delivers to the user — one paragraph]\n\n"
            "## User Experience\n"
            "[Describe the complete user flow from start to finish]\n\n"
            "## Requirements\n"
            "- [Specific user-facing requirement 1]\n"
            "- [Specific user-facing requirement 2]\n\n"
            "## Visual Design\n"
            "[Colors, layout, feedback, animations the user should see]\n"
        )
        
        # Initialize LLM for the manager
        if not hasattr(self, 'llm'):
            from ..utils.llm import LLM
            llm_config = get_llm_config()
            self.llm = LLM(llm_config)
        
        part1 = self.llm.generate(prompt)

        # Part 2: append template verbatim as framework-specific requirements
        part2 = ""
        if template_text.strip():
            part2 = (
                "\n\n---\n\n"
                "## Framework & Technical Requirements\n\n"
                f"{template_text.strip()}\n"
            )

        return part1 + part2

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
        self.log_operation("user_ask", directory, {
            "question": question[:200],
            "answer_preview": answer[:200],
        })
        logger.info(f"[manager] ASK mode: Answered question: {question[:50]}...")
        return answer

