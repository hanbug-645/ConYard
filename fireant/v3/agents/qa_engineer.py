import logging
import re
import subprocess
from pathlib import Path

from .base import BaseAgent
from ..utils.manifest import update_field

logger = logging.getLogger("fireant")


class QAEngineerAgent(BaseAgent):
    """Writes and executes unit tests for each file individually.
    
    ═══════════════════════════════════════════════════════════════
    DUTY: PER-FILE TEST WRITING & EXECUTION (Step 4)
    ═══════════════════════════════════════════════════════════════
    Controls: qa_status field only.
    
    Env-signal trigger: ANY file deliverable has
        coding_status == 'done' AND qa_status == 'pending'
    
    For each ready file, writes an individual test file at
    test/test_<stem>.ext and executes it.
    On pass → sets qa_status = 'pass' (deliverable complete).
    On fail → sets qa_status = 'fail', writes _review.md
              (Engineer reads review as env signal for self-correction).
    
    What QA Engineer DOES NOT do:
    - Write application code (→ Engineer)
    - Fix bugs (→ Engineer self-correction / Debugger)
    ═══════════════════════════════════════════════════════════════
    """

    role = "qa_engineer"

    def build_folder_context(self, directory: Path) -> str:
        """Build implementation context: current + subdirs."""
        parts = []

        # Current folder context
        current_context = self.get_current_dir_context(directory)
        if current_context:
            parts.append(current_context)

        # Subdirectory context
        subdir_context = self.get_subdir_context(directory)
        if subdir_context:
            parts.append(subdir_context)

        return "\n".join(parts)

    def check_trigger(self, directory: Path) -> bool:
        manifest = self.read_manifest(directory)
        if manifest is None:
            return False

        deliverables = manifest.get("deliverables", [])

        # All child subdirectories must be complete (coded + tested) first
        dir_deliverables = [d for d in deliverables if d.get("type") == "directory"]
        if dir_deliverables and not all(
            d.get("status") == "complete" for d in dir_deliverables
        ):
            return False

        file_deliverables = [d for d in deliverables if d.get("type") == "file"]
        if not file_deliverables:
            return False

        # Trigger when ANY file is coded and awaiting QA — no need to wait for all.
        # Engineer should fix QA failures before QA re-runs those files.
        return any(
            d.get("coding_status") == "done" and d.get("qa_status") == "pending"
            for d in file_deliverables
        )

    def _execute_impl(self, directory: Path) -> None:
        prd_content = self.read_prd(directory)
        if not prd_content:
            return

        manifest = self.read_manifest(directory)
        if manifest is None:
            return

        ready_files = [
            d for d in manifest["deliverables"]
            if d.get("type") == "file"
            and d.get("coding_status") == "done"
            and d.get("qa_status") == "pending"
        ]
        if not ready_files:
            return

        folder_ctx = self.build_folder_context(directory)
        all_failed: list[str] = []
        all_outputs: list[str] = []

        for deliverable in ready_files:
            filename = deliverable["name"]
            code_path = directory / filename
            if not code_path.exists():
                continue

            code = code_path.read_text()

            # Static validation: check import paths resolve to real files
            import_errors = self._validate_imports(directory, {filename: code})
            if import_errors:
                error_report = "\n".join(import_errors)
                update_field(directory, filename, "qa_status", "fail")
                all_failed.append(filename)
                all_outputs.append(
                    f"## {filename} (import validation)\n```\n{error_report}\n```\n"
                    f"Fix the import paths to match files that actually exist in the project."
                )
                self.log_operation("qa_fail", directory, {
                    "failed_files": [filename],
                    "output_preview": error_report[:200],
                })
                logger.info(f"[qa_engineer] Import validation FAILED for {filename} in {directory}")
                continue

            # Determine language and test path
            lang = self._detect_language({Path(filename).suffix})
            lang_ext = {"javascript": ".js", "python": ".py"}.get(lang, ".js")
            stem = Path(filename).stem
            test_filename = f"test_{stem}{lang_ext}"
            test_rel = f"test/{test_filename}"
            test_path = directory / test_rel
            test_path.parent.mkdir(parents=True, exist_ok=True)

            test_code = self._generate_test(
                prd_content, filename, code, lang, folder_ctx, test_rel,
            )
            test_path.write_text(test_code)

            # Validate the generated test's own imports before running
            test_import_errors = self._validate_imports(
                directory, {test_rel: test_code},
            )
            if test_import_errors:
                logger.warning(
                    f"[qa_engineer] Generated test {test_rel} has broken imports, "
                    f"will retry: {test_import_errors}"
                )
                continue

            self.log_operation("tests_written", directory, {
                "test_file": test_rel,
                "file_tested": filename,
            })

            passed, output = self._run_tests(directory, test_rel, lang)

            if passed:
                update_field(directory, filename, "qa_status", "pass")
                self.log_operation("qa_pass", directory, {"file": filename})
                logger.info(f"[qa_engineer] Tests PASSED for {filename} in {directory}")
            else:
                update_field(directory, filename, "qa_status", "fail")
                all_failed.append(filename)
                all_outputs.append(
                    f"## {filename} ({test_rel})\n```\n{output[:1000]}\n```"
                )
                self.log_operation("qa_fail", directory, {
                    "failed_files": [filename],
                    "output_preview": output[:200],
                })
                logger.info(f"[qa_engineer] Tests FAILED for {filename} in {directory}")

        if all_failed:
            failed_list = "\n".join(f"- {name}" for name in all_failed)
            self.write_review(directory, (
                f"# QA Test Failures\n\n"
                + "\n\n".join(all_outputs)
                + f"\n\n## Files That Need Fixes\n{failed_list}\n"
            ))

    # ── Language detection ─────────────────────────────────────────────

    @staticmethod
    def _detect_language(extensions: set[str]) -> str:
        if extensions & {".py"}:
            return "python"
        if extensions & {".js", ".jsx"}:
            return "javascript"
        if extensions & {".ts", ".tsx"}:
            return "typescript"
        if extensions & {".go"}:
            return "go"
        if extensions & {".java"}:
            return "java"
        return "javascript"  # default

    # ── Test execution ─────────────────────────────────────────────────

    def _run_tests(self, directory: Path, test_filename: str, lang: str) -> tuple[bool, str]:
        """Execute the test file and return (passed, output)."""
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
            passed = result.returncode == 0
            return passed, output
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
        if lang == "go":
            return ["go", "test", "-v", "-run", "."]
        return None

    # ── LLM calls ──────────────────────────────────────────────────────

    def _generate_test(
        self,
        prd: str,
        filename: str,
        code: str,
        lang: str,
        folder_ctx: str = "",
        test_file_rel: str = "test/test_file.js",
    ) -> str:
        """Generate test code for a single source file."""
        basename = Path(filename).name
        import_example = f"  `import {{ ... }} from '../{basename}';`"

        ctx_parts = []
        ctx_parts.append(f"PRD:\n{prd}")
        ctx_parts.append(f"=== {basename} ===\n```\n{code}\n```")
        context = "\n\n".join(ctx_parts)

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
            "- Use ONLY `import` syntax. NEVER use `require()` — it does not exist in ESM.\n"
            f"- The test file lives at `{test_file_rel}`.\n"
            "  The source file is in the PARENT directory. Import with `../` prefix.\n"
            f"- Use EXACTLY this import path:\n{import_example}\n"
            "  Do NOT add subdirectory prefixes — the test is already in the right folder.\n"
            "- ONLY import from the file under test. Do NOT import from other project files.\n"
            "- ALWAYS include the `.js` extension in import paths.\n\n"
            "KAPLAY GAME TESTING RULES:\n"
            "- Do NOT try to mock or simulate Kaplay (k.add, k.scene, k.pos, etc.)\n"
            "- Do NOT test functions that primarily call Kaplay APIs (scenes, main, entity wiring)\n"
            "- ONLY test pure logic functions: math helpers, config values, coordinate calculations,\n"
            "  geometry math, state transitions, utility logic, etc.\n"
            "- If a function takes `k` as a parameter, SKIP it — it depends on Kaplay runtime\n"
            "- If the file is entirely Kaplay-dependent, write a minimal test that just validates\n"
            "  any exported constants or basic data, then exit with success\n"
            "- Tests run in Node.js — there is NO browser, NO DOM, NO Kaplay runtime\n\n"
            "Return ONLY the complete test source code. No markdown fences."
        )

        return self.llm.generate(prompt, context=context)

    @staticmethod
    def _validate_imports(directory: Path, code_contents: dict[str, str]) -> list[str]:
        """Check that all JS/TS import paths resolve to real files.

        Returns a list of error strings, empty if all imports are valid.
        """
        # Match: import ... from './path.js'  or  import ... from "../path.js"
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
                    errors.append(f"{filename}: import '{import_path}' not found (resolved to {resolved.relative_to(directory)})")
        return errors

    @staticmethod
    def _test_framework(lang: str) -> str:
        return {
            "python": "pytest (assert statements)",
            "javascript": "console.assert or simple assert with process.exit(1) on failure",
            "typescript": "console.assert or simple assert",
            "go": "testing package",
            "java": "JUnit",
        }.get(lang, "built-in assertions")
