"""Prompt builders for each LLM call in the game-turn pipeline.

All functions accept plain Python types (strings, dicts, lists) — no
Pydantic models — so this module stays independent of the FastAPI layer
and is easy to unit-test or update without touching the route code.
"""

import json


def starter_prompts_prompt(*, registry: list[dict]) -> str:
    """Build the prompt for dynamic first-run game suggestions."""
    return f"""You create concise starter requests for an AI game studio.

Return ONLY valid JSON with this exact structure:
{{
  "prompts": ["<request 1>", "<request 2>", "<request 3>"]
}}

Rules:
- Return exactly three distinct requests a user could submit directly
- Keep each request under 12 words
- Make every request specific, playful, and immediately understandable
- Cover different available templates
- Include one meaningful customization in each request
- Do not number the requests or add explanations

Available templates:
{json.dumps(registry, indent=2)}

Respond with ONLY the JSON object."""


def edit_suggestions_prompt(
    *,
    template: dict,
    hooks_source: str,
    variants: list[str],
    summary: str,
    generated_code: str,
) -> str:
    """Build the prompt for contextual next-edit suggestions."""
    return f"""You suggest useful next edits for a generated browser game.

Return ONLY valid JSON with this exact structure:
{{
  "suggestions": [
    {{"kind": "edit", "text": "<direct edit request>"}},
    {{"kind": "complete", "text": "<short option to keep the game as-is>"}}
  ]
}}

Rules:
- Suggest zero to three edits that are supported by AVAILABLE HOOKS
- Each edit must be specific, non-duplicative, and ready to submit directly
- Do not suggest features that require changing the engine or adding dependencies
- Do not repeat customizations already present in CURRENT GAME or CURRENT SUMMARY
- Always include exactly one "complete" option
- If no meaningful supported edit remains, return only the "complete" option
- Write the completion text naturally; say the game is good enough when appropriate
- Keep every text under 14 words

TEMPLATE:
{json.dumps(template, indent=2)}

AVAILABLE HOOKS:
{hooks_source}

EXISTING EXAMPLE VARIANTS:
{json.dumps(variants, indent=2)}

CURRENT SUMMARY:
{summary or 'None'}

CURRENT GAME:
{generated_code}

Respond with ONLY the JSON object."""


def planning_prompt(
    *,
    message: str,
    phase: str,
    has_game: bool,
    summary: str,
    pending_question: str | None,
    registry: list[dict],
) -> str:
    """Build the planning prompt that returns a routing decision as JSON."""
    return f"""You are a game creation assistant. Decide the next action.

Return ONLY valid JSON with this exact structure:
{{
  "action": "ask" | "inform" | "generate" | "edit" | "unsupported",
  "template_id": "<id from available templates, or null>",
  "question": "<one short question \u2014 only when action is ask>",
  "summary": "<concise one-sentence summary of what the user wants>"
}}

Rules:
- User asks which templates, game types, or capabilities are available \u2192 action: inform
- Questions about available templates are in scope and must not be marked unsupported
- User has an existing game (has_game=true) and gives feedback \u2192 action: edit
- No game, request is clear \u2192 action: generate
- No game, a critical template-specific detail is unknown \u2192 action: ask with ONE question
- No template fits the requested game \u2192 action: unsupported (explain in summary)
- Do NOT ask about things with sensible defaults (colors, speed, etc.)
- Ask at most one question per turn

Available templates:
{json.dumps(registry, indent=2)}

State:
  phase: {phase}
  has_game: {has_game}
  summary_so_far: {summary or 'none'}
  pending_question: {pending_question or 'none'}

User\u2019s latest message: {message}

Respond with ONLY the JSON object. No explanation, no markdown, no extra text."""


def generation_prompt(
    *,
    message: str,
    summary: str,
    template_name: str,
    base_class: str,
    base_src: str,
    examples_block: str,
) -> str:
    """Build the generation prompt for a brand-new game.js subclass."""
    return f"""You are a JavaScript game developer. Generate a customized {template_name} game subclass.

STRICT CONTRACT \u2014 follow exactly or the code will be rejected:
1. First line: import {{ {base_class}, mount }} from "./base.js";
2. ONE class extending {base_class} with a descriptive name
3. Override only the hooks needed; do not redefine defaults
4. Last line: mount(YourClassName);
5. No Markdown fences (no backticks anywhere)
6. No imports except the one above; no dep/ imports

AVAILABLE HOOKS (all overridable methods):
{base_src}

EXAMPLE GAMES (match this style exactly):
{examples_block}

CONTEXT:
  Summary: {summary or 'New request'}

USER REQUEST: {message}

Output JavaScript only:"""


def edit_prompt(
    *,
    message: str,
    summary: str,
    base_class: str,
    base_src: str,
    generated_code: str,
) -> str:
    """Build the edit prompt to rewrite an existing game.js based on feedback."""
    return f"""You are a JavaScript game developer. Edit an existing game subclass.

STRICT CONTRACT:
1. Keep: import {{ {base_class}, mount }} from "./base.js";
2. Return the COMPLETE updated file, not just the changed parts
3. No Markdown fences, no extra imports, no dep/ imports

AVAILABLE HOOKS (for reference):
{base_src}

CURRENT SUMMARY:
{summary or 'None'}

CURRENT GAME:
{generated_code}

USER FEEDBACK: {message}

Output complete updated JavaScript only:"""


def repair_prompt(
    *,
    validation_error: str,
    base_class: str,
    base_src: str,
    generated_code: str,
) -> str:
    """Build the repair prompt used after generated code fails validation."""
    return f"""You are repairing a generated JavaScript game subclass that failed validation.

VALIDATION ERROR:
{validation_error}

STRICT CONTRACT:
1. First line: import {{ {base_class}, mount }} from "./base.js";
2. Return the COMPLETE corrected file
3. ONE class extending {base_class}
4. Override only methods listed in AVAILABLE HOOKS
5. Last line: mount(YourClassName);
6. No Markdown fences, no extra imports, no dep/ imports

AVAILABLE HOOKS:
{base_src}

INVALID GENERATED CODE:
{generated_code}

Output complete corrected JavaScript only:"""
