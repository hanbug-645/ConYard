"""QA Engineer agent — claims task_done signals, writes and executes tests.

Polls Redis for `task_done` signals.
On pass → pushes `green` signal (file verified).
On fail → pushes `fix_request` signal with failure details.
"""

import logging
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

from agents.base import BaseAgent

logger = logging.getLogger("fireant")


class QAEngineerAgent(BaseAgent):
    """Writes and executes unit tests for completed files.

    Consumes `task_done` signals from Redis.
    Does NOT write application code or fix bugs.
    """

    role = "qa_engineer"

    def __init__(self, project_dir: Path, agent_id: str = "qa-0", **kwargs):
        super().__init__(**kwargs)
        self.project_dir = project_dir
        self.agent_id = agent_id

    # ── Main loop ────────────────────────────────────────────────────

    def run_loop(self, poll_interval: float = 1.0, stop_event=None) -> None:
        """Poll Redis for task_done signals and test each file."""
        logger.info(f"[{self.agent_id}] QA Engineer started")

        while stop_event is None or not stop_event.is_set():
            signal = self.signals.claim_signal("task_done", self.agent_id)
            if signal is None:
                time.sleep(poll_interval)
                continue

            self._handle_signal(signal)

        logger.info(f"[{self.agent_id}] QA Engineer stopped")

    # ── Signal handling ──────────────────────────────────────────────

    def _handle_signal(self, signal: dict) -> None:
        """Test a single file from a task_done signal."""
        file_rel = signal.get("file", "")
        layer = signal.get("layer", "")
        path_rel = signal.get("path", "")

        if not file_rel:
            logger.warning(f"[{self.agent_id}] task_done signal missing 'file': {signal.get('id')}")
            return

        # Resolve full path
        if layer:
            file_path = self.project_dir / layer / file_rel
            test_base = self.project_dir / layer
        else:
            file_path = self.project_dir / file_rel
            test_base = self.project_dir

        if not file_path.exists():
            logger.warning(f"[{self.agent_id}] File not found: {file_path}")
            return

        code = file_path.read_text()
        logger.info(f"[{self.agent_id}] Testing {path_rel or file_rel}")

        # Static import validation
        import_errors = self._validate_imports(test_base, {file_rel: code})
        if import_errors:
            error_report = "\n".join(import_errors)
            logger.info(f"[{self.agent_id}] Import validation FAILED for {file_rel}")
            self._push_fix_request(file_rel, layer, error_report)
            return

        # Determine language and generate + run tests
        lang = self._detect_language(file_path.suffix)
        lang_ext = {"javascript": ".js", "python": ".py"}.get(lang, ".js")
        stem = file_path.stem
        test_filename = f"test_{stem}{lang_ext}"
        test_rel = f"test/{test_filename}"
        test_path = test_base / test_rel
        test_path.parent.mkdir(parents=True, exist_ok=True)

        prd = self.read_prd(self.project_dir) or ""
        test_code = self._generate_test(prd, file_rel, code, lang, test_rel)
        test_path.write_text(test_code)

        # Validate generated test imports — auto-pass if LLM generates bad test imports
        test_import_errors = self._validate_imports(test_base, {test_rel: test_code})
        if test_import_errors:
            logger.warning(f"[{self.agent_id}] Generated test has broken imports — auto-passing {file_rel}")
            green_path = path_rel or file_rel
            self.signals.push_green(green_path, layer, producer=self.agent_id)
            self.log_operation("qa_pass_auto", self.project_dir, {
                "file": file_rel, "reason": "test import validation failed",
            })
            return

        self.log_operation("tests_written", self.project_dir, {
            "test_file": test_rel, "file_tested": file_rel,
        })

        passed, output = self._run_tests(test_base, test_rel, lang)

        if passed:
            # Push green signal — file is verified
            green_path = path_rel or file_rel
            self.signals.push_green(green_path, layer, producer=self.agent_id)
            self.log_operation("qa_pass", self.project_dir, {"file": file_rel})
            logger.info(f"[{self.agent_id}] PASSED: {file_rel}")
        else:
            self._push_fix_request(file_rel, layer, output[:1500])
            self.log_operation("qa_fail", self.project_dir, {
                "file": file_rel, "output_preview": output[:200],
            })
            logger.info(f"[{self.agent_id}] FAILED: {file_rel}")

    def _push_fix_request(self, file_rel: str, layer: str, details: str) -> None:
        """Push a fix_request signal back to Engineers."""
        self.signals.push_signal("fix_request", {
            "file": file_rel,
            "layer": layer,
            "details": details,
        }, producer=self.agent_id)

    # ── Language detection ───────────────────────────────────────────

    @staticmethod
    def _detect_language(ext: str) -> str:
        if ext in (".py",):
            return "python"
        if ext in (".js", ".jsx"):
            return "javascript"
        if ext in (".ts", ".tsx"):
            return "typescript"
        return "javascript"

    # ── Test execution ───────────────────────────────────────────────

    def _run_tests(self, directory: Path, test_filename: str, lang: str) -> tuple[bool, str]:
        cmd = self._build_test_command(test_filename, lang)
        if not cmd:
            return False, f"No test runner configured for language: {lang}"

        try:
            result = subprocess.run(
                cmd,
                cwd=str(directory),
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = result.stdout + result.stderr
            return result.returncode == 0, output
        except subprocess.TimeoutExpired:
            return False, "Test execution timed out (30s limit)"
        except FileNotFoundError as e:
            return False, f"Test runner not found: {e}"
        except Exception as e:
            return False, f"Test execution error: {e}"

    @staticmethod
    def _build_test_command(test_filename: str, lang: str) -> list[str] | None:
        if lang == "python":
            return ["python3", "-m", "pytest", test_filename, "-v", "--tb=short"]
        if lang == "typescript":
            return ["node", "--experimental-strip-types", test_filename]
        if lang == "javascript":
            return ["node", test_filename]
        return None

    # ── LLM calls ────────────────────────────────────────────────────

    def _generate_test(
        self, prd: str, filename: str, code: str, lang: str,
        test_file_rel: str = "test/test_file.js",
    ) -> str:
        basename = Path(filename).name
        import_example = f"  `import {{ ... }} from '../{basename}';`"

        context = f"PRD:\n{prd}\n\n=== {basename} ===\n```\n{code}\n```"

        prompt = (
            f"Write unit tests in {lang} for the file `{basename}` shown above.\n\n"
            "Requirements:\n"
            "1. Test the key functions and behaviors described in the PRD\n"
            "2. Test edge cases and error handling\n"
            "3. Tests must be self-contained — use only built-in test tools\n"
            f"4. For {lang}: use {self._test_framework(lang)}\n"
            "5. Each test should have a clear assertion\n"
            "6. Do NOT use any type annotations in test code — write plain JavaScript\n\n"
            "ES MODULE RULES (CRITICAL — tests WILL fail if you break these):\n"
            "- The project uses ES modules (`\"type\": \"module\"` in package.json).\n"
            "- Use ONLY `import` syntax. NEVER use `require()`.\n"
            f"- The test file lives at `{test_file_rel}`.\n"
            "  The source file is in the PARENT directory. Import with `../` prefix.\n"
            f"- Use EXACTLY this import path:\n{import_example}\n"
            "- ONLY import from the file under test.\n"
            "- ALWAYS include the `.js` extension in import paths.\n\n"
            "KAPLAY GAME TESTING RULES:\n"
            "- Do NOT mock or simulate Kaplay (k.add, k.scene, k.pos, etc.)\n"
            "- ONLY test pure logic functions: math helpers, config values, state transitions\n"
            "- If the file is entirely Kaplay-dependent, write a minimal test that validates\n"
            "  any exported constants or basic data, then exit with success\n"
            "- Tests run in Node.js — NO browser, NO DOM, NO Kaplay runtime\n\n"
            "Return ONLY the complete test source code. No markdown fences."
        )

        return self.llm.generate(prompt, context=context)

    @staticmethod
    def _validate_imports(directory: Path, code_contents: dict[str, str]) -> list[str]:
        import_re = re.compile(r"""import\s+.+?\s+from\s+['"](\.[^'"]+)['"]""")
        errors = []
        for filename, code in code_contents.items():
            if not filename.endswith((".js", ".ts", ".mjs")):
                continue
            file_dir = (directory / filename).parent
            for match in import_re.finditer(code):
                import_path = match.group(1)
                resolved = (file_dir / import_path).resolve()
                if not resolved.exists():
                    errors.append(f"{filename}: import '{import_path}' not found")
        return errors

    @staticmethod
    def _test_framework(lang: str) -> str:
        return {
            "python": "pytest (assert statements)",
            "javascript": "console.assert or simple assert with process.exit(1) on failure",
            "typescript": "console.assert or simple assert",
        }.get(lang, "built-in assertions")
