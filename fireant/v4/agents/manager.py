import json
import logging
from pathlib import Path

from agents.base import BaseAgent

# Template directory lives alongside the agents package
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_DEFAULT_TEMPLATE = "kaplay_web_game.txt"

logger = logging.getLogger("fireant")


class ManagerAgent(BaseAgent):
    """User-facing communication agent.

    Three modes:
        DO    — Create PRD from user task, kick off the system.
        ASK   — Answer user questions using LLM with project context.
        DEBUG — Analyze user-reported issues, push fix_request signals.

    Manager does NOT write code or tests.
    """

    role = "manager"

    # ── DO mode ──────────────────────────────────────────────────────

    def handle_do(self, task: str, project_dir: Path, template: str = _DEFAULT_TEMPLATE) -> None:
        """Create PRD on disk from template + user task."""
        template_path = _TEMPLATES_DIR / template
        template_text = ""
        if template_path.exists():
            template_text = template_path.read_text()
        else:
            logger.warning(f"[manager] Template not found: {template_path}")

        prd_content = self._generate_prd(task, template_text)
        self.write_prd(project_dir, prd_content)
        self.log_operation("user_do", project_dir, {
            "task": task[:200],
            "template": template,
        })
        logger.info(f"[manager] DO mode: Created PRD (template={template})")

    def _generate_prd(self, task: str, template_text: str) -> str:
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

        part1 = self.llm.generate(prompt)

        part2 = ""
        if template_text.strip():
            part2 = (
                "\n\n---\n\n"
                "## Framework & Technical Requirements\n\n"
                f"{template_text.strip()}\n"
            )

        return part1 + part2

    # ── ASK mode ─────────────────────────────────────────────────────

    def handle_ask(self, question: str, project_dir: Path) -> str:
        """Answer user questions about the project."""
        prd_content = self.read_prd(project_dir) or ""
        code_files = self.get_code_files(project_dir)
        code_snippets = []
        for f in code_files[:10]:
            code_snippets.append(f"=== {f.relative_to(project_dir)} ===\n{f.read_text()[:500]}")
        code_context = "\n\n".join(code_snippets)

        context = f"PRD:\n{prd_content}\n\nCode:\n{code_context}"
        prompt = (
            f"User question: {question}\n\n"
            "Provide a clear, concise answer based on the project context."
        )

        answer = self.llm.generate(prompt, context=context)
        self.log_operation("user_ask", project_dir, {
            "question": question[:200],
            "answer_preview": answer[:200],
        })
        logger.info(f"[manager] ASK mode: Answered question: {question[:50]}...")
        return answer

    # ── DEBUG mode ───────────────────────────────────────────────────

    def handle_debug(self, instructions: str, project_dir: Path) -> str:
        """Analyze user-reported issue and push fix_request signals."""
        prd_content = self.read_prd(project_dir) or ""
        code_files = self.get_code_files(project_dir)
        code_snippets = []
        for f in code_files[:10]:
            rel = str(f.relative_to(project_dir))
            code_snippets.append(f"=== {rel} ===\n{f.read_text()[:1000]}")
        code_context = "\n\n".join(code_snippets)

        context = f"PRD:\n{prd_content}\n\nCode:\n{code_context}"
        prompt = (
            f"User reported an issue:\n{instructions}\n\n"
            "Analyze the code and identify which files need fixes.\n"
            "Return a JSON array of objects: [{\"file\": \"layer_1/foo.js\", \"details\": \"what is wrong\"}]"
        )

        raw = self.llm.generate_json(prompt, context=context)
        self.log_operation("user_debug", project_dir, {"instructions": instructions[:200]})

        # Push fix_request signals for each identified file
        try:
            fixes = json.loads(raw)
        except json.JSONDecodeError:
            logger.error(f"[manager] Failed to parse debug analysis: {raw[:200]}")
            return "Could not analyze the issue."

        if self.signals and isinstance(fixes, list):
            for fix in fixes:
                self.signals.push_signal("fix_request", {
                    "file": fix.get("file", ""),
                    "details": fix.get("details", ""),
                }, producer="manager")

        logger.info(f"[manager] DEBUG mode: Pushed {len(fixes)} fix_request signals")
        return f"Identified {len(fixes)} files to fix."

    # ── README generation ────────────────────────────────────────────

    def generate_readme(self, project_dir: Path) -> None:
        """Generate a README.md after project completion."""
        prd_content = self.read_prd(project_dir) or ""
        prompt = (
            "Generate a concise README.md for this project.\n"
            "Include: project name, description, how to run, key features.\n"
            "Keep it under 200 words."
        )
        readme = self.llm.generate(prompt, context=f"PRD:\n{prd_content}")
        self.write_file(project_dir / "README.md", readme)
        logger.info("[manager] Generated README.md")

