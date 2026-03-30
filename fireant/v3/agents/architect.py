import json
import logging
from pathlib import Path

from .base import BaseAgent
from ..utils.config import get_architect_config
from ..utils.manifest import STANDARD_FILES, create_manifest

logger = logging.getLogger("fireant")


class ArchitectAgent(BaseAgent):
    """Decomposes PRD into deliverables using divide-and-conquer.
    
    ═══════════════════════════════════════════════════════════════
    DUTY: MANIFEST CREATION (Step 2) — DIVIDE & CONQUER
    ═══════════════════════════════════════════════════════════════
    Architect reads the PRD and decomposes work using divide-and-conquer.
    Don't try to solve everything in one layer — create subdirectories
    and let future Architect invocations handle their decomposition.
    
    HARD LIMITS:
    - Max files per directory (from config)
    - Max subdirectories per directory (from config)
    - Each file < max_lines (from config), does ONE thing
    - Each subdir gets its own _prd.md for recursive decomposition
    
    Strategy: if complexity > 6 files, split into subdirectories.
    Each subdir gets its own _prd.md, triggering Architect recursively.
    
    For subdirectories, writes _prd.md in each so the Architect
    is recursively triggered there by the pipeline scanner.
    
    What Architect DOES NOT do:
    - Write code (→ Engineer agent)
    ═══════════════════════════════════════════════════════════════

    Trigger: has _prd.md but no _manifest.json
    """

    role = "architect"

    def __init__(self):
        super().__init__()
        self.config = get_architect_config()

    def check_trigger(self, directory: Path) -> bool:
        if not self.has_prd(directory):
            return False
        if self.has_manifest(directory):
            return False
        return True

    def _execute_impl(self, directory: Path) -> None:
        prd_content = self.read_prd(directory)
        if not prd_content:
            logger.warning(f"[architect] Empty prd.md in {directory}")
            return

        # Note existing subdirs to avoid duplicates
        skip_names = {"lib", "test", "node_modules", "__pycache__"}
        existing_components = {
            d.name for d in self.get_subdirs(directory)
            if not d.name.startswith((".", "_")) and d.name not in skip_names
        }

        # Get limits from config
        max_files = self.config["max_files_per_dir"]
        max_subdirs = self.config["max_subdirs_per_dir"]
        max_lines = self.config["max_lines_per_file"]

        # Detect root: no parent manifest means this is the project root
        parent = directory.parent
        is_root = not (parent / STANDARD_FILES["manifest"]).exists()

        folder_ctx = self.build_folder_context(directory)
        plan = self._plan_deliverables(
            prd_content, folder_ctx, directory.name,
            max_files, max_subdirs, max_lines,
            is_root=is_root,
        )
        # Deduplicate: if LLM returns multiple deliverables with the same name,
        # keep only the LAST one (it tends to be more specific).
        seen_names = {}
        for idx, d in enumerate(plan):
            seen_names[d.get("name")] = idx
        deliverables = [plan[i] for i in sorted(seen_names.values())]
        if len(deliverables) < len(plan):
            dropped = len(plan) - len(deliverables)
            logger.warning(f"[architect] Dropped {dropped} duplicate deliverable name(s)")

        # Collect directory names so we can strip files that duplicate a sibling dir
        dir_names = {d["name"] for d in deliverables if d.get("type") == "directory"}

        manifest_entries = []
        dir_count = 0
        file_count = 0
        _seen_dirs = set()  # track auto-promoted directories

        for d in deliverables:
            d_type = d.get("type", "file")
            name = d["name"]
            description = d.get("description", "")
            exports = d.get("exports", {})

            # Enforce hard limits
            if d_type == "directory" and dir_count >= max_subdirs:
                logger.warning(f"[architect] Skipping subdir {name}: hit {max_subdirs}-subdir limit")
                continue
            if d_type == "file" and file_count >= max_files:
                logger.warning(f"[architect] Skipping file {name}: hit {max_files}-file limit")
                continue

            # At project root, only main.js is allowed as a file
            if d_type == "file" and is_root and name != "main.js":
                logger.warning(f"[architect] Dropping root file '{name}': only main.js allowed at root")
                continue

            # Drop files whose stem duplicates a sibling directory name
            if d_type == "file":
                stem = name.rsplit(".", 1)[0] if "." in name else name
                if stem in dir_names:
                    logger.warning(f"[architect] Dropping file '{name}': duplicates sibling directory '{stem}/'")
                    continue

            if d_type == "directory":
                # Create subdirectory with detailed LLM-generated sub-PRD
                subdir = directory / name
                if name not in existing_components:
                    subdir.mkdir(parents=True, exist_ok=True)
                    sub_prd = self._generate_subdir_prd(
                        prd_content, name, description, exports,
                    )
                    self.write_prd(subdir, sub_prd)
                    self.log_operation("create_sub_prd", directory, {
                        "subdir": name,
                        "description": description,
                        "exports": list(exports.keys()) if exports else [],
                    })
                    logger.info(f"[architect] Created sub-PRD for {name}/")
                manifest_entries.append({
                    "name": name,
                    "type": "directory",
                    "description": description,
                    "exports": exports,
                })
                dir_count += 1
            else:
                # Convention: deliverable names are always LOCAL to this directory.
                # If LLM returned a path like "config/game.js", promote the prefix
                # to a directory deliverable and keep only the basename as context.
                if "/" in name:
                    dir_name = name.split("/")[0]
                    base_name = name.split("/")[-1]
                    logger.warning(f"[architect] Path in file name: {name} → promoting '{dir_name}/' to directory")

                    # Create the directory deliverable (if not already seen)
                    if dir_name not in _seen_dirs:
                        _seen_dirs.add(dir_name)
                        if dir_count < max_subdirs:
                            subdir = directory / dir_name
                            prd_path = subdir / STANDARD_FILES["prd"]
                            if not prd_path.exists():
                                subdir.mkdir(parents=True, exist_ok=True)
                                sub_prd = self._generate_subdir_prd(
                                    prd_content, dir_name, description, exports,
                                )
                                self.write_prd(subdir, sub_prd)
                                self.log_operation("create_sub_prd", directory, {
                                    "subdir": dir_name,
                                    "description": description,
                                })
                                logger.info(f"[architect] Created sub-PRD for {dir_name}/")
                            manifest_entries.append({
                                "name": dir_name,
                                "type": "directory",
                                "description": description,
                                "exports": exports,
                            })
                            dir_count += 1
                    # Do NOT add the path-based file to manifest —
                    # the sub-architect will decompose the directory into files.
                    continue

                # File deliverable with exports contract
                manifest_entries.append({
                    "name": name,
                    "type": "file",
                    "description": description,
                    "exports": exports,
                })
                file_count += 1

        manifest = create_manifest(manifest_entries)
        self.write_manifest(directory, manifest)


        self.log_operation("create_manifest", directory, {
            "files": file_count, "directories": dir_count,
            "is_replan": False,
        })
        logger.info(
            f"[architect] Planned {directory}: "
            f"{file_count} files + {dir_count} subdirectories"
        )

    # ── Helpers ──────────────────────────────────────────────────────

    def _generate_subdir_prd(
        self,
        parent_prd: str,
        name: str,
        description: str,
        exports: dict,
    ) -> str:
        """Use LLM to generate a detailed sub-PRD for a subdirectory.

        The sub-PRD inherits relevant context from the parent PRD so that
        engineers have enough detail to implement correctly (e.g. game
        mechanics, data formats, edge cases).
        """
        exports_block = ""
        if exports:
            exports_lines = [f"- `{sig}`: {desc}" for sig, desc in exports.items()]
            exports_block = "Required exports:\n" + "\n".join(exports_lines)

        prompt = (
            f"Write a detailed FUNCTIONAL SPECIFICATION for the `{name}/` module.\n\n"
            f"Module purpose: {description}\n\n"
            f"{exports_block}\n\n"
            "This document is the PRIMARY reference an engineer will use to implement\n"
            "the module. It must contain enough detail that the engineer can build\n"
            "correct, complete logic WITHOUT reading the parent PRD.\n\n"
            "This module exists because parent-level files DEPEND ON this child module.\n"
            "It should contain logic or data that must be implemented first so parent files\n"
            "can import it later. Describe what dependency role this module serves for its\n"
            "parent directory and what parent-level responsibilities rely on it.\n\n"
            "MUST INCLUDE:\n"
            "- **Dependency role**: Explain why parent-level files depend on this module\n"
            "  and why it should be implemented before them. Identify what parent-level\n"
            "  responsibilities rely on this module.\n"
            "- **Functional behaviors**: Describe step-by-step what happens for each\n"
            "  feature this module handles. Use cause-and-effect language:\n"
            "  'When X happens, Y must occur, then Z follows.'\n"
            "  Example: 'When entity A collides with entity B:\n"
            "  1. Entity B is destroyed. 2. A new entity B spawns at a\n"
            "  random valid position. 3. Entity A's state updates accordingly.\n"
            "  4. A counter increments by INCREMENT_VALUE.'\n"
            "- **State transitions**: What states exist, what triggers transitions,\n"
            "  what is reset or preserved across transitions.\n"
            "- **Concrete values**: All constants, speeds, sizes, colors, timings\n"
            "  that this module needs, with exact numbers from the parent PRD.\n"
            "- **Edge cases and boundaries**: What happens at boundaries, at zero,\n"
            "  at maximum values, when collections are empty, etc.\n"
            "- **Data types**: Exact types for function parameters and return values.\n"
            "- **Relationships**: How values relate to each other\n"
            "  (e.g. 'total_width = NUM_COLUMNS * CELL_SIZE').\n\n"
            "CRITICAL CONSTRAINT:\n"
            "- Config/constant files have NO access to `k` (the Kaplay instance).\n"
            "  ALL colors must be plain arrays [r, g, b], NOT k.rgb() or k.Color().\n"
            "  ALL positions/vectors must be plain objects {x, y}, NOT k.vec2().\n"
            "  The caller converts to Kaplay types at the call site.\n\n"
            "DO NOT INCLUDE:\n"
            "- Implementation code or pseudocode.\n"
            "- Export signature lists (the manifest handles that).\n"
            "- Vague requirements — every behavior must be specific and testable.\n\n"
            f"Output plain markdown. Start with `# {name}`.\n"
        )

        context = f"Parent PRD:\n{parent_prd}"
        result = self.llm.generate(prompt, context=context)

        # Fallback if LLM fails
        if not result or not result.strip():
            lines = [f"# {name}", "", "## Core Function", description, ""]
            if exports:
                lines += ["## Exports"]
                for sig, desc in exports.items():
                    lines.append(f"- `{sig}`: {desc}")
                lines.append("")
            return "\n".join(lines) + "\n"

        return result.strip() + "\n"

    # ── LLM calls ────────────────────────────────────────────────────

    def _plan_deliverables(
        self, prd_content: str, folder_ctx: str = "", current_dir_name: str = ".",
        max_files: int = 6,
        max_subdirs: int = 5,
        max_lines: int = 1000,
        is_root: bool = False,
    ) -> list:
        """Decide whether to create files or subdirectories for this PRD.

        Returns:
          - deliverables: list of dicts with keys: name, type, description, exports
        """
        prompt = (
            "Analyze this PRD and plan deliverables.\n\n"
            f"Current directory: {current_dir_name}\n"
            "All planned deliverables must be immediate children of this directory.\n"
            "Do NOT recreate the current directory name as a child deliverable.\n\n"
            "KAPLAY ARCHITECTURE:\n"
            "- Use Kaplay's functional Entity-Component System. NO classes or deep inheritance.\n"
            "- Game objects are built by composing arrays of functional components:\n"
            "  e.g. k.add([sprite('hero'), pos(100,200), area(), body(), health(3)])\n\n"
            "FILE & DIRECTORY STRUCTURE:\n"
            "- Prefer a FLAT file structure by default within the current directory.\n"
            "  Start from files, not subdirectories.\n"
            "- ALL deliverable names are LOCAL to this directory — no paths with '/'.\n"
            "  WRONG: \"name\": \"config/game.js\"\n"
            "  RIGHT: \"name\": \"config\", \"type\": \"directory\"\n"
            "- Create a subdirectory ONLY when multiple files in the current directory\n"
            "  depend on the same child dependency module.\n"
            "  Good subdirectory reasons: constants/config needed by parent files, helper logic\n"
            "  that parent files import, dependency modules that must exist before parent orchestration.\n"
            "- If a concern is used by just one parent file, keep it as a flat file in the\n"
            "  current directory instead of making a subdirectory.\n"
            "- To group files in a subdirectory, create a deliverable with \"type\": \"directory\".\n"
            "  The sub-architect will decompose it into files automatically.\n"
            "- Code in subdirectories is generated BEFORE parent-level files.\n"
            "  Therefore, only put child dependency modules in subdirectories when parent-level\n"
            "  files need them to exist first.\n"
            "- Parent-level files (main.js, scenes, orchestration) import FROM subdirectories.\n"
            "- Inside a focused module directory, prefer files over creating more subdirectories.\n"
            "  Only create a child directory when it is a clearly distinct sub-concern, not a repeat\n"
            "  of the current directory's purpose.\n"
            "- Keep the structure SIMPLE — typically 1-2 subdirectories + a few parent files.\n"
            "  Do NOT over-split into many tiny subdirectories.\n"
            "- Sibling files in the SAME directory should NOT import from each other.\n"
            "  If they need shared logic, that logic belongs in a subdirectory.\n\n"
            "DEPENDENCY GRAPH:\n"
            "- Shape: a TREE, not a web. Parent imports from children, never the reverse.\n"
            "- Dependencies are ONLY between a parent and its DIRECT children.\n"
            "  A parent file must NEVER import directly from a grandchild (child's child).\n"
            "  If a parent needs a function from a grandchild, the CHILD directory must\n"
            "  re-export that function so the parent imports from the child only.\n"
            "  WRONG: import { foo } from './utils/config/constants.js'  (grandchild)\n"
            "  RIGHT: import { foo } from './utils/constants.js'  (child re-exports it)\n"
            "- main.js is the root — it imports from everything and wires the app together.\n"
            "- Subdirectory modules are independent leaves — they export functions but do NOT\n"
            "  import from siblings or parent-level files.\n\n"
            "HARD LIMITS:\n"
            f"- Maximum {max_files} files in this directory\n"
            f"- Maximum {max_subdirs} subdirectories — keep it minimal\n"
            f"- Each file does ONE thing, under {max_lines} lines\n\n"
            "RULES:\n"
            "- File names: lowercase (e.g. \"main.js\", \"entities.js\", \"config.js\")\n"
            "- Do NOT include index.html — it is pre-created with Kaplay loaded\n"
            "- The main entry point should be main.js (loaded by index.html)\n"
            "- main.js calls `const k = kaplay({...})` using the GLOBAL kaplay function\n"
            "  (loaded via <script> tag). Do NOT give main.js an export like `initGame(k)`.\n"
            "  main.js is the top-level wiring — it imports scenes/modules and calls them with `k`.\n"
            "- Prefer passing data through function arguments over shared state\n\n"
            + (
                "ROOT DIRECTORY RULE (this IS the project root):\n"
                "- The ONLY file at root must be main.js. ALL other code goes into subdirectories.\n"
                "- Do NOT create files like constants.js, scenes.js, entities.js, etc. at root.\n"
                "- Root = main.js (entry point) + subdirectories (logic modules). Nothing else.\n\n"
                if is_root else ""
            ) +
            "DIRECTORY DECISION RULE:\n"
            "- Before creating any directory deliverable, ask: 'Will parent-level files depend\n"
            "  on this child module?'\n"
            "- If NO, keep it as a flat file.\n"
            "- If YES, a directory is allowed.\n"
            "- Do NOT create a directory just to separate one feature or one scene from another.\n"
            "- Do NOT create a directory whose purpose merely repeats the current directory's purpose.\n\n"
            "UNIQUE NAMES — CRITICAL:\n"
            "- Every deliverable MUST have a UNIQUE name. NEVER output two deliverables with the same name.\n"
            "- If the LLM wants to split a concern, give each part a distinct name.\n\n"
            "DESCRIPTION QUALITY — CRITICAL:\n"
            "- Descriptions must be SPECIFIC and FUNCTIONAL, not generic containers.\n"
            "  WRONG: 'Contains configuration files for utility modules.'\n"
            "  RIGHT: 'Defines grid dimensions (GRID_WIDTH, GRID_HEIGHT, CELL_SIZE) and\n"
            "          derived playfield pixel sizes used by all grid-based calculations.'\n"
            "- Every description must answer: WHAT specific data/logic does this provide,\n"
            "  and WHAT concrete values or behaviors does it define?\n"
            "- If a description could apply to any project, it is too vague. Rewrite it.\n\n"
            "EXPORTS CONTRACT — for EVERY file you MUST specify:\n"
            "- Its core function in one sentence (description)\n"
            "- Its exports: a map of signatures to descriptions.\n"
            "  For functions: \"funcName(param: type, ...) -> returnType\"\n"
            "  For constants: \"CONST_NAME: type\" (e.g. \"MAX_SPEED: number\", \"START_POS: {x: number, y: number}\")\n"
            "  Be TYPE-PRECISE — engineers will consume these exact types across files.\n"
            "  Use plain JS types (number, string, boolean, object, array) ONLY.\n"
            "  NEVER use framework-specific runtime types in config/constant exports.\n"
            "  Config files have NO access to `k` (the Kaplay instance) — it only exists in main.js.\n"
            "  WRONG: \"SNAKE_COLOR: object\" described as \"Kaplay color object (k.rgb)\" — k is undefined here!\n"
            "  RIGHT: \"SNAKE_COLOR: [number, number, number]\" described as \"RGB values [r, g, b]\"\n"
            "  Colors must be plain arrays like [100, 200, 100]. Convert to k.Color(...) at call site.\n"
            "Return a JSON array where each element has:\n"
            "   - \"name\": LOCAL name only (e.g. \"main.js\", \"config\") — NEVER a path with '/'\n"
            "   - \"type\": \"file\" or \"directory\"\n"
            "   - \"description\": what this module does\n"
            "   - \"exports\": object mapping typed signatures to descriptions\n"
            '   e.g. {"updateState(state: object, input: string) -> object": "Advance game state one step"}\n\n'
            f"PRD:\n{prd_content}"
        )

        ctx = folder_ctx
        raw = self.llm.generate_json(prompt, context=ctx)
        try:
            result = json.loads(raw)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            logger.error(f"[architect] Failed to parse deliverables: {raw[:200]}")

        return []
