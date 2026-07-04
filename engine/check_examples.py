"""Static smoke test for template examples.

For each template, verifies that every file in `example/`:

- follows the naming convention `game_YYMMDD_HHMM_<slug>.js`
- has a `@demonstrates:` tag in its top comment
- imports from `../base.js` (not from `dep/` directly)
- ends with a `mount(<Class>)` call
- overrides only methods listed in `base.js`'s `HOOKS` export

The check is intentionally static: no browser, no node runtime. It
catches ~90% of ways an example can go bad without any dependencies.
For full behavioral verification, load the example via `engine.serve`
and inspect visually.

Usage::

    python3 -m engine.check_examples             # all templates
    python3 -m engine.check_examples snake       # one template
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    from .template_manager import TemplateManager, Template
except ImportError:
    from template_manager import TemplateManager, Template

FILENAME_RE = re.compile(r"^game_\d{6}_\d{4}_[a-z0-9]+(?:_[a-z0-9]+)*\.js$")
HOOKS_RE = re.compile(r"export\s+const\s+HOOKS\s*=\s*\[(.*?)\]\s*;", re.S)
HOOK_NAME_RE = re.compile(r'name\s*:\s*["\']([A-Za-z_][A-Za-z0-9_]*)["\']')
IMPORT_BASE_RE = re.compile(r'from\s+["\']\.\./base\.js["\']')
IMPORT_DEP_RE = re.compile(r'from\s+["\'][^"\']*dep/[^"\']*["\']')
MOUNT_CALL_RE = re.compile(r"\bmount\s*\(")
DEMONSTRATES_RE = re.compile(r"@demonstrates:\s*\S")
METHOD_DEF_RE = re.compile(r"^\s{2}([A-Za-z_][A-Za-z0-9_]*)\s*\(", re.M)


def parse_hooks(base_js: Path) -> set[str]:
    text = base_js.read_text(encoding="utf-8")
    block = HOOKS_RE.search(text)
    if not block:
        return set()
    return set(HOOK_NAME_RE.findall(block.group(1)))


def parse_overrides(example_src: str) -> set[str]:
    class_start = example_src.find("class ")
    if class_start < 0:
        return set()
    # naive: methods are two-space-indented `name(...)` inside the class body.
    return set(METHOD_DEF_RE.findall(example_src[class_start:]))


def check_example(path: Path, hooks: set[str]) -> list[str]:
    problems: list[str] = []
    if not FILENAME_RE.match(path.name):
        problems.append(
            f"filename does not match game_YYMMDD_HHMM_<slug>.js: {path.name}"
        )
    src = path.read_text(encoding="utf-8")
    if not DEMONSTRATES_RE.search(src):
        problems.append("missing @demonstrates tag in top comment")
    if not IMPORT_BASE_RE.search(src):
        problems.append("does not import from ../base.js")
    if IMPORT_DEP_RE.search(src):
        problems.append("imports from dep/ (forbidden — use ../base.js only)")
    if not MOUNT_CALL_RE.search(src):
        problems.append("no mount(...) call found")
    overrides = parse_overrides(src)
    # `constructor` and any method that just happens to share a name with
    # a lifecycle helper are ignored; we only flag overrides that look
    # like hooks (start with `get`, `on`, or `draw`) but are unknown.
    for name in sorted(overrides):
        if name in {"constructor"}:
            continue
        if not (name.startswith("get") or name.startswith("on") or name.startswith("draw")):
            continue
        if name not in hooks:
            problems.append(
                f"overrides `{name}` which is not listed in base.js HOOKS"
            )
    return problems


def check_template(template: Template) -> int:
    base_js = template.template_dir / "base.js"
    hooks = parse_hooks(base_js)
    example_dir = template.template_dir / "example"
    if not example_dir.exists():
        return 0

    failures = 0
    for path in sorted(example_dir.glob("*.js")):
        problems = check_example(path, hooks)
        if problems:
            failures += 1
            print(f"FAIL {template.template_id}/example/{path.name}")
            for p in problems:
                print(f"    - {p}")
        else:
            print(f"ok   {template.template_id}/example/{path.name}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template_id", nargs="?")
    args = parser.parse_args()

    manager = TemplateManager()
    templates = manager._templates
    if args.template_id:
        templates = [t for t in templates if t.template_id == args.template_id]
        if not templates:
            print(f"Unknown template: {args.template_id}", file=sys.stderr)
            return 2

    total_failures = sum(check_template(t) for t in templates)
    if total_failures:
        print(f"\n{total_failures} example(s) failed.")
        return 1
    print("\nAll examples ok.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
