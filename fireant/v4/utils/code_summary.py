"""Extract function/class signatures and descriptions from source code.

Produces a compact summary suitable for LLM context — much smaller than
raw source while preserving the API surface needed for planning and coding.

Supported languages: JavaScript/TypeScript, Python.
"""

import re
from pathlib import Path


def summarize_js(code: str) -> str:
    """Extract exported symbols, function signatures, and JSDoc descriptions from JS/TS code.

    Returns a compact multi-line summary like:
        // Constants
        export const TILE_SIZE = 32;

        // playerSetup(k, config) — Initialize the player sprite and movement handlers.
        // spawnEnemy(k, type, pos) — Create an enemy at the given position.
    """
    lines = code.splitlines()
    entries: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # ── Collect JSDoc comment block above a symbol ─────────────
        jsdoc_desc = ""
        if stripped.startswith("/**"):
            doc_lines: list[str] = []
            while i < len(lines):
                dl = lines[i].strip()
                # Grab @description or first plain text line
                cleaned = dl.lstrip("/* ").rstrip("*/").strip()
                if cleaned and not cleaned.startswith("@"):
                    doc_lines.append(cleaned)
                if dl.endswith("*/"):
                    i += 1
                    break
                i += 1
            jsdoc_desc = " ".join(doc_lines)
            if i >= len(lines):
                break
            line = lines[i]
            stripped = line.strip()

        # ── Single-line // comment right before a function ─────────
        if not jsdoc_desc and stripped.startswith("//"):
            jsdoc_desc = stripped.lstrip("/ ").strip()
            i += 1
            if i >= len(lines):
                break
            line = lines[i]
            stripped = line.strip()

        # ── Exported constants / variables ─────────────────────────
        const_match = re.match(
            r"export\s+(?:const|let|var)\s+(\w+)\s*=\s*(.+)",
            stripped,
        )
        if const_match:
            name = const_match.group(1)
            value_preview = const_match.group(2)[:80].rstrip(";").strip()
            entry = f"export const {name} = {value_preview}"
            if jsdoc_desc:
                entry += f"  // {jsdoc_desc}"
            entries.append(entry)
            i += 1
            continue

        # ── Function declarations & expressions ────────────────────
        func_match = re.match(
            r"(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)",
            stripped,
        )
        if not func_match:
            # Arrow / const function
            func_match = re.match(
                r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(?([^)=]*)\)?\s*=>",
                stripped,
            )

        if func_match:
            name = func_match.group(1)
            params = func_match.group(2).strip()
            sig = f"{name}({params})"
            desc_part = f" — {jsdoc_desc}" if jsdoc_desc else ""
            entries.append(f"{sig}{desc_part}")
            i += 1
            continue

        # ── Class declarations ─────────────────────────────────────
        class_match = re.match(
            r"(?:export\s+)?(?:default\s+)?class\s+(\w+)",
            stripped,
        )
        if class_match:
            name = class_match.group(1)
            desc_part = f" — {jsdoc_desc}" if jsdoc_desc else ""
            entries.append(f"class {name}{desc_part}")
            i += 1
            continue

        i += 1

    return "\n".join(entries)


def summarize_py(code: str) -> str:
    """Extract function/class signatures and docstrings from Python code.

    Returns a compact multi-line summary like:
        def load_config(path: str) -> dict — Load YAML config from disk.
        class BaseAgent — Base class for all agents.
    """
    lines = code.splitlines()
    entries: list[str] = []

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        # ── Function / method ──────────────────────────────────────
        func_match = re.match(r"((?:async\s+)?def\s+\w+\([^)]*\)(?:\s*->\s*\S+)?)", stripped)
        if func_match:
            sig = func_match.group(1)
            docstring = _extract_py_docstring(lines, i + 1)
            desc_part = f" — {docstring}" if docstring else ""
            entries.append(f"{sig}{desc_part}")
            i += 1
            continue

        # ── Class ──────────────────────────────────────────────────
        class_match = re.match(r"(class\s+\w+(?:\([^)]*\))?)\s*:", stripped)
        if class_match:
            sig = class_match.group(1)
            docstring = _extract_py_docstring(lines, i + 1)
            desc_part = f" — {docstring}" if docstring else ""
            entries.append(f"{sig}{desc_part}")
            i += 1
            continue

        i += 1

    return "\n".join(entries)


def _extract_py_docstring(lines: list[str], start: int) -> str:
    """Extract the first line of a docstring starting at `start`."""
    if start >= len(lines):
        return ""
    stripped = lines[start].strip()
    # Single-line: """some text"""  or  '''some text'''
    single = re.match(r'^(?:\"\"\"|\'\'\')(.*?)(?:\"\"\"|\'\'\')$', stripped)
    if single:
        return single.group(1).strip()
    # Multi-line: first line after opening quotes
    if stripped.startswith('"""') or stripped.startswith("'''"):
        first_line = stripped[3:].strip()
        if first_line:
            return first_line
        # Next non-empty line
        for j in range(start + 1, min(start + 5, len(lines))):
            candidate = lines[j].strip().rstrip('"""').rstrip("'''").strip()
            if candidate:
                return candidate
    return ""


def summarize_file(path: Path) -> str:
    """Summarize a single file based on its extension.

    Returns an empty string if the language is unsupported or the file is empty.
    """
    if not path.exists():
        return ""
    code = path.read_text()
    if not code.strip():
        return ""

    ext = path.suffix.lower()
    if ext in (".js", ".jsx", ".ts", ".tsx", ".mjs"):
        return summarize_js(code)
    elif ext in (".py",):
        return summarize_py(code)
    return ""


def summarize_files(paths: dict[str, Path]) -> dict[str, str]:
    """Summarize multiple files.

    Args:
        paths: mapping of relative path → absolute Path

    Returns:
        mapping of relative path → summary string (empty entries omitted)
    """
    result = {}
    for rel, abs_path in paths.items():
        summary = summarize_file(abs_path)
        if summary:
            result[rel] = summary
    return result


def format_summaries(
    summaries: dict[str, str],
    header: str = "Verified (green) file signatures",
    preserve_order: bool = False,
) -> str:
    """Format file summaries into a single context string for LLM prompts.

    Args:
        summaries: mapping of relative path → summary text.
        header: section header.
        preserve_order: if True, use dict insertion order; otherwise sort alphabetically.
    """
    if not summaries:
        return ""
    sections = [f"=== {header} ==="]
    items = summaries.items() if preserve_order else sorted(summaries.items())
    for rel_path, summary in items:
        sections.append(f"--- {rel_path} ---\n{summary}")
    return "\n\n".join(sections)
