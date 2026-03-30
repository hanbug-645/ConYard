import logging
import threading
from pathlib import Path
from typing import Optional
import sys

from .orchestrator.pipeline import Pipeline
from .agents.manager import ManagerAgent
from .utils.config import load_config

logger = logging.getLogger("fireant")


class FireAntServer:
    """Interactive server mode for FireAnt.
    
    Listens to terminal commands and executes them:
    - DO <task>: Build a project from task description
    - ASK <question>: Ask a question about the current project
    - STATUS: Show current project status
    - STOP: Stop any running pipeline
    - EXIT: Shutdown server
    """

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.current_project: Optional[Path] = None
        self.pipeline: Optional[Pipeline] = None
        self.pipeline_thread: Optional[threading.Thread] = None
        self.running = False
        self.manager = ManagerAgent()
        
        # Import Debugger agent for DEBUG command
        from .agents.debugger import DebuggerAgent
        self.debugger = DebuggerAgent()
        
        logger.info(f"[server] Initialized with workspace: {workspace_root}")

    def start(self):
        """Start the server and listen for commands."""
        self.running = True
        print("\n" + "="*60)
        print("🔥 FireAnt Server Started")
        print("="*60)
        print("\nAvailable commands:")
        print("  DO <task>       - Build a project (e.g., 'DO build a snake game in js')")
        print("  ASK <question>  - Ask about the current project")
        print("  DEBUG <id> <instructions> - Debug a project (e.g., 'DEBUG 1227 snake not moving')")
        print("  STATUS          - Show current project status")
        print("  STOP            - Stop running pipeline")
        print("  EXIT            - Shutdown server")
        print("\n" + "="*60 + "\n")
        
        self._command_loop()

    def _command_loop(self):
        """Main command listening loop."""
        while self.running:
            try:
                # Read command from terminal
                command_line = input("fireant> ").strip()
                
                if not command_line:
                    continue
                
                # Parse command
                parts = command_line.split(maxsplit=1)
                command = parts[0].upper()
                args = parts[1] if len(parts) > 1 else ""
                
                # Execute command
                self._handle_command(command, args)
                
            except KeyboardInterrupt:
                print("\n\nReceived interrupt. Type 'EXIT' to shutdown.")
            except EOFError:
                print("\n\nEOF received. Shutting down...")
                self.running = False
            except Exception as e:
                logger.error(f"[server] Error handling command: {e}", exc_info=True)
                print(f"❌ Error: {e}")

    def _handle_command(self, command: str, args: str):
        """Handle a single command."""
        if command == "DO":
            self._handle_do(args)
        elif command == "ASK":
            self._handle_ask(args)
        elif command == "DEBUG":
            self._handle_debug(args)
        elif command == "STATUS":
            self._handle_status()
        elif command == "STOP":
            self._handle_stop()
        elif command == "EXIT":
            self._handle_exit()
        elif command == "HELP":
            self._handle_help()
        else:
            print(f"❌ Unknown command: {command}")
            print("Type 'HELP' for available commands.")

    def _handle_do(self, task: str):
        """Handle DO command - build a project."""
        if not task:
            print("❌ Usage: DO <task description>")
            print("   Example: DO build a snake game in js")
            return
        
        # Check if pipeline is already running
        if self.pipeline_thread and self.pipeline_thread.is_alive():
            print("⚠️  Pipeline is already running. Use 'STOP' to cancel it first.")
            return
        
        print(f"\n🚀 Starting project: {task}")
        
        # Create project directory
        project_name = self._generate_project_name(task)
        project_dir = self.workspace_root / "projects" / project_name
        project_dir.mkdir(parents=True, exist_ok=True)
        
        self.current_project = project_dir
        
        # Use Manager to create initial PRD
        print("📝 Creating project requirements...")
        self.manager.handle_do_mode(task, project_dir)
        
        # Start pipeline in background thread
        print("🔧 Starting build pipeline...")
        self.pipeline = Pipeline()
        self.pipeline_thread = threading.Thread(
            target=self._run_pipeline,
            args=(project_dir,),
            daemon=True
        )
        self.pipeline_thread.start()
        
        print(f"✅ Pipeline started for: {project_dir}")
        print("   Use 'STATUS' to check progress")

    def _handle_ask(self, question: str):
        """Handle ASK command - answer questions."""
        if not question:
            print("❌ Usage: ASK <question>")
            print("   Example: ASK how do I run this game?")
            return
        
        if not self.current_project or not self.current_project.exists():
            print("❌ No active project. Use 'DO' to create a project first.")
            return
        
        print(f"\n💬 Question: {question}")
        print("🤔 Thinking...")
        
        try:
            answer = self.manager.handle_ask_mode(question, self.current_project)
            print(f"\n📖 Answer:\n{answer}\n")
        except Exception as e:
            logger.error(f"[server] Error in ASK mode: {e}", exc_info=True)
            print(f"❌ Error: {e}")

    def _handle_debug(self, args: str):
        """Handle DEBUG command - debug a project by identifier."""
        if not args:
            print("❌ Usage: DEBUG <project_id> <instructions>")
            print("   Example: DEBUG 1227 the snake is not moving correctly")
            return
        
        # Parse project_id and instructions
        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            print("❌ Usage: DEBUG <project_id> <instructions>")
            print("   Example: DEBUG 1227 the snake is not moving correctly")
            return
        
        project_id = parts[0]
        instructions = parts[1]
        
        print(f"\n🐛 Debug request for project: {project_id}")
        print(f"   Instructions: {instructions}")
        
        # Manager's role: Find project (communication)
        project_dir = self._find_project_by_id(project_id)
        if not project_dir:
            print(f"❌ No project found matching '{project_id}'")
            print(f"   Projects are in: {self.workspace_root / 'projects'}")
            return
        
        print(f"   Found project: {project_dir.name}")
        
        # Delegate technical analysis to Debugger agent
        print("🔍 Analyzing project...")
        try:
            from .utils.operation_log import OperationLogger
            op_logger = OperationLogger(project_dir)
            self.debugger.set_operation_logger(op_logger)
            
            # Debugger handles escalation-based resolution
            result = self.debugger.analyze_and_fix(project_dir, instructions)
            
            print(f"\n✅ {result['message']}")
            print(f"   Project: {project_dir}")
            
        except Exception as e:
            logger.error(f"[server] Error in DEBUG mode: {e}", exc_info=True)
            print(f"❌ Error: {e}")

    def _handle_status(self):
        """Handle STATUS command - show project status."""
        if not self.current_project:
            print("ℹ️  No active project")
            return
        
        print(f"\n📊 Project Status")
        print(f"   Location: {self.current_project}")
        
        # Check if pipeline is running
        if self.pipeline_thread and self.pipeline_thread.is_alive():
            print(f"   Pipeline: 🔄 Running")
        else:
            print(f"   Pipeline: ⏸️  Stopped")
        
        # Check for status files
        if (self.current_project / "status_pass.flag").exists():
            print(f"   Status: ✅ Complete")
        elif (self.current_project / "escalation.md").exists():
            print(f"   Status: ⚠️  Escalated")
        elif (self.current_project / "manifest.json").exists():
            print(f"   Status: 🔧 In Progress")
        else:
            print(f"   Status: 📝 Planning")
        
        # Check for README
        if (self.current_project / "README.md").exists():
            print(f"   README: ✅ Available")
            readme_path = self.current_project / "README.md"
            print(f"\n   View README: cat {readme_path}")
        else:
            print(f"   README: ⏳ Pending")
        
        print()

    def _handle_stop(self):
        """Handle STOP command - stop running pipeline."""
        if not self.pipeline_thread or not self.pipeline_thread.is_alive():
            print("ℹ️  No pipeline is currently running")
            return
        
        print("⏹️  Stopping pipeline...")
        # Note: Thread will stop at next iteration check
        # Python threads can't be forcefully stopped, they finish their current work
        print("⚠️  Pipeline will stop after current iteration completes")

    def _handle_exit(self):
        """Handle EXIT command - shutdown server."""
        print("\n👋 Shutting down FireAnt server...")
        
        if self.pipeline_thread and self.pipeline_thread.is_alive():
            print("⏳ Waiting for pipeline to finish...")
            self.pipeline_thread.join(timeout=5)
        
        self.running = False
        print("✅ Goodbye!\n")

    def _handle_help(self):
        """Handle HELP command - show available commands."""
        print("\n📚 FireAnt Server Commands:")
        print("\n  DO <task>")
        print("     Build a project from task description")
        print("     Example: DO build a snake game in js")
        print("\n  ASK <question>")
        print("     Ask a question about the current project")
        print("     Example: ASK how do I run this game?")
        print("\n  DEBUG <project_id> <instructions>")
        print("     Debug a project by identifying and fixing issues")
        print("     Example: DEBUG 1227 the snake is not moving correctly")
        print("\n  STATUS")
        print("     Show current project status and location")
        print("\n  STOP")
        print("     Stop the currently running pipeline")
        print("\n  EXIT")
        print("     Shutdown the server")
        print("\n  HELP")
        print("     Show this help message")
        print()

    def _run_pipeline(self, project_dir: Path):
        """Run pipeline in background thread."""
        try:
            logger.info(f"[server] Starting pipeline for {project_dir}")
            success = self.pipeline.run(project_dir)
            
            if success:
                # Generate README after successful completion
                print(f"\n✅ Project complete: {project_dir}")
                print(f"📝 Generating README...")
                try:
                    self._generate_readme(project_dir)
                    print(f"   ✓ README.md created with entry points and instructions")
                except Exception as e:
                    logger.error(f"[server] Failed to generate README: {e}")
                    print(f"   ⚠️  README generation failed: {e}")
            else:
                print(f"\n⚠️  Pipeline stopped (max iterations reached)")
                print(f"   Project: {project_dir}")
            
            print("\nfireant> ", end="", flush=True)
            
        except Exception as e:
            logger.error(f"[server] Pipeline error: {e}", exc_info=True)
            print(f"\n❌ Pipeline error: {e}")
            print("\nfireant> ", end="", flush=True)

    def _generate_readme(self, project_dir: Path):
        """Generate README.md for completed project using Manager agent."""
        # Manager's _execute_impl logic for README generation
        prd_content = (project_dir / "prd.md").read_text() if (project_dir / "prd.md").exists() else ""
        
        # Detect project type and entry point location
        project_type = "javascript_web"  # Default for now, can be enhanced
        entry_point = None
        
        # Check for entry points at root level first
        if (project_dir / "index.html").exists():
            project_type = "javascript_web"
            entry_point = "index.html"
        elif (project_dir / "main.py").exists():
            project_type = "python"
            entry_point = "main.py"
        elif (project_dir / "app.py").exists():
            project_type = "python"
            entry_point = "app.py"
        # Fallback: check lib/ folder
        elif (project_dir / "lib" / "index.html").exists():
            project_type = "javascript_web"
            entry_point = "lib/index.html"
        elif any(project_dir.glob("**/*.html")):
            project_type = "javascript_web"
        elif (project_dir / "requirements.txt").exists():
            project_type = "python"
        
        # Get file list for context
        files = []
        for item in project_dir.rglob("*"):
            if item.is_file() and not item.name.startswith(".") and item.name not in ["prd.md", "manifest.json", "README.md"]:
                files.append(str(item.relative_to(project_dir)))
        file_list = "\n".join(sorted(files)[:20])
        
        entry_point_info = f"\n\nDetected entry point: {entry_point}" if entry_point else ""
        context = f"PRD:\n{prd_content}\n\nProject type: {project_type}{entry_point_info}\n\nProject files:\n{file_list}"
        
        prompt = (
            "Generate a comprehensive README.md for this project.\n\n"
            "CRITICAL REQUIREMENTS:\n"
            "1. **Entry Point**: Clearly state the main entry point file with its EXACT path\n"
            "2. **How to Run**: Provide step-by-step instructions to run/start the project\n"
            "3. **Dependencies**: List any required dependencies and how to install them\n"
            "4. **Project Structure**: Brief overview of the codebase organization\n\n"
        )
        
        if project_type == "javascript_web":
            prompt += (
                "For JavaScript web projects:\n"
                "- Specify the HTML entry point with its exact path (check if at root or in lib/)\n"
                "- Mention that it needs to be served via HTTP server (not file://)\n"
                "- Provide command: `python3 -m http.server` or `npx serve`\n"
                "- Include browser URL with correct path (e.g., http://localhost:8000 or http://localhost:8000/lib/)\n\n"
            )
        
        prompt += (
            "Format:\n"
            "# [Project Name]\n\n"
            "## Overview\n"
            "[Brief description]\n\n"
            "## Entry Point\n"
            "**Main file**: `[filename]`\n\n"
            "## How to Run\n"
            "```bash\n"
            "[step-by-step commands]\n"
            "```\n\n"
            "## Project Structure\n"
            "[Brief overview]\n"
        )
        
        readme_content = self.manager.llm.generate(prompt, context=context)
        readme_path = project_dir / "README.md"
        readme_path.write_text(readme_content)
        logger.info(f"[server] Generated README.md for {project_dir}")

    def _find_project_by_id(self, project_id: str) -> Optional[Path]:
        """Find project directory by identifier (timestamp or partial name)."""
        projects_dir = self.workspace_root / "projects"
        if not projects_dir.exists():
            return None
        
        # Look for projects containing the identifier
        for project_dir in projects_dir.iterdir():
            if project_dir.is_dir() and project_id in project_dir.name:
                return project_dir
        
        return None

    def _generate_project_name(self, task: str) -> str:
        """Generate a project directory name from task description."""
        from datetime import datetime
        
        # Extract key words from task
        words = task.lower().split()
        # Filter out common words
        stop_words = {"a", "an", "the", "in", "on", "at", "to", "for", "of", "with", "build", "create", "make"}
        key_words = [w for w in words if w not in stop_words][:3]
        
        # Create name with timestamp
        name_part = "_".join(key_words) if key_words else "project"
        timestamp = datetime.now().strftime("%m%d_%H%M")
        
        return f"{name_part}_{timestamp}"


def start_server(workspace_root: Optional[Path] = None):
    """Start the FireAnt server.
    
    Args:
        workspace_root: Root directory for projects. Defaults to current directory.
    """
    if workspace_root is None:
        workspace_root = Path.cwd()
    
    workspace_root = Path(workspace_root).resolve()
    
    # Ensure workspace exists
    workspace_root.mkdir(parents=True, exist_ok=True)
    
    # Start server
    server = FireAntServer(workspace_root)
    server.start()
