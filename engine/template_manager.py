"""Select the game template that best matches a user request.

Each template folder under `engine/templates/` follows a fixed convention
(see `engine/template.md`):

    <template-id>/
      manifest.json   # includes "entry": "base.js"
      base.js         # contract + DOM bootstrap; re-exports the class
      dep/            # private engine implementation
        engine.js
        styles.css
      example/        # generated example game.js files (excluded from bundle)

The HTML shell is not stored in the template folder. It is generated on
demand by `engine.serve` (dev) or the backend bundler (prod) from
`manifest["entry"]`.

The manifest declares the template id, routing keywords, and an optional
`default: true` flag used as a fallback when no keyword matches.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

EXCLUDED_DIRS = frozenset({"example"})


@dataclass(frozen=True)
class Template:
    template_id: str
    template_dir: Path
    manifest: dict

    @property
    def bundle_files(self) -> tuple[Path, ...]:
        files: list[Path] = []
        for path in sorted(self.template_dir.rglob("*")):
            if path.is_dir():
                continue
            rel_parts = path.relative_to(self.template_dir).parts
            if any(part in EXCLUDED_DIRS for part in rel_parts):
                continue
            if path.name == ".gitkeep":
                continue
            files.append(path)
        return tuple(files)


class TemplateManager:
    """Registry-backed template selector.

    Keyword routing is deterministic for the first version. It can later be
    replaced with model-based classification without changing callers.
    """

    def __init__(self, template_root: Path | None = None) -> None:
        self.template_root = template_root or Path(__file__).parent / "templates"
        self._templates = self._load_templates()

    def select(self, user_requirement: str) -> Template:
        if not self._templates:
            raise LookupError("No game templates are installed.")

        requirement = user_requirement.casefold()

        def score(template: Template) -> int:
            return sum(
                keyword.casefold() in requirement
                for keyword in template.manifest.get("routing_keywords", [])
            )

        best = max(self._templates, key=score)
        if score(best) > 0:
            return best

        for template in self._templates:
            if template.manifest.get("default"):
                return template
        return self._templates[0]

    def _load_templates(self) -> list[Template]:
        templates: list[Template] = []
        for manifest_path in sorted(self.template_root.glob("*/manifest.json")):
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            templates.append(
                Template(
                    template_id=manifest["id"],
                    template_dir=manifest_path.parent,
                    manifest=manifest,
                )
            )
        return templates
